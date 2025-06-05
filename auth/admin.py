# auth/admin.py
"""Admin user management routes"""

import uuid
import logging
from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from .utils import (
    is_valid_email, is_valid_phone, validate_password, 
    normalize_phone, create_user_dict
)
from .decorators import role_required
from model import db, User, UserRole

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin/register', methods=['POST'])
@jwt_required()
@role_required('ADMIN')
def register_admin():
    """Register a new admin user (Admin only)"""
    data = request.get_json()

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    name = data.get("name", "").strip()
    phone = data.get("phone", "").strip() if data.get("phone") else None
    permissions = data.get("permissions", "").strip() if data.get("permissions") else None

    # Validation
    if not email or not password or not name:
        return jsonify({"msg": "Email, password, and name are required"}), 400

    if not is_valid_email(email):
        return jsonify({"msg": "Invalid email address"}), 400

    if phone and not is_valid_phone(phone):
        return jsonify({"msg": "Invalid phone number format"}), 400

    if not validate_password(password):
        return jsonify({"msg": "Password must be at least 8 characters long, contain letters and numbers"}), 400

    # Check for existing users
    if User.query.filter_by(email=email).first():
        return jsonify({"msg": "Email already registered"}), 400

    if phone and User.query.filter_by(phone=phone).first():
        return jsonify({"msg": "Phone number already registered"}), 400

    try:
        user_data = create_user_dict(
            email=email,
            name=name,
            phone=phone,
            role=UserRole.ADMIN,
            permissions=permissions
        )
        new_admin = User(**user_data)
        new_admin.set_password(password)

        db.session.add(new_admin)
        db.session.commit()

        return jsonify({"msg": "Admin registered successfully"}), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Admin registration error: {str(e)}")
        return jsonify({"msg": "Admin registration failed", "error": str(e)}), 500

@admin_bp.route('/staff/register', methods=['POST'])
@jwt_required()
@role_required('ADMIN')
def register_staff():
    """Register a new staff user (Admin only)"""
    data = request.get_json()

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    name = data.get("name", "").strip()
    phone = data.get("phone", "").strip() if data.get("phone") else None
    permissions = data.get("permissions", "").strip() if data.get("permissions") else None
    address = data.get("address", "").strip() if data.get("address") else None
    county = data.get("county", "").strip() if data.get("county") else None

    # Validation
    if not email or not password or not name:
        return jsonify({"msg": "Email, password, and name are required"}), 400

    if not is_valid_email(email):
        return jsonify({"msg": "Invalid email address"}), 400

    if phone and not is_valid_phone(phone):
        return jsonify({"msg": "Invalid phone number format"}), 400

    if not validate_password(password):
        return jsonify({"msg": "Password must be at least 8 characters long, contain letters and numbers"}), 400

    # Check for existing users
    if User.query.filter_by(email=email).first():
        return jsonify({"msg": "Email already registered"}), 400

    if phone and User.query.filter_by(phone=phone).first():
        return jsonify({"msg": "Phone number already registered"}), 400

    try:
        user_data = create_user_dict(
            email=email,
            name=name,
            phone=phone,
            address=address,
            county=county,
            role=UserRole.STAFF,
            permissions=permissions
        )
        new_staff = User(**user_data)
        new_staff.set_password(password)

        db.session.add(new_staff)
        db.session.commit()

        return jsonify({"msg": "Staff registered successfully"}), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Staff registration error: {str(e)}")
        return jsonify({"msg": "Staff registration failed", "error": str(e)}), 500

@admin_bp.route('/users', methods=['GET'])
@jwt_required()
@role_required('ADMIN')
def get_users():
    """Get list of all users with optional search and filtering"""
    try:
        search_query = request.args.get('search', '').strip().lower()
        role_filter = request.args.get('role', '').strip().upper()
        is_active_filter = request.args.get('is_active', '').strip().lower()

        query = User.query

        if search_query:
            query = query.filter(
                db.or_(
                    User.name.ilike(f'%{search_query}%'),
                    User.email.ilike(f'%{search_query}%'),
                    User.phone.ilike(f'%{search_query}%')
                )
            )

        if role_filter and hasattr(UserRole, role_filter):
            query = query.filter(User.role == getattr(UserRole, role_filter))

        if is_active_filter in ['true', 'false']:
            query = query.filter(User.is_active == (is_active_filter == 'true'))

        users = query.order_by(User.created_at.desc()).all()

        result = [user.as_dict() for user in users]
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error fetching users: {str(e)}")
        return jsonify({"msg": "Failed to fetch users", "error": str(e)}), 500

@admin_bp.route('/users/<user_id>', methods=['GET'])
@jwt_required()
@role_required('ADMIN')
def get_user(user_id):
    """Get specific user details"""
    user = User.query.get(user_id)

    if not user:
        return jsonify({"msg": "User not found"}), 404

    return jsonify(user.as_dict()), 200

@admin_bp.route('/users/<user_id>/activate', methods=['PUT'])
@jwt_required()
@role_required('ADMIN')
def activate_user(user_id):
    """Activate a user account"""
    user = User.query.get(user_id)

    if not user:
        return jsonify({"msg": "User not found"}), 404

    try:
        user.is_active = True
        user.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"msg": "User activated successfully"}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error activating user: {str(e)}")
        return jsonify({"msg": "Failed to activate user"}), 500

@admin_bp.route('/users/<user_id>/deactivate', methods=['PUT'])
@jwt_required()
@role_required('ADMIN')
def deactivate_user(user_id):
    """Deactivate a user account"""
    user = User.query.get(user_id)

    if not user:
        return jsonify({"msg": "User not found"}), 404

    if user.is_admin():
        return jsonify({"msg": "Cannot deactivate admin users"}), 403

    try:
        user.is_active = False
        user.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"msg": "User deactivated successfully"}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deactivating user: {str(e)}")
        return jsonify({"msg": "Failed to deactivate user"}), 500

@admin_bp.route('/users/<user_id>/permissions', methods=['PUT'])
@jwt_required()
@role_required('ADMIN')
def update_user_permissions(user_id):
    """Update user permissions"""
    user = User.query.get(user_id)

    if not user:
        return jsonify({"msg": "User not found"}), 404

    data = request.get_json()
    permissions = data.get("permissions", "").strip()

    try:
        user.permissions = permissions if permissions else None
        user.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"msg": "User permissions updated successfully"}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating user permissions: {str(e)}")
        return jsonify({"msg": "Failed to update user permissions"}), 500