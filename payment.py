import json
import uuid
from flask import request, jsonify
from flask_restful import Resource
from datetime import datetime
from model import db, Payment, PaymentStatus, Order, OrderStatus, User, UserRole
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from decimal import Decimal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PaymentResource(Resource):
    
    @jwt_required()
    def get(self, payment_id=None):
        """Retrieve a payment by ID or return user's payments if no ID is provided."""
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user:
            return {"message": "User not found"}, 404
        
        if payment_id:
            try:
                # Get specific payment
                if user.role == UserRole.ADMIN:
                    # Admin can view any payment
                    payment = Payment.query.get(payment_id)
                else:
                    # Regular user can only view payments for their own orders
                    payment = Payment.query.join(Order).filter(
                        Payment.id == payment_id,
                        Order.user_id == current_user_id
                    ).first()
                
                if payment:
                    return payment.as_dict(), 200
                return {"message": "Payment not found"}, 404
            except (OperationalError, SQLAlchemyError) as e:
                logger.error(f"Database error: {str(e)}")
                return {"message": "Database connection error"}, 500
        
        # Get query parameters for pagination and filtering
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        status = request.args.get('status', type=str)
        order_id = request.args.get('order_id', type=str)
        
        try:
            # Build query based on user role
            if user.role == UserRole.ADMIN:
                # Admin can see all payments
                query = Payment.query
            else:
                # Regular user can only see payments for their own orders
                query = Payment.query.join(Order).filter(Order.user_id == current_user_id)
            
            # Filter by order_id if provided
            if order_id:
                query = query.filter(Payment.order_id == order_id)
            
            # Filter by status if provided
            if status:
                try:
                    status_enum = PaymentStatus(status.lower())
                    query = query.filter(Payment.status == status_enum)
                except ValueError:
                    return {"message": "Invalid status value"}, 400
            
            # Order by payment_date descending
            query = query.order_by(Payment.payment_date.desc())
            
            # Get payments with pagination
            payments = query.paginate(page=page, per_page=per_page, error_out=False)
            
            if not payments.items:
                return {
                    'payments': [],
                    'total': 0,
                    'pages': 0,
                    'current_page': page
                }
            
            return {
                'payments': [payment.as_dict() for payment in payments.items],
                'total': payments.total,
                'pages': payments.pages,
                'current_page': payments.page
            }, 200
            
        except (OperationalError, SQLAlchemyError) as e:
            logger.error(f"Database error: {str(e)}")
            return {"message": "Database connection error"}, 500
        except Exception as e:
            logger.error(f"Error fetching payments: {str(e)}")
            return {"message": "Error fetching payments"}, 500

    @jwt_required()
    def post(self):
        """Submit M-Pesa payment code for an order."""
        try:
            current_user_id = get_jwt_identity()
            user = User.query.get(current_user_id)
            
            if not user:
                return {"message": "User not found"}, 404

            data = request.get_json()
            if not data:
                return {"message": "No data provided"}, 400

            # Validate required fields
            required_fields = ["order_id", "mpesa_code", "phone_number"]
            for field in required_fields:
                if field not in data:
                    return {"message": f"Missing field: {field}"}, 400

            order_id = data["order_id"]
            mpesa_code = data["mpesa_code"].strip()
            phone_number = data["phone_number"].strip()

            # Validate order exists and belongs to user (unless admin)
            if user.role == UserRole.ADMIN:
                order = Order.query.get(order_id)
            else:
                order = Order.query.filter_by(id=order_id, user_id=current_user_id).first()

            if not order:
                return {"message": "Order not found"}, 404

            # Check if order is in a valid state for payment
            if order.status in [OrderStatus.CANCELLED, OrderStatus.DELIVERED]:
                return {"message": "Cannot make payment for order in current status"}, 400

            # Check if payment already exists for this order
            existing_payment = Payment.query.filter_by(order_id=order_id).first()
            if existing_payment:
                if existing_payment.status == PaymentStatus.VERIFIED:
                    return {"message": "Payment already verified for this order"}, 400
                elif existing_payment.status == PaymentStatus.PENDING:
                    return {"message": "Payment already submitted and pending verification"}, 400

            # Validate M-Pesa code format (basic validation)
            if len(mpesa_code) < 8:
                return {"message": "Invalid M-Pesa code format"}, 400

            # Validate phone number format (basic validation)
            if not phone_number.startswith(('254', '+254', '07', '01')):
                return {"message": "Invalid phone number format"}, 400

            # Create Payment instance
            payment = Payment(
                order_id=order_id,
                mpesa_code=mpesa_code,
                amount=order.total_amount,
                phone_number=phone_number,
                status=PaymentStatus.PENDING
            )

            db.session.add(payment)
            db.session.commit()
            
            return {
                "message": "M-Pesa code submitted successfully. Awaiting admin verification.", 
                "payment": payment.as_dict(), 
                "id": payment.id
            }, 201

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error submitting payment: {str(e)}")
            return {"error": str(e)}, 500

    @jwt_required()
    def put(self, payment_id):
        """Update payment details. Users can update pending payments, admins can update any payment."""
        try:
            current_user_id = get_jwt_identity()
            user = User.query.get(current_user_id)
            
            if not user:
                return {"message": "User not found"}, 404

            # Get the payment
            if user.role == UserRole.ADMIN:
                payment = Payment.query.get(payment_id)
            else:
                # Regular user can only update payments for their own orders
                payment = Payment.query.join(Order).filter(
                    Payment.id == payment_id,
                    Order.user_id == current_user_id
                ).first()

            if not payment:
                return {"error": "Payment not found"}, 404

            # Check if payment can be updated
            if payment.status == PaymentStatus.VERIFIED and user.role != UserRole.ADMIN:
                return {"message": "Cannot update verified payment"}, 400

            data = request.get_json()
            if not data:
                return {"error": "No data provided"}, 400

            # Update M-Pesa code (users can update if pending, admins can always update)
            if "mpesa_code" in data:
                if payment.status == PaymentStatus.PENDING or user.role == UserRole.ADMIN:
                    mpesa_code = data["mpesa_code"].strip()
                    if len(mpesa_code) < 8:
                        return {"error": "Invalid M-Pesa code format"}, 400
                    payment.mpesa_code = mpesa_code
                else:
                    return {"error": "Cannot update M-Pesa code for verified payment"}, 400

            # Update phone number
            if "phone_number" in data:
                if payment.status == PaymentStatus.PENDING or user.role == UserRole.ADMIN:
                    phone_number = data["phone_number"].strip()
                    if not phone_number.startswith(('254', '+254', '07', '01')):
                        return {"error": "Invalid phone number format"}, 400
                    payment.phone_number = phone_number
                else:
                    return {"error": "Cannot update phone number for verified payment"}, 400

            db.session.commit()
            return {"message": "Payment updated successfully", "payment": payment.as_dict()}, 200

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating payment: {str(e)}")
            return {"error": f"An error occurred: {str(e)}"}, 500

    @jwt_required()
    def delete(self, payment_id):
        """Delete/cancel a pending payment."""
        try:
            current_user_id = get_jwt_identity()
            user = User.query.get(current_user_id)
            
            if not user:
                return {"message": "User not found"}, 404

            # Get the payment
            if user.role == UserRole.ADMIN:
                payment = Payment.query.get(payment_id)
            else:
                # Regular user can only delete payments for their own orders
                payment = Payment.query.join(Order).filter(
                    Payment.id == payment_id,
                    Order.user_id == current_user_id
                ).first()

            if not payment:
                return {"error": "Payment not found"}, 404

            # Check if payment can be deleted
            if payment.status == PaymentStatus.VERIFIED and user.role != UserRole.ADMIN:
                return {"message": "Cannot delete verified payment"}, 400

            db.session.delete(payment)
            db.session.commit()
            return {"message": "Payment deleted successfully"}, 200
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting payment id {payment_id}: {str(e)}", exc_info=True)
            return {"error": "An unexpected error occurred during payment deletion."}, 500


