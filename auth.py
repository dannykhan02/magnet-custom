from flask import Blueprint, jsonify, request, url_for, session, redirect
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity, get_jwt, jwt_required, create_access_token
from email_validator import validate_email, EmailNotValidError
import re
import phonenumbers as pn
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import uuid
from model import db, User, UserRole
from datetime import datetime, timedelta
from oauth_config import oauth
from flask_mail import Message
from config import Config
import logging
from itsdangerous import URLSafeTimedSerializer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Authentication Blueprint
auth_bp = Blueprint('auth', __name__)

def generate_token(user):
    """Generate JWT token with user claims"""
    return create_access_token(
        identity=str(user.id),
        additional_claims={
            "email": user.email,
            "role": str(user.role.value),
            "name": user.name,
            "permissions": user.permissions
        },
        expires_delta=timedelta(days=30)
    )

@auth_bp.route('/login/google')
def google_login():
    """Initiate Google OAuth login"""
    state = str(uuid.uuid4())
    nonce = str(uuid.uuid4())
    session["oauth_state"] = state
    session["oauth_nonce"] = nonce
    session.modified = True
    redirect_uri = Config.GOOGLE_REDIRECT_URI
    return oauth.google.authorize_redirect(
        redirect_uri,
        state=state,
        nonce=nonce
    )

