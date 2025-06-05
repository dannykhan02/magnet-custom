# auth/decorators.py
"""Authentication decorators"""

from functools import wraps
from flask import jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity, get_jwt
import logging

logger = logging.getLogger(__name__)

def role_required(required_role):
    """Decorator to require specific user role"""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            claims = get_jwt()
            logger.debug(f"DEBUG: Claims retrieved: {claims}")

            if "role" not in claims or claims["role"].upper() != required_role.upper():
                return jsonify({"msg": "Forbidden: Access Denied"}), 403

            return fn(*args, **kwargs)
        return wrapper
    return decorator

def permission_required(permission):
    """Decorator to require specific permission"""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            user_id = get_jwt_identity()
            
            # Import here to avoid circular imports
            from model import User
            user = User.query.get(user_id)

            if not user or not user.has_permission(permission):
                return jsonify({"msg": "Forbidden: Insufficient Permissions"}), 403

            return fn(*args, **kwargs)
        return wrapper
    return decorator