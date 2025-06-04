import json
from flask import request, jsonify
from flask_restful import Resource
from datetime import datetime
from model import db, PickupPoint, User, UserRole
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
        is_active = request.args.get('is_active', True, type=bool)
        
        try:
            # Build query with filters
            query = PickupPoint.query
            
            if city:
                query = query.filter(PickupPoint.city.ilike(f'%{city}%'))
            
            if is_active is not None:
                query = query.filter_by(is_active=is_active)
            
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
                }
            
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

            # Validate required fields
            required_fields = ["name"]
            for field in required_fields:
                if field not in data:
                    return {"message": f"Missing field: {field}"}, 400

            # Check if pickup point with same name already exists
            existing_pickup_point = PickupPoint.query.filter_by(name=data["name"]).first()
            if existing_pickup_point:
                return {"message": "Pickup point with this name already exists"}, 400

            # Create PickupPoint instance
            pickup_point = PickupPoint(
                name=data["name"],
                location_details=data.get("location_details"),
                city=data.get("city"),
                is_active=data.get('is_active', True)
            )

            db.session.add(pickup_point)
            db.session.commit()
            
            return {
                "message": "Pickup point created successfully", 
                "pickup_point": pickup_point.as_dict(), 
                "id": pickup_point.id
            }, 201

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating pickup point: {str(e)}")
            return {"error": str(e)}, 500

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
                if existing_pickup_point:
                    return {"error": "Pickup point with this name already exists"}, 400

            # Update pickup point attributes
            if "name" in data:
                pickup_point.name = data["name"]
            
            if "location_details" in data:
                pickup_point.location_details = data.get("location_details")
            
            if "city" in data:
                pickup_point.city = data.get("city")
            
            if "is_active" in data:
                pickup_point.is_active = bool(data["is_active"])

            # Update the updated timestamp
            pickup_point.updated = datetime.utcnow()

            db.session.commit()
            return {"message": "Pickup point updated successfully", "pickup_point": pickup_point.as_dict()}, 200

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating pickup point: {str(e)}")
            return {"error": f"An error occurred: {str(e)}"}, 500

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
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting pickup point id {pickup_point_id}: {str(e)}", exc_info=True)
            return {"error": "An unexpected error occurred during pickup point deletion."}, 500


class PickupPointByCityResource(Resource):
    """Resource for getting pickup points filtered by city."""
    
    def get(self, city):
        """Get all active pickup points in a specific city."""
        try:
            pickup_points = PickupPoint.query.filter(
                PickupPoint.city.ilike(f'%{city}%'),
                PickupPoint.is_active == True
            ).order_by(PickupPoint.name.asc()).all()
            
            return {
                'pickup_points': [pickup_point.as_dict() for pickup_point in pickup_points],
                'city': city,
                'total': len(pickup_points)
            }, 200
            
        except Exception as e:
            logger.error(f"Error fetching pickup points for city {city}: {str(e)}")
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
            
            # Get all pickup points (including inactive ones) with pagination
            pickup_points = PickupPoint.query.order_by(PickupPoint.created_at.desc()).paginate(
                page=page, per_page=per_page, error_out=False
            )
            
            return {
                'pickup_points': [pickup_point.as_dict() for pickup_point in pickup_points.items],
                'total': pickup_points.total,
                'pages': pickup_points.pages,
                'current_page': pickup_points.page
            }, 200
            
        except Exception as e:
            logger.error(f"Error fetching admin pickup points: {str(e)}")
            return {"message": "Error fetching pickup points"}, 500


def register_pickup_point_resources(api):
    """Registers the PickupPointResource routes with Flask-RESTful API."""
    api.add_resource(PickupPointResource, "/pickup-points", "/pickup-points/<string:pickup_point_id>")
    api.add_resource(PickupPointByCityResource, "/pickup-points/city/<string:city>")
    api.add_resource(AdminPickupPointsResource, "/admin/pickup-points")