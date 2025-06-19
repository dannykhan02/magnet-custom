import json
import uuid
from flask import request, jsonify
from flask_restful import Resource
from datetime import datetime
from model import db, Order, OrderItem, OrderStatus, User, UserRole, Product, PickupPoint
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from decimal import Decimal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_order_number():
    """Generate a unique order number."""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    random_part = str(uuid.uuid4())[:8].upper()
    return f"ORD-{timestamp}-{random_part}"


class OrderResource(Resource):
    
    @jwt_required()
    def get(self, order_id=None):
        """Retrieve an order by ID or return user's orders if no ID is provided."""
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user:
            return {"message": "User not found"}, 404
        
        if order_id:
            try:
                # Get specific order
                if user.role == UserRole.ADMIN:
                    # Admin can view any order
                    order = Order.query.get(order_id)
                else:
                    # Regular user can only view their own orders
                    order = Order.query.filter_by(id=order_id, user_id=current_user_id).first()
                
                if order:
                    return order.as_dict(), 200
                return {"message": "Order not found"}, 404
            except (OperationalError, SQLAlchemyError) as e:
                logger.error(f"Database error: {str(e)}")
                return {"message": "Database connection error"}, 500
        
        # Get query parameters for pagination and filtering
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        status = request.args.get('status', type=str)
        
        try:
            # Build query based on user role
            if user.role == UserRole.ADMIN:
                # Admin can see all orders
                query = Order.query
            else:
                # Regular user can only see their own orders
                query = Order.query.filter_by(user_id=current_user_id)
            
            # Filter by status if provided
            if status:
                try:
                    status_enum = OrderStatus(status.lower())
                    query = query.filter_by(status=status_enum)
                except ValueError:
                    return {"message": "Invalid status value"}, 400
            
            # Order by created_at descending
            query = query.order_by(Order.created_at.desc())
            
            # Get orders with pagination
            orders = query.paginate(page=page, per_page=per_page, error_out=False)
            
            if not orders.items:
                return {
                    'orders': [],
                    'total': 0,
                    'pages': 0,
                    'current_page': page
                }
            
            return {
                'orders': [order.as_dict() for order in orders.items],
                'total': orders.total,
                'pages': orders.pages,
                'current_page': orders.page
            }, 200
            
        except (OperationalError, SQLAlchemyError) as e:
            logger.error(f"Database error: {str(e)}")
            return {"message": "Database connection error"}, 500
        except Exception as e:
            logger.error(f"Error fetching orders: {str(e)}")
            return {"message": "Error fetching orders"}, 500

    @jwt_required()
    def post(self):
        """Create a new order with minimal required data (order items only)."""
        try:
            current_user_id = get_jwt_identity()
            user = User.query.get(current_user_id)
            
            if not user:
                return {"message": "User not found"}, 404

            data = request.get_json()
            if not data:
                return {"message": "No data provided"}, 400

            # Validate required fields (only order_items now required)
            required_fields = ["order_items"]
            for field in required_fields:
                if field not in data:
                    return {"message": f"Missing field: {field}"}, 400

            # Validate order items
            order_items_data = data.get("order_items", [])
            if not order_items_data:
                return {"message": "Order must contain at least one item"}, 400

            # Calculate total amount and validate products
            total_amount = Decimal('0.00')
            validated_items = []
            
            for item_data in order_items_data:
                if 'product_id' not in item_data or 'quantity' not in item_data:
                    return {"message": "Each order item must have product_id and quantity"}, 400
                
                product = Product.query.get(item_data['product_id'])
                if not product or not product.is_active:
                    return {"message": f"Product not found or inactive: {item_data['product_id']}"}, 400
                
                quantity = int(item_data['quantity'])
                if quantity <= 0:
                    return {"message": "Quantity must be greater than 0"}, 400
                
                if product.quantity < quantity:
                    return {"message": f"Insufficient stock for product: {product.name}. Available: {product.quantity}"}, 400
                
                item_total = product.price * quantity
                total_amount += item_total
                
                validated_items.append({
                    'product': product,
                    'quantity': quantity,
                    'unit_price': product.price,
                    'total_price': item_total
                })

            # Generate unique order number
            order_number = generate_order_number()
            while Order.query.filter_by(order_number=order_number).first():
                order_number = generate_order_number()

            # Create Order instance with minimal required data
            order = Order(
                user_id=current_user_id,
                order_number=order_number,
                total_amount=total_amount,
                status= OrderStatus.PENDING,  # Initial status
                # Optional fields - can be None initially
                customer_name=data.get("customer_name"),
                customer_phone=data.get("customer_phone"),
                delivery_address=data.get("delivery_address"),
                city=data.get("city"),
                pickup_point_id=data.get("pickup_point_id"),
                order_notes=data.get("order_notes")
            )

            db.session.add(order)
            db.session.flush()  # Get the order ID

            # Create order items and update product quantities
            for item_data in validated_items:
                order_item = OrderItem(
                    order_id=order.id,
                    product_id=item_data['product'].id,
                    quantity=item_data['quantity'],
                    unit_price=item_data['unit_price'],
                    total_price=item_data['total_price']
                )
                db.session.add(order_item)
                
                # Update product quantity
                item_data['product'].quantity -= item_data['quantity']

            db.session.commit()
            
            return {
                "message": "Order created successfully", 
                "order": order.as_dict(), 
                "id": order.id,
                "status": "draft" if not all([order.customer_name, order.customer_phone]) else "pending"
            }, 201

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating order: {str(e)}")
            return {"error": str(e)}, 500

    @jwt_required()
    def put(self, order_id):
        """Update order details (customer info, pickup points, etc.)."""
        try:
            current_user_id = get_jwt_identity()
            user = User.query.get(current_user_id)
            
            if not user:
                return {"message": "User not found"}, 404

            # Get the order
            order = Order.query.filter_by(id=order_id, user_id=current_user_id).first()
            if not order:
                return {"message": "Order not found or access denied"}, 404

            # Check if order can be modified (only draft and pending orders)
            if order.status not in ['draft', 'pending']:
                return {"message": f"Cannot modify order with status: {order.status}"}, 400

            data = request.get_json()
            if not data:
                return {"message": "No data provided"}, 400

            # Validate pickup point if provided
            pickup_point_id = data.get("pickup_point_id")
            if pickup_point_id:
                pickup_point = PickupPoint.query.get(pickup_point_id)
                if not pickup_point or not pickup_point.is_active:
                    return {"message": "Invalid or inactive pickup point"}, 400

            # Update order fields
            updatable_fields = [
                'customer_name', 'customer_phone', 'delivery_address', 
                'city', 'pickup_point_id', 'order_notes'
            ]
            
            updated_fields = []
            for field in updatable_fields:
                if field in data:
                    setattr(order, field, data[field])
                    updated_fields.append(field)

            # Update status based on completeness
            if order.customer_name and order.customer_phone:
                if order.status == 'draft':
                    order.status = 'pending'
            
            # Add timestamp for last update
            order.updated_at = datetime.utcnow()

            db.session.commit()
            
            return {
                "message": "Order updated successfully",
                "order": order.as_dict(),
                "updated_fields": updated_fields,
                "status": order.status
            }, 200

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating order: {str(e)}")
            return {"error": str(e)}, 500

    @jwt_required()
    def patch(self, order_id):
        """Add or modify order items for existing order."""
        try:
            current_user_id = get_jwt_identity()
            user = User.query.get(current_user_id)
            
            if not user:
                return {"message": "User not found"}, 404

            # Get the order
            order = Order.query.filter_by(id=order_id, user_id=current_user_id).first()
            if not order:
                return {"message": "Order not found or access denied"}, 404

            # Check if order can be modified
            if order.status not in ['draft', 'pending']:
                return {"message": f"Cannot modify order items with status: {order.status}"}, 400

            data = request.get_json()
            if not data:
                return {"message": "No data provided"}, 400

            action = data.get('action', 'add')  # 'add', 'remove', 'update'
            order_items_data = data.get("order_items", [])

            if action == 'add':
                # Add new items to existing order
                total_addition = Decimal('0.00')
                
                for item_data in order_items_data:
                    if 'product_id' not in item_data or 'quantity' not in item_data:
                        return {"message": "Each order item must have product_id and quantity"}, 400
                    
                    product = Product.query.get(item_data['product_id'])
                    if not product or not product.is_active:
                        return {"message": f"Product not found or inactive: {item_data['product_id']}"}, 400
                    
                    quantity = int(item_data['quantity'])
                    if quantity <= 0:
                        return {"message": "Quantity must be greater than 0"}, 400
                    
                    if product.quantity < quantity:
                        return {"message": f"Insufficient stock for product: {product.name}. Available: {product.quantity}"}, 400
                    
                    item_total = product.price * quantity
                    total_addition += item_total
                    
                    # Create new order item
                    order_item = OrderItem(
                        order_id=order.id,
                        product_id=product.id,
                        quantity=quantity,
                        unit_price=product.price,
                        total_price=item_total
                    )
                    db.session.add(order_item)
                    
                    # Update product quantity
                    product.quantity -= quantity

                # Update order total
                order.total_amount += total_addition
                
            elif action == 'remove':
                # Remove specified items
                item_ids = data.get('order_item_ids', [])
                for item_id in item_ids:
                    order_item = OrderItem.query.filter_by(id=item_id, order_id=order.id).first()
                    if order_item:
                        # Restore product quantity
                        product = Product.query.get(order_item.product_id)
                        if product:
                            product.quantity += order_item.quantity
                        
                        # Update order total
                        order.total_amount -= order_item.total_price
                        
                        # Remove item
                        db.session.delete(order_item)

            order.updated_at = datetime.utcnow()
            db.session.commit()
            
            return {
                "message": f"Order items {action}ed successfully",
                "order": order.as_dict(),
                "total_amount": float(order.total_amount)
            }, 200

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error modifying order items: {str(e)}")
            return {"error": str(e)}, 500
    @jwt_required()
    def put(self, order_id):
        """Update an existing order. Users can update their own orders, admins can update any order."""
        try:
            current_user_id = get_jwt_identity()
            user = User.query.get(current_user_id)
            
            if not user:
                return {"message": "User not found"}, 404

            # Get the order
            if user.role == UserRole.ADMIN:
                order = Order.query.get(order_id)
            else:
                order = Order.query.filter_by(id=order_id, user_id=current_user_id).first()

            if not order:
                return {"error": "Order not found"}, 404

            # Check if order can be updated
            if order.status in [OrderStatus.SHIPPED, OrderStatus.DELIVERED, OrderStatus.CANCELLED]:
                if user.role != UserRole.ADMIN:
                    return {"message": "Cannot update order in current status"}, 400

            data = request.get_json()
            if not data:
                return {"error": "No data provided"}, 400

            # Update order status (admin only)
            if "status" in data and user.role == UserRole.ADMIN:
                try:
                    new_status = OrderStatus(data["status"].lower())
                    order.status = new_status
                    if new_status in [OrderStatus.CONFIRMED, OrderStatus.PROCESSING]:
                        order.approved_by = current_user_id
                except ValueError:
                    return {"error": "Invalid status value"}, 400

            # Update other order attributes
            if "customer_name" in data:
                order.customer_name = data["customer_name"]
            
            if "customer_phone" in data:
                order.customer_phone = data["customer_phone"]
            
            if "delivery_address" in data:
                order.delivery_address = data.get("delivery_address")
            
            if "city" in data:
                order.city = data.get("city")
            
            if "pickup_point_id" in data:
                pickup_point_id = data.get("pickup_point_id")
                if pickup_point_id:
                    pickup_point = PickupPoint.query.get(pickup_point_id)
                    if not pickup_point or not pickup_point.is_active:
                        return {"error": "Invalid or inactive pickup point"}, 400
                order.pickup_point_id = pickup_point_id
            
            if "order_notes" in data:
                order.order_notes = data.get("order_notes")

            # Update the updated_at timestamp
            order.updated_at = datetime.utcnow()

            db.session.commit()
            return {"message": "Order updated successfully", "order": order.as_dict()}, 200

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating order: {str(e)}")
            return {"error": f"An error occurred: {str(e)}"}, 500

    @jwt_required()
    def delete(self, order_id):
        """Cancel an order (Users can cancel their own pending orders, admins can cancel any order)."""
        try:
            current_user_id = get_jwt_identity()
            user = User.query.get(current_user_id)
            
            if not user:
                return {"message": "User not found"}, 404

            # Get the order
            if user.role == UserRole.ADMIN:
                order = Order.query.get(order_id)
            else:
                order = Order.query.filter_by(id=order_id, user_id=current_user_id).first()

            if not order:
                return {"error": "Order not found"}, 404

            # Check if order can be cancelled
            if order.status in [OrderStatus.DELIVERED, OrderStatus.CANCELLED]:
                return {"message": "Cannot cancel order in current status"}, 400

            # Restore product quantities if order is being cancelled
            if order.status != OrderStatus.CANCELLED:
                for order_item in order.order_items:
                    product = Product.query.get(order_item.product_id)
                    if product:
                        product.quantity += order_item.quantity

            # Update order status to cancelled
            order.status = OrderStatus.CANCELLED
            order.updated_at = datetime.utcnow()

            db.session.commit()
            return {"message": "Order cancelled successfully"}, 200
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error cancelling order id {order_id}: {str(e)}", exc_info=True)
            return {"error": "An unexpected error occurred during order cancellation."}, 500


