# auth/routes.py
"""Main authentication routes"""

import uuid
import logging
from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_mail import Message
from itsdangerous import URLSafeTimedSerializer

from .utils import (
    generate_token, is_valid_email, is_valid_phone, 
    validate_password, normalize_phone, create_user_dict
)
from .decorators import role_required
from model import db, User, UserRole
from config import Config

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/register', methods=['POST'])
def register():
    """Register a new customer user"""
    data = request.get_json()

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    name = data.get("name", "").strip() if data.get("name") else None
    phone = data.get("phone", "").strip() if data.get("phone") else None
    address = data.get("address", "").strip() if data.get("address") else None
    county = data.get("county", "").strip() if data.get("county") else None

    # Validation
    if not email or not password:
        return jsonify({"msg": "Email, password are required"}), 400

    if not is_valid_email(email):
        return jsonify({"msg": "Invalid email address"}), 400

    if phone and not is_valid_phone(phone):
        logger.error(f"Invalid phone number: {phone}")
        return jsonify({"msg": "Invalid phone number format"}), 400

    if not validate_password(password):
        return jsonify({"msg": "Password must be at least 8 characters long, contain letters and numbers"}), 400

    # Check for existing users
    if User.query.filter_by(email=email).first():
        return jsonify({"msg": "Email already registered"}), 400

    if phone and User.query.filter_by(phone=phone).first():
        return jsonify({"msg": "Phone number already registered"}), 400

    try:
        # Create user
        user_data = create_user_dict(email, name, phone, address, county)
        new_user = User(**user_data)
        new_user.set_password(password)

        db.session.add(new_user)
        db.session.commit()

        return jsonify({"msg": "User registered successfully"}), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Registration error: {str(e)}")
        return jsonify({"msg": "Registration failed", "error": str(e)}), 500

@auth_bp.route('/login', methods=['POST'])
def login():
    """Handles user authentication and token generation"""
    data = request.get_json()

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    user = User.query.filter_by(email=email).first()

    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid email or password"}), 401

    if not user.is_active:
        return jsonify({"error": "Account is deactivated"}), 403

    access_token = generate_token(user)

    response = jsonify({
        "message": "Login successful",
        "user": user.as_dict()
    })

    response.set_cookie(
        'access_token',
        access_token,
        httponly=True,
        secure=True,
        samesite='None',
        path='/',
        max_age=30*24*60*60
    )

    return response, 200

@auth_bp.route('/logout', methods=['POST'])
def logout():
    """Handles user logout by clearing the access token cookie"""
    response = jsonify({"message": "Logout successful"})
    response.set_cookie(
        'access_token',
        '',
        expires=0,
        httponly=True,
        secure=True,
        samesite='None',
        path='/'
    )
    return response, 200

@auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    """Send password reset link to user's email"""
    from app import mail

    data = request.get_json()
    email = data.get("email", "").strip().lower()

    if not email:
        return jsonify({"msg": "Email is required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"msg": "Email not found"}), 404

    if not user.is_active:
        return jsonify({"msg": "Account is deactivated"}), 403

    serializer = URLSafeTimedSerializer(Config.SECRET_KEY)
    token = serializer.dumps(email, salt="reset-password-salt")
    reset_link = f"{Config.FRONTEND_URL}/reset-password/{token}"

    try:
        msg = Message("Password Reset Request", recipients=[email])
        msg.body = f"Click the link to reset your password: {reset_link}"
        mail.send(msg)
        return jsonify({"msg": "Reset link sent to your email"}), 200
    except Exception as e:
        logger.error(f"Failed to send reset email: {str(e)}")
        return jsonify({"msg": "Failed to send reset email"}), 500

@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Reset password using token"""
    serializer = URLSafeTimedSerializer(Config.SECRET_KEY)

    try:
        email = serializer.loads(token, salt="reset-password-salt", max_age=3600)
    except Exception as e:
        logger.error(f"Token validation error: {e}")
        return jsonify({"msg": "Invalid or expired token"}), 400

    if request.method == 'GET':
        return jsonify({"msg": "Token is valid. You can now reset your password.", "email": email}), 200

    data = request.get_json()
    new_password = data.get("password", "")

    if not validate_password(new_password):
        return jsonify({"msg": "Password must be at least 8 characters long, contain letters and numbers"}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"msg": "User not found"}), 404

    try:
        user.set_password(new_password)
        user.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"msg": "Password reset successful"}), 200
    except Exception as e:
        logger.error(f"Error updating password: {e}")
        db.session.rollback()
        return jsonify({"msg": "An error occurred while updating the password"}), 500