class PaymentVerificationResource(Resource):
    """Resource for admin to verify/reject M-Pesa payments."""
    
    @jwt_required()
    def put(self, payment_id):
        """Verify or reject a payment (Admin only)."""
        try:
            current_user_id = get_jwt_identity()
            user = User.query.get(current_user_id)
            
            if not user or user.role != UserRole.ADMIN:
                return {"message": "Only admins can verify payments"}, 403

            payment = Payment.query.get(payment_id)
            if not payment:
                return {"error": "Payment not found"}, 404

            data = request.get_json()
            if not data or 'status' not in data:
                return {"error": "Status is required"}, 400

            try:
                new_status = PaymentStatus(data["status"].lower())
                
                # Only allow verification transitions
                if new_status not in [PaymentStatus.VERIFIED, PaymentStatus.REJECTED]:
                    return {"error": "Invalid status. Only 'verified' or 'rejected' allowed"}, 400

                old_status = payment.status
                payment.status = new_status
                
                # Update related order status if payment is verified
                if new_status == PaymentStatus.VERIFIED:
                    order = Order.query.get(payment.order_id)
                    if order and order.status == OrderStatus.PENDING:
                        order.status = OrderStatus.CONFIRMED
                        order.approved_by = current_user_id
                        order.updated_at = datetime.utcnow()
                
                db.session.commit()
                
                return {
                    "message": f"Payment status updated from {old_status.value} to {new_status.value}",
                    "payment": payment.as_dict()
                }, 200
                
            except ValueError:
                return {"error": "Invalid status value"}, 400

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error verifying payment: {str(e)}")
            return {"error": f"An error occurred: {str(e)}"}, 500


