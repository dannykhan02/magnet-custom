import json
from flask import request, jsonify
from flask_restful import Resource
from datetime import datetime
from model import db, Product, User, UserRole, Category
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from decimal import Decimal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ProductResource(Resource):
    
    def get(self, product_id=None):
        """Retrieve a product by ID or return all products if no ID is provided."""
        if product_id:
            try:
                product = Product.query.get(product_id)
                if product:
                    return product.as_dict(), 200
                return {"message": "Product not found"}, 404
            except (OperationalError, SQLAlchemyError) as e:
                logger.error(f"Database error: {str(e)}")
                return {"message": "Database connection error"}, 500
        
        # Get query parameters for pagination and filtering
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        category_id = request.args.get('category_id', type=str)
        is_active = request.args.get('is_active', True, type=bool)
        
        try:
            # Build query with filters
            query = Product.query
            
            if category_id:
                query = query.filter_by(category_id=category_id)
            
            if is_active is not None:
                query = query.filter_by(is_active=is_active)
            
            # Order by created_at descending
            query = query.order_by(Product.created_at.desc())
            
            # Get products with pagination
            products = query.paginate(page=page, per_page=per_page, error_out=False)
            
            if not products.items:
                return {
                    'products': [],
                    'total': 0,
                    'pages': 0,
                    'current_page': page
                }
            
            return {
                'products': [product.as_dict() for product in products.items],
                'total': products.total,
                'pages': products.pages,
                'current_page': products.page
            }, 200
            
        except (OperationalError, SQLAlchemyError) as e:
            logger.error(f"Database error: {str(e)}")
            return {"message": "Database connection error"}, 500
        except Exception as e:
            logger.error(f"Error fetching products: {str(e)}")
            return {"message": "Error fetching products"}, 500

    # @jwt_required()
    def post(self):
        """Create a new product (Only admins can create products)."""
        try:
            # identity = get_jwt_identity()
            # user = User.query.get(identity)
            
            # if not user or user.role != UserRole.ADMIN:
            #     return {"message": "Only admins can create products"}, 403

            data = request.get_json()
            if not data:
                return {"message": "No data provided"}, 400

            # Validate required fields
            required_fields = ["name", "price", "quantity"]
            for field in required_fields:
                if field not in data:
                    return {"message": f"Missing field: {field}"}, 400

            # Validate price
            try:
                price = Decimal(str(data["price"]))
                if price < 0:
                    return {"message": "Price cannot be negative"}, 400
            except (ValueError, TypeError):
                return {"message": "Invalid price format"}, 400

            # Validate quantity
            try:
                quantity = int(data["quantity"])
                if quantity < 0:
                    return {"message": "Quantity cannot be negative"}, 400
            except (ValueError, TypeError):
                return {"message": "Invalid quantity format"}, 400

            # Get category_id if provided
            category_id = data.get('category_id')
            if category_id:
                category = Category.query.get(category_id)
                if not category:
                    return {"message": "Invalid category ID"}, 400

            # Create Product instance
            product = Product(
                name=data["name"],
                description=data.get("description"),
                price=price,
                quantity=quantity,
                image_url=data.get("image_url"),
                category_id=category_id,
                created_by=user.id,
                is_active=data.get('is_active', True)
            )

            db.session.add(product)
            db.session.commit()
            
            return {
                "message": "Product created successfully", 
                "product": product.as_dict(), 
                "id": product.id
            }, 201

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating product: {str(e)}")
            return {"error": str(e)}, 500

    @jwt_required()
    def put(self, product_id):
        """Update an existing product. Only admins can update products."""
        try:
            identity = get_jwt_identity()
            user = User.query.get(identity)
            
            if not user or user.role != UserRole.ADMIN:
                return {"message": "Only admins can update products"}, 403

            product = Product.query.get(product_id)
            if not product:
                return {"error": "Product not found"}, 404

            data = request.get_json()
            if not data:
                return {"error": "No data provided"}, 400

            # Update product attributes
            if "name" in data:
                product.name = data["name"]
            
            if "description" in data:
                product.description = data.get("description")
            
            if "price" in data:
                try:
                    price = Decimal(str(data["price"]))
                    if price < 0:
                        return {"error": "Price cannot be negative"}, 400
                    product.price = price
                except (ValueError, TypeError):
                    return {"error": "Invalid price format"}, 400
            
            if "quantity" in data:
                try:
                    quantity = int(data["quantity"])
                    if quantity < 0:
                        return {"error": "Quantity cannot be negative"}, 400
                    product.quantity = quantity
                except (ValueError, TypeError):
                    return {"error": "Invalid quantity format"}, 400
            
            if "image_url" in data:
                product.image_url = data["image_url"]
            
            if "category_id" in data:
                category_id = data["category_id"]
                if category_id:
                    category = Category.query.get(category_id)
                    if not category:
                        return {"error": "Invalid category ID"}, 400
                product.category_id = category_id
            
            if "is_active" in data:
                product.is_active = bool(data["is_active"])

            # Update the updated_at timestamp
            product.updated_at = datetime.utcnow()

            db.session.commit()
            return {"message": "Product updated successfully", "product": product.as_dict()}, 200

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating product: {str(e)}")
            return {"error": f"An error occurred: {str(e)}"}, 500

    @jwt_required()
    def delete(self, product_id):
        """Delete a product (Only admins can delete products)."""
        try:
            identity = get_jwt_identity()
            user = User.query.get(identity)
            
            if not user or user.role != UserRole.ADMIN:
                return {"message": "Only admins can delete products"}, 403

            product = Product.query.get(product_id)
            if not product:
                return {"error": "Product not found"}, 404

            db.session.delete(product)
            db.session.commit()
            return {"message": "Product deleted successfully"}, 200
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting product id {product_id}: {str(e)}", exc_info=True)
            return {"error": "An unexpected error occurred during product deletion."}, 500


