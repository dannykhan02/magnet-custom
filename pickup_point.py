import json
from flask import request, jsonify
from flask_restful import Resource
from datetime import datetime
from model import db, PickupPoint, User, UserRole # Ensure PickupPoint, User, UserRole are correctly imported
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging
from sqlalchemy.exc import OperationalError, SQLAlchemyError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PickupPointResource(Resource):

    def get(self, pickup_point_id=None):
        """Retrieve a pickup point by ID or return all pickup points if no ID is provided."""
        if pickup_point_id:
            try:
                pickup_point = PickupPoint.query.get(pickup_point_id)
                if pickup_point:
                    return pickup_point.as_dict(), 200
                return {"message": "Pickup point not found"}, 404
            except (OperationalError, SQLAlchemyError) as e:
                logger.error(f"Database error: {str(e)}")
                return {"message": "Database connection error"}, 500

        # Get query parameters for pagination and filtering
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        city = request.args.get('city', type=str)
        is_active = request.args.get('is_active', True, type=lambda x: x.lower() == 'true') # Handle boolean from query string
        
        # New filters for GET: delivery_method, is_doorstep
        delivery_method = request.args.get('delivery_method', type=str)
        is_doorstep = request.args.get('is_doorstep', type=lambda x: x.lower() == 'true') # Handle boolean from query string

        try:
            # Build query with filters
            query = PickupPoint.query

            if city:
                query = query.filter(PickupPoint.city.ilike(f'%{city}%'))

            if is_active is not None:
                query = query.filter_by(is_active=is_active)

            # Apply new filters
            if delivery_method:
                query = query.filter(PickupPoint.delivery_method.ilike(f'%{delivery_method}%'))

            if is_doorstep is not None:
                query = query.filter_by(is_doorstep=is_doorstep)

            # Order by created_at descending
            query = query.order_by(PickupPoint.created_at.desc())

            # Get pickup points with pagination
            pickup_points = query.paginate(page=page, per_page=per_page, error_out=False)

            if not pickup_points.items:
                return {
                    'pickup_points': [],
                    'total': 0,
                    'pages': 0,
                    'current_page': page
                }, 200 # Return 200 with empty list if no items, rather than 404 for a collection

            return {
                'pickup_points': [pickup_point.as_dict() for pickup_point in pickup_points.items],
                'total': pickup_points.total,
                'pages': pickup_points.pages,
                'current_page': pickup_points.page
            }, 200

        except (OperationalError, SQLAlchemyError) as e:
            logger.error(f"Database error: {str(e)}")
            return {"message": "Database connection error"}, 500
        except Exception as e:
            logger.error(f"Error fetching pickup points: {str(e)}")
            return {"message": "Error fetching pickup points"}, 500

    @jwt_required()
    def post(self):
        """Create a new pickup point (Only admins can create pickup points)."""
        try:
            identity = get_jwt_identity()
            user = User.query.get(identity)

            if not user or user.role != UserRole.ADMIN:
                return {"message": "Only admins can create pickup points"}, 403

            data = request.get_json()
            if not data:
                return {"message": "No data provided"}, 400

            # Validate required fields (including new ones)
            required_fields = ["name", "cost", "delivery_method"]
            for field in required_fields:
                if field not in data:
                    return {"message": f"Missing required field: {field}"}, 400

            # Basic type validation for cost
            try:
                cost_value = float(data["cost"])
            except (ValueError, TypeError):
                return {"message": "Cost must be a valid number."}, 400

            # Check if pickup point with same name already exists
            existing_pickup_point = PickupPoint.query.filter_by(name=data["name"]).first()
            if existing_pickup_point:
                return {"message": "Pickup point with this name already exists"}, 400

            # Create PickupPoint instance with all new fields
            pickup_point = PickupPoint(
                name=data["name"],
                location_details=data.get("location_details"),
                city=data.get("city"),
                is_active=data.get('is_active', True),
                cost=cost_value,
                phone_number=data.get("phone_number"),
                is_doorstep=data.get('is_doorstep', False), # Default to False if not provided
                delivery_method=data["delivery_method"],
                contact_person=data.get("contact_person") # <--- Explicitly getting contact_person for POST
            )

            db.session.add(pickup_point)
            db.session.commit()

            return {
                "message": "Pickup point created successfully",
                "pickup_point": pickup_point.as_dict(),
                "id": pickup_point.id
            }, 201

        except (OperationalError, SQLAlchemyError) as e:
            db.session.rollback()
            logger.error(f"Database error during pickup point creation: {str(e)}")
            return {"message": "Database connection error or operation failed"}, 500
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating pickup point: {str(e)}", exc_info=True)
            return {"error": f"An unexpected error occurred: {str(e)}"}, 500

    @jwt_required()
    def put(self, pickup_point_id):
        """Update an existing pickup point. Only admins can update pickup points."""
        try:
            identity = get_jwt_identity()
            user = User.query.get(identity)

            if not user or user.role != UserRole.ADMIN:
                return {"message": "Only admins can update pickup points"}, 403

            pickup_point = PickupPoint.query.get(pickup_point_id)
            if not pickup_point:
                return {"error": "Pickup point not found"}, 404

            data = request.get_json()
            if not data:
                return {"error": "No data provided"}, 400

            # Check if name is being updated and if it already exists
            if "name" in data and data["name"] != pickup_point.name:
                existing_pickup_point = PickupPoint.query.filter_by(name=data["name"]).first()
                if existing_pickup_point and existing_pickup_point.id != pickup_point.id: # Ensure it's not the same point
                    return {"error": "Pickup point with this name already exists"}, 400

            # Update pickup point attributes
            if "name" in data:
                pickup_point.name = data["name"]

            if "location_details" in data:
                pickup_point.location_details = data.get("location_details") # Use data.get for nullable fields

            if "city" in data:
                pickup_point.city = data.get("city") # Use data.get for nullable fields

            if "is_active" in data:
                pickup_point.is_active = bool(data["is_active"])

            # Update new fields
            if "cost" in data:
                try:
                    pickup_point.cost = float(data["cost"])
                except (ValueError, TypeError):
                    return {"message": "Cost must be a valid number."}, 400

            if "phone_number" in data:
                pickup_point.phone_number = data.get("phone_number") # Use data.get as it's nullable

            if "is_doorstep" in data:
                pickup_point.is_doorstep = bool(data["is_doorstep"])

            if "delivery_method" in data:
                pickup_point.delivery_method = data["delivery_method"]
            
            if "contact_person" in data: # <--- Explicitly getting contact_person for PUT
                pickup_point.contact_person = data.get("contact_person") # Use data.get as it's nullable


            # Update the updated timestamp (already there, but good to ensure it's explicitly set if needed)
            pickup_point.updated = datetime.utcnow()

            db.session.commit()
            return {"message": "Pickup point updated successfully", "pickup_point": pickup_point.as_dict()}, 200

        except (OperationalError, SQLAlchemyError) as e:
            db.session.rollback()
            logger.error(f"Database error during pickup point update: {str(e)}")
            return {"message": "Database connection error or operation failed"}, 500
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating pickup point: {str(e)}", exc_info=True)
            return {"error": f"An unexpected error occurred: {str(e)}"}, 500

    @jwt_required()
    def delete(self, pickup_point_id):
        """Delete a pickup point (Only admins can delete pickup points)."""
        try:
            identity = get_jwt_identity()
            user = User.query.get(identity)

            if not user or user.role != UserRole.ADMIN:
                return {"message": "Only admins can delete pickup points"}, 403

            pickup_point = PickupPoint.query.get(pickup_point_id)
            if not pickup_point:
                return {"error": "Pickup point not found"}, 404

            # Check if pickup point has associated orders
            if pickup_point.orders:
                return {"message": "Cannot delete pickup point with associated orders. Consider deactivating instead."}, 400

            db.session.delete(pickup_point)
            db.session.commit()
            return {"message": "Pickup point deleted successfully"}, 200

        except (OperationalError, SQLAlchemyError) as e:
            db.session.rollback()
            logger.error(f"Database error during pickup point deletion: {str(e)}")
            return {"message": "Database connection error or operation failed."}, 500
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting pickup point id {pickup_point_id}: {str(e)}", exc_info=True)
            return {"error": "An unexpected error occurred during pickup point deletion."}, 500


