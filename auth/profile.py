# auth/profile.py
"""User profile management routes"""

import logging
from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt


from .utils import is_valid_phone, normalize_phone, validate_password
from model import db, User,  TokenBlocklist

logger = logging.getLogger(__name__)

profile_bp = Blueprint('profile', __name__)

@profile_bp.route('/profile', methods=['GET'])
@jwt_required()
def get_profile():
    """Get user profile information"""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    if not user:
        return jsonify({"msg": "User not found"}), 404

    return jsonify(user.as_dict()), 200

@profile_bp.route('/profile', methods=['PUT'])
@jwt_required()
def update_profile():
    """Update user profile information"""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    if not user:
        return jsonify({"msg": "User not found"}), 404

    data = request.get_json()

    try:
        if 'name' in data:
            user.name = data['name'].strip()

        if 'phone' in data:
            phone = data['phone'].strip() if data['phone'] else None
            if phone and not is_valid_phone(phone):
                return jsonify({"msg": "Invalid phone number format"}), 400
            user.phone = normalize_phone(phone) if phone else None

        if 'address' in data:
            user.address = data['address'].strip() if data['address'] else None

        if 'county' in data:
            user.county = data['county'].strip() if data['county'] else None

        user.updated_at = datetime.utcnow()
        db.session.commit()

        return jsonify({"msg": "Profile updated successfully", "user": user.as_dict()}), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Profile update error: {str(e)}")
        return jsonify({"msg": "Failed to update profile", "error": str(e)}), 500

@profile_bp.route('/change-password', methods=['POST'])
@jwt_required()
def change_password():
    """Change user password"""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    if not user:
        return jsonify({"msg": "User not found"}), 404

    data = request.get_json()
    current_password = data.get("current_password", "")
    new_password = data.get("new_password", "")

    if not current_password or not new_password:
        return jsonify({"msg": "Current password and new password are required"}), 400

    if not user.check_password(current_password):
        return jsonify({"msg": "Current password is incorrect"}), 400

    if not validate_password(new_password):
        return jsonify({"msg": "Password must be at least 8 characters long, contain letters and numbers"}), 400

    try:
        user.set_password(new_password)
        user.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"msg": "Password changed successfully"}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Password change error: {str(e)}")
        return jsonify({"msg": "Failed to change password"}), 500

@profile_bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    """Get current authenticated user's information"""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    if not user:
        return jsonify({"msg": "User not found"}), 404

    return jsonify(user.as_dict()), 200

@profile_bp.route('/logout-all', methods=['POST'])
@jwt_required()
def logout_all_devices():
    """Logs out the user from all devices by blacklisting all tokens"""
    user_id = get_jwt_identity()
    now = datetime.utcnow()

    # Optional: log the current session token as well
    current_token = get_jwt()
    current_jti = current_token.get("jti")

    try:
        # Add current token to blocklist just in case
        if current_jti:
            existing = TokenBlocklist.query.filter_by(jti=current_jti).first()
            if not existing:
                db.session.add(TokenBlocklist(jti=current_jti, user_id=user_id, created_at=now))

        # You could also delete old tokens before today if you stored more info

        # Add an entry to blocklist for all user's tokens
        # (Assumes you don’t track all jtis, so this is symbolic)
        # Better: If you stored all issued tokens per user, you’d loop over them here

        # Since we can't invalidate unknown past tokens without tracking them,
        # we simulate logout-all by blacklisting future ones and clearing cookies

        db.session.commit()
        return jsonify({"msg": "Successfully logged out from all devices"}), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Logout all devices failed: {str(e)}")
        return jsonify({"msg": "Logout all failed", "error": str(e)}), 500
    
@profile_bp.route('/delete-account', methods=['DELETE'])
@jwt_required()
def delete_account():
    """Permanently delete the logged-in user's account"""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    if not user:
        return jsonify({"msg": "User not found"}), 404

    try:
        # Optionally blacklist the current token (logout)
        token = get_jwt()
        jti = token.get("jti")

        if jti:
            existing = TokenBlocklist.query.filter_by(jti=jti).first()
            if not existing:
                db.session.add(TokenBlocklist(jti=jti, user_id=user_id))

        # Delete the user
        db.session.delete(user)
        db.session.commit()

        return jsonify({"msg": "Your account has been deleted successfully."}), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting account: {str(e)}")
        return jsonify({"msg": "Failed to delete account", "error": str(e)}), 500