class ProductCategoryResource(Resource):
    """Resource for handling product categories."""
    
    def get(self):
        """Get all product categories"""
        try:
            categories = Category.query.filter_by(is_active=True).all()
            return {
                'categories': [category.as_dict() for category in categories]
            }, 200
        except Exception as e:
            logger.error(f"Error fetching categories: {str(e)}")
            return {"message": "Error fetching categories"}, 500

    @jwt_required()
    def post(self):
        """Create a new product category (Admin only)"""
        try:
            current_user = User.query.get(get_jwt_identity())
            if not current_user or current_user.role != UserRole.ADMIN:
                return {"message": "Only admins can create categories"}, 403

            data = request.get_json()
            if not data or 'name' not in data:
                return {"message": "Category name is required"}, 400

            # Check if category already exists
            existing_category = Category.query.filter_by(name=data['name']).first()
            if existing_category:
                return {"message": "Category with this name already exists"}, 400

            category = Category(
                name=data['name'],
                description=data.get('description'),
                is_active=data.get('is_active', True)
            )
            
            db.session.add(category)
            db.session.commit()
            return {"message": "Category created successfully", "category": category.as_dict()}, 201
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating category: {str(e)}")
            return {"message": str(e)}, 400


class AdminProductsResource(Resource):
    """Resource for admins to manage all products."""
    
    @jwt_required()
    def get(self):
        """Retrieve all products for admin management (including inactive ones)."""
        try:
            current_user_id = get_jwt_identity()
            user = User.query.get(current_user_id)

            if not user or user.role != UserRole.ADMIN:
                return {"message": "Only admins can access this endpoint"}, 403

            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 10, type=int)
            
            # Get all products (including inactive ones) with pagination
            products = Product.query.order_by(Product.created_at.desc()).paginate(
                page=page, per_page=per_page, error_out=False
            )
            
            return {
                'products': [product.as_dict() for product in products.items],
                'total': products.total,
                'pages': products.pages,
                'current_page': products.page
            }, 200
            
        except Exception as e:
            logger.error(f"Error fetching admin products: {str(e)}")
            return {"message": "Error fetching products"}, 500


def register_product_resources(api):
    """Registers the ProductResource routes with Flask-RESTful API."""
    api.add_resource(ProductResource, "/products", "/products/<string:product_id>")
    api.add_resource(ProductCategoryResource, "/product-categories")
    api.add_resource(AdminProductsResource, "/admin/products")