class PickupPointByCityResource(Resource):
    """Resource for getting pickup points filtered by city."""

    def get(self, county):
        """Get all active pickup points in a specific county."""
        try:
            pickup_points = PickupPoint.query.filter(
                PickupPoint.county.ilike(f'%{county}%'), # Changed 'city' to 'county'
                PickupPoint.is_active == True
            ).order_by(PickupPoint.name.asc()).all()

            # If PickupPoint model's as_dict() method includes postalCode,
            # you might need to adjust as_dict() or filter it out here
            # if it's strictly not to be returned for pickup points.
            # For now, assuming as_dict() only returns relevant data.
            return {
                'pickup_points': [pickup_point.as_dict() for pickup_point in pickup_points],
                'county': county, # Changed 'city' to 'county'
                'total': len(pickup_points)
            }, 200

        except (OperationalError, SQLAlchemyError) as e:
            logger.error(f"Database error fetching pickup points for county {county}: {str(e)}")
            return {"message": "Database connection error or operation failed."}, 500
        except Exception as e:
            logger.error(f"Error fetching pickup points for county {county}: {str(e)}", exc_info=True)
            return {"message": "Error fetching pickup points"}, 500

class AdminPickupPointsResource(Resource):
    """Resource for admins to manage all pickup points."""

    @jwt_required()
    def get(self):
        """Retrieve all pickup points for admin management (including inactive ones)."""
        try:
            current_user_id = get_jwt_identity()
            user = User.query.get(current_user_id)

            if not user or user.role != UserRole.ADMIN:
                return {"message": "Only admins can access this endpoint"}, 403

            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 10, type=int)
            
            # Allow admin to filter by active status as well
            is_active_filter = request.args.get('is_active', type=lambda x: x.lower() == 'true' or x.lower() == 'false')

            query = PickupPoint.query
            if is_active_filter is not None:
                query = query.filter_by(is_active=is_active_filter)

            # Get all pickup points (including inactive ones) with pagination
            pickup_points = query.order_by(PickupPoint.created_at.desc()).paginate(
                page=page, per_page=per_page, error_out=False
            )

            return {
                'pickup_points': [pickup_point.as_dict() for pickup_point in pickup_points.items],
                'total': pickup_points.total,
                'pages': pickup_points.pages,
                'current_page': pickup_points.page
            }, 200

        except (OperationalError, SQLAlchemyError) as e:
            logger.error(f"Database error fetching admin pickup points: {str(e)}")
            return {"message": "Database connection error or operation failed."}, 500
        except Exception as e:
            logger.error(f"Error fetching admin pickup points: {str(e)}", exc_info=True)
            return {"message": "Error fetching pickup points"}, 500


def register_pickup_point_resources(api):
    """Registers the PickupPointResource routes with Flask-RESTful API."""
    api.add_resource(PickupPointResource, "/pickup-points", "/pickup-points/<string:pickup_point_id>")
    api.add_resource(PickupPointByCityResource, "/pickup-points/city/<string:county>")
    api.add_resource(AdminPickupPointsResource, "/admin/pickup-points")