import json
import uuid
import os
from flask import request, jsonify
from flask_restful import Resource
from datetime import datetime
from werkzeug.utils import secure_filename
from model import db, CustomImage, OrderItem, Order, Product, User, UserRole
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from PIL import Image
import base64
from io import BytesIO

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
UPLOAD_FOLDER = 'uploads/custom_images'

def allowed_file(filename):
    """Check if the uploaded file has an allowed extension."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def create_upload_folder():
    """Create upload folder if it doesn't exist."""
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)

def validate_image_size(image_file):
    """Validate image dimensions and file size."""
    try:
        # Check file size
        image_file.seek(0, os.SEEK_END)
        file_size = image_file.tell()
        image_file.seek(0)
        
        if file_size > MAX_FILE_SIZE:
            return False, "File size exceeds 5MB limit"
        
        # Check if it's a valid image
        try:
            img = Image.open(image_file)
            img.verify()
            image_file.seek(0)  # Reset file pointer
            return True, "Valid image"
        except Exception:
            return False, "Invalid image file"
            
    except Exception as e:
        logger.error(f"Error validating image: {str(e)}")
        return False, "Error validating image"

def process_base64_image(base64_data, filename):
    """Process base64 encoded image data."""
    try:
        # Remove data URL prefix if present
        if base64_data.startswith('data:image'):
            base64_data = base64_data.split(',')[1]
        
        # Decode base64 data
        image_data = base64.b64decode(base64_data)
        
        # Create BytesIO object
        image_file = BytesIO(image_data)
        
        # Validate image
        is_valid, message = validate_image_size(image_file)
        if not is_valid:
            return None, message
            
        # Generate unique filename
        file_extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else 'jpg'
        unique_filename = f"{uuid.uuid4().hex}.{file_extension}"
        file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
        
        # Save image
        create_upload_folder()
        with open(file_path, 'wb') as f:
            f.write(image_data)
            
        return file_path, "Image processed successfully"
        
    except Exception as e:
        logger.error(f"Error processing base64 image: {str(e)}")
        return None, "Error processing image data"