@auth_bp.route("/callback/google")
def google_callback():
    """Handle Google OAuth callback"""
    try:
        received_state = request.args.get("state")
        stored_state = session.pop("oauth_state", None)
        stored_nonce = session.pop("oauth_nonce", None)

        if not stored_state or not received_state or stored_state != received_state:
            return jsonify({"error": "Invalid state, possible CSRF attack"}), 400

        token = oauth.google.authorize_access_token()
        user_info = oauth.google.parse_id_token(token, nonce=stored_nonce)

        email = user_info["email"]
        name = user_info.get("name", "Google User")

        user = User.query.filter_by(email=email).first()

        if not user:
            user = User(
                id=str(uuid.uuid4()),
                email=email,
                name=name,
                password=generate_password_hash(str(uuid.uuid4())),
                role=UserRole.CUSTOMER,
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.session.add(user)
            db.session.commit()

        if not user.is_active:
            return jsonify({"error": "Account is deactivated"}), 403

        access_token = generate_token(user)

        response = jsonify({
            "msg": "Login successful",
            "user": user.as_dict()
        })

        response.set_cookie(
            'access_token',
            access_token,
            httponly=True,
            secure=True,
            samesite='None',
            path='/',
            domain=None,
            max_age=30*24*60*60
        )

        frontend_callback_url = f"{Config.FRONTEND_URL}/auth/callback/google"
        return redirect(frontend_callback_url)

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in Google callback: {str(e)}")
        return jsonify({"error": str(e)}), 500

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
            user = User.query.get(user_id)

            if not user or not user.has_permission(permission):
                return jsonify({"msg": "Forbidden: Insufficient Permissions"}), 403

            return fn(*args, **kwargs)
        return wrapper
    return decorator

def is_valid_email(email: str) -> bool:
    """Validates an email address"""
    try:
        validate_email(email, check_deliverability=True)
        return True
    except EmailNotValidError:
        return False

def normalize_phone(phone: str) -> str:
    """Converts phone numbers to a standard format"""
    if not isinstance(phone, str):
        logger.warning(f"Phone number is not a string: {phone}")
        phone = str(phone)

    logger.info(f"Normalizing phone number: {phone}")
    phone = re.sub(r"\D", "", phone)

    if phone.startswith("+254"):
        phone = "0" + phone[4:]
    elif phone.startswith("254") and len(phone) == 12:
        phone = "0" + phone[3:]

    logger.info(f"Normalized phone number: {phone}")
    return phone

def is_valid_phone(phone: str, region="KE") -> bool:
    """Validates phone number format"""
    if not phone:
        return False

    phone = normalize_phone(phone)

    if len(phone) not in [9, 10]:
        logger.warning(f"Invalid length for phone number: {phone}")
        return False

    try:
        parsed_number = pn.parse(phone, region)
        if not pn.is_valid_number(parsed_number):
            logger.warning(f"Invalid phone number format: {phone}")
            return False
        return True
    except pn.phonenumberutil.NumberParseException:
        logger.warning(f"Failed to parse phone number: {phone}")
        return False

def validate_password(password: str) -> bool:
    """Password must be at least 8 characters long, contain letters and numbers"""
    return bool(re.match(r'^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d@$!%*?&]{8,}$', password))

@auth_bp.route('/register', methods=['POST'])
def register():
    """Register a new customer user"""
    data = request.get_json()

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    name = data.get("name", "").strip()
    phone = data.get("phone", "").strip() if data.get("phone") else None
    address = data.get("address", "").strip() if data.get("address") else None
    city = data.get("city", "").strip() if data.get("city") else None

    if not email or not password or not name:
        return jsonify({"msg": "Email, password, and name are required"}), 400

    if not is_valid_email(email):
        return jsonify({"msg": "Invalid email address"}), 400

    if phone and not is_valid_phone(phone):
        logger.error(f"Invalid phone number: {phone}")
        return jsonify({"msg": "Invalid phone number format"}), 400

    if not validate_password(password):
        return jsonify({"msg": "Password must be at least 8 characters long, contain letters and numbers"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"msg": "Email already registered"}), 400

    if phone and User.query.filter_by(phone=phone).first():
        return jsonify({"msg": "Phone number already registered"}), 400

    try:
        new_user = User(
            id=str(uuid.uuid4()),
            email=email,
            name=name,
            phone=normalize_phone(phone) if phone else None,
            address=address,
            city=city,
            role=UserRole.CUSTOMER,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        new_user.set_password(password)

        db.session.add(new_user)
        db.session.commit()

        return jsonify({"msg": "User registered successfully"}), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Registration error: {str(e)}")
        return jsonify({"msg": "Registration failed", "error": str(e)}), 500

@auth_bp.route('/admin/register', methods=['POST'])
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

    if not email or not password or not name:
        return jsonify({"msg": "Email, password, and name are required"}), 400

    if not is_valid_email(email):
        return jsonify({"msg": "Invalid email address"}), 400

    if phone and not is_valid_phone(phone):
        return jsonify({"msg": "Invalid phone number format"}), 400

    if not validate_password(password):
        return jsonify({"msg": "Password must be at least 8 characters long, contain letters and numbers"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"msg": "Email already registered"}), 400

    if phone and User.query.filter_by(phone=phone).first():
        return jsonify({"msg": "Phone number already registered"}), 400

    try:
        new_admin = User(
            id=str(uuid.uuid4()),
            email=email,
            name=name,
            phone=normalize_phone(phone) if phone else None,
            role=UserRole.ADMIN,
            permissions=permissions,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        new_admin.set_password(password)

        db.session.add(new_admin)
        db.session.commit()

        return jsonify({"msg": "Admin registered successfully"}), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Admin registration error: {str(e)}")
        return jsonify({"msg": "Admin registration failed", "error": str(e)}), 500

@auth_bp.route('/staff/register', methods=['POST'])
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
    city = data.get("city", "").strip() if data.get("city") else None

    if not email or not password or not name:
        return jsonify({"msg": "Email, password, and name are required"}), 400

    if not is_valid_email(email):
        return jsonify({"msg": "Invalid email address"}), 400

    if phone and not is_valid_phone(phone):
        return jsonify({"msg": "Invalid phone number format"}), 400

    if not validate_password(password):
        return jsonify({"msg": "Password must be at least 8 characters long, contain letters and numbers"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"msg": "Email already registered"}), 400

    if phone and User.query.filter_by(phone=phone).first():
        return jsonify({"msg": "Phone number already registered"}), 400

    try:
        new_staff = User(
            id=str(uuid.uuid4()),
            email=email,
            name=name,
            phone=normalize_phone(phone) if phone else None,
            address=address,
            city=city,
            role=UserRole.STAFF,
            permissions=permissions,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        new_staff.set_password(password)

        db.session.add(new_staff)
        db.session.commit()

        return jsonify({"msg": "Staff registered successfully"}), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Staff registration error: {str(e)}")
        return jsonify({"msg": "Staff registration failed", "error": str(e)}), 500

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

@auth_bp.route('/profile', methods=['GET'])
@jwt_required()
def get_profile():
    """Get user profile information"""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    if not user:
        return jsonify({"msg": "User not found"}), 404

    return jsonify(user.as_dict()), 200

@auth_bp.route('/profile', methods=['PUT'])
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

        if 'city' in data:
            user.city = data['city'].strip() if data['city'] else None

        user.updated_at = datetime.utcnow()
        db.session.commit()

        return jsonify({"msg": "Profile updated successfully", "user": user.as_dict()}), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Profile update error: {str(e)}")
        return jsonify({"msg": "Failed to update profile", "error": str(e)}), 500

@auth_bp.route('/change-password', methods=['POST'])
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

@auth_bp.route('/users', methods=['GET'])
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

@auth_bp.route('/users/<user_id>', methods=['GET'])
@jwt_required()
@role_required('ADMIN')
def get_user(user_id):
    """Get specific user details"""
    user = User.query.get(user_id)

    if not user:
        return jsonify({"msg": "User not found"}), 404

    return jsonify(user.as_dict()), 200

@auth_bp.route('/users/<user_id>/activate', methods=['PUT'])
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

@auth_bp.route('/users/<user_id>/deactivate', methods=['PUT'])
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

@auth_bp.route('/users/<user_id>/permissions', methods=['PUT'])
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

@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    """Get current authenticated user's information"""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    if not user:
        return jsonify({"msg": "User not found"}), 404

    return jsonify(user.as_dict()), 200