class AdminPaymentsResource(Resource):
    """Resource for admins to manage all payments."""
    
    @jwt_required()
    def get(self):
        """Retrieve all payments for admin management."""
        try:
            current_user_id = get_jwt_identity()
            user = User.query.get(current_user_id)

            if not user or user.role != UserRole.ADMIN:
                return {"message": "Only admins can access this endpoint"}, 403

            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 10, type=int)
            status = request.args.get('status', type=str)
            
            # Build query
            query = Payment.query
            
            # Filter by status if provided
            if status:
                try:
                    status_enum = PaymentStatus(status.lower())
                    query = query.filter(Payment.status == status_enum)
                except ValueError:
                    return {"message": "Invalid status value"}, 400
            
            # Get all payments with pagination, ordered by date
            payments = query.order_by(Payment.payment_date.desc()).paginate(
                page=page, per_page=per_page, error_out=False
            )
            
            # Enhanced response with order details
            payment_data = []
            for payment in payments.items:
                payment_dict = payment.as_dict()
                # Add order information
                order = Order.query.get(payment.order_id)
                if order:
                    payment_dict['order_info'] = {
                        'order_number': order.order_number,
                        'customer_name': order.customer_name,
                        'customer_phone': order.customer_phone,
                        'status': order.status.value
                    }
                payment_data.append(payment_dict)
            
            return {
                'payments': payment_data,
                'total': payments.total,
                'pages': payments.pages,
                'current_page': payments.page
            }, 200
            
        except Exception as e:
            logger.error(f"Error fetching admin payments: {str(e)}")
            return {"message": "Error fetching payments"}, 500


def register_payment_resources(api):
    """Registers the Payment resource routes with Flask-RESTful API."""
    api.add_resource(PaymentResource, "/payments", "/payments/<string:payment_id>")
    api.add_resource(PaymentVerificationResource, "/payments/<string:payment_id>/verify")
    api.add_resource(AdminPaymentsResource, "/admin/payments")