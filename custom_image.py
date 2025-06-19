import json
import uuid
import os
from flask import request, jsonify
from flask_restful import Resource
from datetime import datetime
from werkzeug.utils import secure_filename
from model import db, CustomImage, OrderItem, Order, Product, User, UserRole, ImageApprovalStatus
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from PIL import Image
import base64
from io import BytesIO
import cloudinary.uploader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

class TempImageResource(Resource):
    @jwt_required()
    def post(self):
        try:
            current_user_id = get_jwt_identity()
            user = User.query.get(current_user_id)

            if not user:
                return {"message": "User not found"}, 404

            if not request.content_type or 'multipart/form-data' not in request.content_type:
                return {"message": "Content-Type must be multipart/form-data"}, 400

            files = request.files.get('image')
            if not files or files.filename == '':
                return {"message": "No image file provided"}, 400

            if not allowed_file(files.filename):
                return {"message": "Invalid file type. Allowed types: PNG, JPG, JPEG, GIF, WEBP"}, 400

            try:
                upload_result = cloudinary.uploader.upload(
                    files,
                    folder="custom_images/temp",
                    resource_type="auto",
                    public_id=f"temp_{current_user_id}_{int(datetime.utcnow().timestamp())}"
                )
                image_url = upload_result.get('secure_url')
                cloudinary_public_id = upload_result.get('public_id')
            except Exception as e:
                logger.error(f"Error uploading image to Cloudinary: {str(e)}")
                return {"message": "Failed to upload image"}, 500

            custom_image = CustomImage(
                user_id=current_user_id,
                image_url=image_url,
                image_name=files.filename,
                cloudinary_public_id=cloudinary_public_id,
                approval_status=ImageApprovalStatus.PENDING,
                is_temporary=True,
                order_item_id=None,
                product_id=None
            )

            db.session.add(custom_image)
            db.session.commit()

            return {
                "message": "Custom image uploaded successfully and pending approval",
                "id": custom_image.id,
                "image_url": custom_image.image_url,
                "image_name": custom_image.image_name,
                "approval_status": custom_image.approval_status.value
            }, 201

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error uploading temp custom image: {str(e)}")
            return {"error": str(e)}, 500

    @jwt_required()
    def delete(self, image_id):
        try:
            current_user_id = get_jwt_identity()

            temp_image = CustomImage.query.filter_by(
                id=image_id,
                user_id=current_user_id,
                is_temporary=True
            ).first()

            if not temp_image:
                return {"message": "Temporary image not found"}, 404

            if temp_image.cloudinary_public_id:
                try:
                    cloudinary.uploader.destroy(temp_image.cloudinary_public_id)
                except Exception as e:
                    logger.warning(f"Failed to delete temp image from Cloudinary: {str(e)}")

            db.session.delete(temp_image)
            db.session.commit()

            return {"message": "Temporary image deleted successfully"}, 200
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting temporary image id {image_id}: {str(e)}")
            return {"error": "An unexpected error occurred during image deletion."}, 500