class AdminOrdersResource(Resource):
    """Resource for admins to manage all orders."""
    
    @jwt_required()
    def get(self):
        """Retrieve all orders for admin management."""
        try:
            current_user_id = get_jwt_identity()
            user = User.query.get(current_user_id)

            if not user or user.role != UserRole.ADMIN:
                return {"message": "Only admins can access this endpoint"}, 403

            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 10, type=int)
            status = request.args.get('status', type=str)
            
            # Build query
            query = Order.query
            
            # Filter by status if provided
            if status:
                try:
                    status_enum = OrderStatus(status.lower())
                    query = query.filter_by(status=status_enum)
                except ValueError:
                    return {"message": "Invalid status value"}, 400
            
            # Get all orders with pagination
            orders = query.order_by(Order.created_at.desc()).paginate(
                page=page, per_page=per_page, error_out=False
            )
            
            return {
                'orders': [order.as_dict() for order in orders.items],
                'total': orders.total,
                'pages': orders.pages,
                'current_page': orders.page
            }, 200
            
        except Exception as e:
            logger.error(f"Error fetching admin orders: {str(e)}")
            return {"message": "Error fetching orders"}, 500


class OrderStatusResource(Resource):
    """Resource for managing order status."""
    
    @jwt_required()
    def put(self, order_id):
        """Update order status (Admin only)."""
        try:
            current_user_id = get_jwt_identity()
            user = User.query.get(current_user_id)
            
            if not user or user.role != UserRole.ADMIN:
                return {"message": "Only admins can update order status"}, 403

            order = Order.query.get(order_id)
            if not order:
                return {"error": "Order not found"}, 404

            data = request.get_json()
            if not data or 'status' not in data:
                return {"error": "Status is required"}, 400

            try:
                new_status = OrderStatus(data["status"].lower())
                old_status = order.status
                order.status = new_status
                
                # Set approved_by for certain status changes
                if new_status in [OrderStatus.CONFIRMED, OrderStatus.PROCESSING] and old_status == OrderStatus.PENDING:
                    order.approved_by = current_user_id
                
                order.updated_at = datetime.utcnow()
                db.session.commit()
                
                return {
                    "message": f"Order status updated from {old_status.value} to {new_status.value}",
                    "order": order.as_dict()
                }, 200
                
            except ValueError:
                return {"error": "Invalid status value"}, 400

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating order status: {str(e)}")
            return {"error": f"An error occurred: {str(e)}"}, 500


def register_order_resources(api):
    """Registers the OrderResource routes with Flask-RESTful API."""
    api.add_resource(OrderResource, "/orders", "/orders/<string:order_id>")
    api.add_resource(AdminOrdersResource, "/admin/orders")
    api.add_resource(OrderStatusResource, "/orders/<string:order_id>/status")