class CustomImageResource(Resource):
    
    @jwt_required()
    def get(self, image_id=None):
        """Retrieve a custom image by ID or return user's images if no ID is provided."""
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user:
            return {"message": "User not found"}, 404
        
        if image_id:
            try:
                # Get specific custom image
                if user.role == UserRole.ADMIN:
                    # Admin can view any custom image
                    custom_image = CustomImage.query.get(image_id)
                else:
                    # Regular user can only view images for their own orders
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
        
        # Get query parameters for pagination and filtering
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        order_item_id = request.args.get('order_item_id', type=str)
        product_id = request.args.get('product_id', type=str)
        
        try:
            # Build query based on user role
            if user.role == UserRole.ADMIN:
                # Admin can see all custom images
                query = CustomImage.query
            else:
                # Regular user can only see images for their own orders
                query = CustomImage.query.join(OrderItem).join(Order).filter(Order.user_id == current_user_id)
            
            # Filter by order_item_id if provided
            if order_item_id:
                query = query.filter(CustomImage.order_item_id == order_item_id)
            
            # Filter by product_id if provided
            if product_id:
                query = query.filter(CustomImage.product_id == product_id)
            
            # Order by upload_date descending
            query = query.order_by(CustomImage.upload_date.desc())
            
            # Get custom images with pagination
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
        """Upload a custom image for an order item."""
        try:
            current_user_id = get_jwt_identity()
            user = User.query.get(current_user_id)
            
            if not user:
                return {"message": "User not found"}, 404

            # Handle both form data and JSON data
            if request.content_type and 'multipart/form-data' in request.content_type:
                # Handle file upload
                data = request.form.to_dict()
                file = request.files.get('image')
                
                if not file:
                    return {"message": "No image file provided"}, 400
                
                if file.filename == '':
                    return {"message": "No file selected"}, 400
                
                if not allowed_file(file.filename):
                    return {"message": f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"}, 400
                
                # Validate image
                is_valid, message = validate_image_size(file)
                if not is_valid:
                    return {"message": message}, 400
                
                # Generate unique filename and save
                filename = secure_filename(file.filename)
                unique_filename = f"{uuid.uuid4().hex}_{filename}"
                create_upload_folder()
                file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
                file.save(file_path)
                
                image_url = file_path
                image_name = filename
                
            else:
                # Handle JSON data with base64 image
                data = request.get_json()
                if not data:
                    return {"message": "No data provided"}, 400
                
                if 'image_data' not in data:
                    return {"message": "No image data provided"}, 400
                
                image_name = data.get('image_name', 'uploaded_image.jpg')
                image_url, message = process_base64_image(data['image_data'], image_name)
                
                if not image_url:
                    return {"message": message}, 400

            # Validate required fields
            if 'order_item_id' not in data:
                return {"message": "Missing field: order_item_id"}, 400

            order_item_id = data['order_item_id']

            # Validate order item exists and belongs to user (unless admin)
            if user.role == UserRole.ADMIN:
                order_item = OrderItem.query.get(order_item_id)
            else:
                order_item = OrderItem.query.join(Order).filter(
                    OrderItem.id == order_item_id,
                    Order.user_id == current_user_id
                ).first()

            if not order_item:
                return {"message": "Order item not found"}, 404

            # Check if custom image already exists for this order item
            existing_image = CustomImage.query.filter_by(order_item_id=order_item_id).first()
            if existing_image:
                return {"message": "Custom image already exists for this order item"}, 400

            # Get product_id if provided
            product_id = data.get('product_id')
            if product_id:
                product = Product.query.get(product_id)
                if not product:
                    return {"message": "Product not found"}, 404

            # Create CustomImage instance
            custom_image = CustomImage(
                order_item_id=order_item_id,
                product_id=product_id,
                image_url=image_url,
                image_name=image_name
            )

            db.session.add(custom_image)
            db.session.commit()
            
            return {
                "message": "Custom image uploaded successfully", 
                "custom_image": custom_image.as_dict(), 
                "id": custom_image.id
            }, 201

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error uploading custom image: {str(e)}")
            return {"error": str(e)}, 500

    @jwt_required()
    def put(self, image_id):
        """Update custom image details."""
        try:
            current_user_id = get_jwt_identity()
            user = User.query.get(current_user_id)
            
            if not user:
                return {"message": "User not found"}, 404

            # Get the custom image
            if user.role == UserRole.ADMIN:
                custom_image = CustomImage.query.get(image_id)
            else:
                # Regular user can only update images for their own orders
                custom_image = CustomImage.query.join(OrderItem).join(Order).filter(
                    CustomImage.id == image_id,
                    Order.user_id == current_user_id
                ).first()

            if not custom_image:
                return {"error": "Custom image not found"}, 404

            data = request.get_json()
            if not data:
                return {"error": "No data provided"}, 400

            # Update image name
            if "image_name" in data:
                custom_image.image_name = data["image_name"]

            # Update product_id (admin only or if not yet assigned)
            if "product_id" in data:
                product_id = data.get("product_id")
                if product_id:
                    product = Product.query.get(product_id)
                    if not product:
                        return {"error": "Product not found"}, 400
                custom_image.product_id = product_id

            # Replace image (handle both file upload and base64)
            if request.content_type and 'multipart/form-data' in request.content_type:
                file = request.files.get('new_image')
                if file and file.filename != '':
                    if not allowed_file(file.filename):
                        return {"error": f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"}, 400
                    
                    # Validate new image
                    is_valid, message = validate_image_size(file)
                    if not is_valid:
                        return {"error": message}, 400
                    
                    # Delete old image file if it exists
                    if custom_image.image_url and os.path.exists(custom_image.image_url):
                        try:
                            os.remove(custom_image.image_url)
                        except Exception as e:
                            logger.warning(f"Could not delete old image file: {str(e)}")
                    
                    # Save new image
                    filename = secure_filename(file.filename)
                    unique_filename = f"{uuid.uuid4().hex}_{filename}"
                    create_upload_folder()
                    file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
                    file.save(file_path)
                    
                    custom_image.image_url = file_path
                    custom_image.image_name = filename

            elif "image_data" in data:
                # Handle base64 image replacement
                image_name = data.get('image_name', custom_image.image_name or 'updated_image.jpg')
                new_image_url, message = process_base64_image(data['image_data'], image_name)
                
                if not new_image_url:
                    return {"error": message}, 400
                
                # Delete old image file if it exists
                if custom_image.image_url and os.path.exists(custom_image.image_url):
                    try:
                        os.remove(custom_image.image_url)
                    except Exception as e:
                        logger.warning(f"Could not delete old image file: {str(e)}")
                
                custom_image.image_url = new_image_url
                custom_image.image_name = image_name

            db.session.commit()
            return {"message": "Custom image updated successfully", "custom_image": custom_image.as_dict()}, 200

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating custom image: {str(e)}")
            return {"error": f"An error occurred: {str(e)}"}, 500

    @jwt_required()
    def delete(self, image_id):
        """Delete a custom image."""
        try:
            current_user_id = get_jwt_identity()
            user = User.query.get(current_user_id)
            
            if not user:
                return {"message": "User not found"}, 404

            # Get the custom image
            if user.role == UserRole.ADMIN:
                custom_image = CustomImage.query.get(image_id)
            else:
                # Regular user can only delete images for their own orders
                custom_image = CustomImage.query.join(OrderItem).join(Order).filter(
                    CustomImage.id == image_id,
                    Order.user_id == current_user_id
                ).first()

            if not custom_image:
                return {"error": "Custom image not found"}, 404

            # Delete the physical file
            if custom_image.image_url and os.path.exists(custom_image.image_url):
                try:
                    os.remove(custom_image.image_url)
                except Exception as e:
                    logger.warning(f"Could not delete image file: {str(e)}")

            db.session.delete(custom_image)
            db.session.commit()
            return {"message": "Custom image deleted successfully"}, 200
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting custom image id {image_id}: {str(e)}", exc_info=True)
            return {"error": "An unexpected error occurred during image deletion."}, 500


class CustomImageApprovalResource(Resource):
    """Resource for admin to approve custom images and assign products."""
    
    @jwt_required()
    def put(self, image_id):
        """Approve custom image and assign product (Admin only)."""
        try:
            current_user_id = get_jwt_identity()
            user = User.query.get(current_user_id)
            
            if not user or user.role != UserRole.ADMIN:
                return {"message": "Only admins can approve custom images"}, 403

            custom_image = CustomImage.query.get(image_id)
            if not custom_image:
                return {"error": "Custom image not found"}, 404

            data = request.get_json()
            if not data:
                return {"error": "No data provided"}, 400

            # Assign product to custom image
            if "product_id" in data:
                product_id = data["product_id"]
                if product_id:
                    product = Product.query.get(product_id)
                    if not product:
                        return {"error": "Product not found"}, 400
                    
                    # Check if product supports custom images (you might want to add this field to Product model)
                    custom_image.product_id = product_id
                else:
                    custom_image.product_id = None

            # Update image name if provided
            if "image_name" in data:
                custom_image.image_name = data["image_name"]

            db.session.commit()
            
            return {
                "message": "Custom image approved and product assigned successfully",
                "custom_image": custom_image.as_dict()
            }, 200

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error approving custom image: {str(e)}")
            return {"error": f"An error occurred: {str(e)}"}, 500


class AdminCustomImagesResource(Resource):
    """Resource for admins to manage all custom images."""
    
    @jwt_required()
    def get(self):
        """Retrieve all custom images for admin management."""
        try:
            current_user_id = get_jwt_identity()
            user = User.query.get(current_user_id)

            if not user or user.role != UserRole.ADMIN:
                return {"message": "Only admins can access this endpoint"}, 403

            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 10, type=int)
            has_product = request.args.get('has_product', type=str)
            
            # Build query
            query = CustomImage.query
            
            # Filter by product assignment if provided
            if has_product:
                if has_product.lower() == 'true':
                    query = query.filter(CustomImage.product_id.isnot(None))
                elif has_product.lower() == 'false':
                    query = query.filter(CustomImage.product_id.is_(None))
            
            # Get all custom images with pagination, ordered by upload date
            custom_images = query.order_by(CustomImage.upload_date.desc()).paginate(
                page=page, per_page=per_page, error_out=False
            )
            
            # Enhanced response with order and product details
            image_data = []
            for custom_image in custom_images.items:
                image_dict = custom_image.as_dict()
                
                # Add order item and order information
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
                
                # Add product information if assigned
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


def register_custom_image_resources(api):
    """Registers the CustomImage resource routes with Flask-RESTful API."""
    api.add_resource(CustomImageResource, "/custom-images", "/custom-images/<string:image_id>")
    api.add_resource(CustomImageApprovalResource, "/custom-images/<string:image_id>/approve")
    api.add_resource(AdminCustomImagesResource, "/admin/custom-images")