class CustomImageResource(Resource):
    @jwt_required()
    def get(self, image_id=None):
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)

        if not user:
            return {"message": "User not found"}, 404

        if image_id:
            try:
                if user.role == UserRole.ADMIN:
                    custom_image = CustomImage.query.get(image_id)
                else:
                    custom_image = CustomImage.query.join(OrderItem).join(Order).filter(
                        CustomImage.id == image_id,
                        Order.user_id == current_user_id
                    ).first()

                if custom_image:
                    return custom_image.as_dict(), 200
                return {"message": "Custom image not found"}, 404
            except (OperationalError, SQLAlchemyError) as e:
                logger.error(f"Database error: {str(e)}")
                return {"message": "Database connection error"}, 500

        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        order_item_id = request.args.get('order_item_id', type=str)
        product_id = request.args.get('product_id', type=str)

        try:
            if user.role == UserRole.ADMIN:
                query = CustomImage.query
            else:
                query = CustomImage.query.join(OrderItem).join(Order).filter(Order.user_id == current_user_id)

            if order_item_id:
                query = query.filter(CustomImage.order_item_id == order_item_id)

            if product_id:
                query = query.filter(CustomImage.product_id == product_id)

            query = query.order_by(CustomImage.upload_date.desc())

            custom_images = query.paginate(page=page, per_page=per_page, error_out=False)

            if not custom_images.items:
                return {
                    'custom_images': [],
                    'total': 0,
                    'pages': 0,
                    'current_page': page
                }

            return {
                'custom_images': [img.as_dict() for img in custom_images.items],
                'total': custom_images.total,
                'pages': custom_images.pages,
                'current_page': custom_images.page
            }, 200

        except (OperationalError, SQLAlchemyError) as e:
            logger.error(f"Database error: {str(e)}")
            return {"message": "Database connection error"}, 500
        except Exception as e:
            logger.error(f"Error fetching custom images: {str(e)}")
            return {"message": "Error fetching custom images"}, 500

    @jwt_required()
    def post(self):
        try:
            current_user_id = get_jwt_identity()
            user = User.query.get(current_user_id)

            if not user:
                return {"message": "User not found"}, 404

            if request.content_type and 'multipart/form-data' in request.content_type:
                data = request.form.to_dict()
                files = request.files.get('image')

                if not files:
                    return {"message": "No image file provided"}, 400

                if files.filename == '':
                    return {"message": "No file selected"}, 400

                if 'order_item_id' not in data:
                    return {"message": "Missing field: order_item_id"}, 400

                order_item_id = data['order_item_id']

                if user.role == UserRole.ADMIN:
                    order_item = OrderItem.query.get(order_item_id)
                else:
                    order_item = OrderItem.query.join(Order).filter(
                        OrderItem.id == order_item_id,
                        Order.user_id == current_user_id
                    ).first()

                if not order_item:
                    return {"message": "Order item not found"}, 404

                existing_image = CustomImage.query.filter_by(order_item_id=order_item_id).first()
                if existing_image:
                    return {"message": "Custom image already exists for this order item"}, 400

                if not allowed_file(files.filename):
                    return {"message": "Invalid file type. Allowed types: PNG, JPG, JPEG, GIF, WEBP"}, 400

                try:
                    upload_result = cloudinary.uploader.upload(
                        files,
                        folder="custom_images/pending",
                        resource_type="auto",
                        public_id=f"pending_{order_item_id}_{int(datetime.utcnow().timestamp())}"
                    )
                    image_url = upload_result.get('secure_url')
                    cloudinary_public_id = upload_result.get('public_id')
                except Exception as e:
                    logger.error(f"Error uploading image to Cloudinary: {str(e)}")
                    return {"message": "Failed to upload image"}, 500

                custom_image = CustomImage(
                    order_item_id=order_item_id,
                    image_url=image_url,
                    image_name=files.filename,
                    cloudinary_public_id=cloudinary_public_id,
                    approval_status=ImageApprovalStatus.PENDING
                )

                db.session.add(custom_image)
                db.session.commit()

                return {
                    "message": "Custom image uploaded successfully and pending approval",
                    "custom_image": custom_image.as_dict(),
                    "id": custom_image.id
                }, 201

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error uploading custom image: {str(e)}")
            return {"error": str(e)}, 500

    @jwt_required()
    def delete(self, image_id):
        try:
            current_user_id = get_jwt_identity()
            user = User.query.get(current_user_id)

            if not user:
                return {"message": "User not found"}, 404

            if user.role == UserRole.ADMIN:
                custom_image = CustomImage.query.get(image_id)
            else:
                custom_image = CustomImage.query.join(OrderItem).join(Order).filter(
                    CustomImage.id == image_id,
                    Order.user_id == current_user_id
                ).first()

            if not custom_image:
                return {"error": "Custom image not found"}, 404

            if custom_image.cloudinary_public_id:
                try:
                    cloudinary.uploader.destroy(custom_image.cloudinary_public_id)
                except Exception as e:
                    logger.warning(f"Failed to delete image from Cloudinary: {str(e)}")

            db.session.delete(custom_image)
            db.session.commit()
            return {"message": "Custom image deleted successfully"}, 200

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting custom image id {image_id}: {str(e)}")
            return {"error": "An unexpected error occurred during image deletion."}, 500

class CustomImageApprovalResource(Resource):
    @jwt_required()
    def put(self, image_id):
        try:
            current_user_id = get_jwt_identity()
            user = User.query.get(current_user_id)

            if not user or user.role != UserRole.ADMIN:
                return {"message": "Only admins can approve/reject custom images"}, 403

            custom_image = CustomImage.query.get(image_id)
            if not custom_image:
                return {"error": "Custom image not found"}, 404

            data = request.get_json()
            if not data:
                return {"error": "No data provided"}, 400

            action = data.get('action')

            if action == 'approve':
                if custom_image.cloudinary_public_id:
                    try:
                        new_public_id = custom_image.cloudinary_public_id.replace('pending_', 'approved_')
                        new_public_id = new_public_id.replace('custom_images/pending/', 'custom_images/approved/')

                        cloudinary.uploader.rename(
                            custom_image.cloudinary_public_id,
                            f"custom_images/approved/{new_public_id}"
                        )

                        custom_image.cloudinary_public_id = f"custom_images/approved/{new_public_id}"
                        custom_image.image_url = cloudinary.CloudinaryImage(f"custom_images/approved/{new_public_id}").build_url()

                    except Exception as e:
                        logger.error(f"Error moving image to approved folder: {str(e)}")
                        return {"error": "Failed to move image to approved folder"}, 500

                custom_image.approval_status = ImageApprovalStatus.APPROVED
                custom_image.approved_by = current_user_id
                custom_image.approval_date = datetime.utcnow()

                if "product_id" in data:
                    product_id = data["product_id"]
                    if product_id:
                        product = Product.query.get(product_id)
                        if not product:
                            return {"error": "Product not found"}, 400
                        custom_image.product_id = product_id

                message = "Custom image approved successfully"

            elif action == 'reject':
                if custom_image.cloudinary_public_id:
                    try:
                        cloudinary.uploader.destroy(custom_image.cloudinary_public_id)
                    except Exception as e:
                        logger.warning(f"Failed to delete rejected image from Cloudinary: {str(e)}")

                custom_image.approval_status = ImageApprovalStatus.REJECTED
                custom_image.approved_by = current_user_id
                custom_image.approval_date = datetime.utcnow()
                custom_image.rejection_reason = data.get('rejection_reason', 'No reason provided')

                message = "Custom image rejected successfully"

            else:
                return {"error": "Invalid action. Use 'approve' or 'reject'"}, 400

            db.session.commit()

            return {
                "message": message,
                "custom_image": custom_image.as_dict()
            }, 200

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error processing custom image approval: {str(e)}")
            return {"error": f"An error occurred: {str(e)}"}, 500

class AdminCustomImagesResource(Resource):
    @jwt_required()
    def get(self):
        try:
            current_user_id = get_jwt_identity()
            user = User.query.get(current_user_id)

            if not user or user.role != UserRole.ADMIN:
                return {"message": "Only admins can access this endpoint"}, 403

            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 10, type=int)
            status = request.args.get('status', type=str)

            query = CustomImage.query

            if status:
                try:
                    status_enum = ImageApprovalStatus(status.lower())
                    query = query.filter(CustomImage.approval_status == status_enum)
                except ValueError:
                    return {"error": "Invalid status. Use: pending, approved, rejected"}, 400

            custom_images = query.order_by(CustomImage.upload_date.desc()).paginate(
                page=page, per_page=per_page, error_out=False
            )

            image_data = []
            for custom_image in custom_images.items:
                image_dict = custom_image.as_dict()

                if custom_image.order_item_id:
                    order_item = OrderItem.query.get(custom_image.order_item_id)
                    if order_item:
                        order = Order.query.get(order_item.order_id)
                        if order:
                            image_dict['order_info'] = {
                                'order_number': order.order_number,
                                'customer_name': order.customer_name,
                                'order_status': order.status.value
                            }
                            image_dict['order_item_info'] = {
                                'quantity': order_item.quantity,
                                'unit_price': float(order_item.unit_price)
                            }

                if custom_image.product_id:
                    product = Product.query.get(custom_image.product_id)
                    if product:
                        image_dict['product_info'] = {
                            'name': product.name,
                            'description': product.description,
                            'price': float(product.price)
                        }

                image_data.append(image_dict)

            return {
                'custom_images': image_data,
                'total': custom_images.total,
                'pages': custom_images.pages,
                'current_page': custom_images.page
            }, 200

        except Exception as e:
            logger.error(f"Error fetching admin custom images: {str(e)}")
            return {"message": "Error fetching custom images"}, 500

def cleanup_abandoned_pending_images():
    try:
        from datetime import timedelta

        cutoff_date = datetime.utcnow() - timedelta(days=7)

        abandoned_images = CustomImage.query.filter(
            CustomImage.approval_status == ImageApprovalStatus.PENDING,
            CustomImage.upload_date < cutoff_date
        ).all()

        for image in abandoned_images:
            if image.cloudinary_public_id:
                try:
                    cloudinary.uploader.destroy(image.cloudinary_public_id)
                except Exception as e:
                    logger.warning(f"Failed to delete abandoned image from Cloudinary: {str(e)}")

            db.session.delete(image)

        db.session.commit()
        logger.info(f"Cleaned up {len(abandoned_images)} abandoned pending images")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error cleaning up abandoned images: {str(e)}")

def register_custom_image_resources(api):
    api.add_resource(CustomImageResource, "/custom-images", "/custom-images/<string:image_id>")
    api.add_resource(CustomImageApprovalResource, "/custom-images/<string:image_id>/approve")
    api.add_resource(AdminCustomImagesResource, "/admin/custom-images")
    api.add_resource(TempImageResource, "/temp-images", "/temp-images/<string:image_id>")
