# auth/utils.py
"""Authentication utility functions"""

import re
import logging
import phonenumbers as pn
from email_validator import validate_email, EmailNotValidError
from werkzeug.security import generate_password_hash
from flask_jwt_extended import create_access_token
from datetime import timedelta

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

def create_user_dict(email, name, phone=None, address=None, county=None, role=None, permissions=None):
    """Create a standardized user dictionary for user creation"""
    from model import UserRole
    import uuid
    from datetime import datetime
    
    return {
        'id': str(uuid.uuid4()),
        'email': email,
        'name': name,
        'phone': normalize_phone(phone) if phone else None,
        'address': address,
        'county': county,
        'role': role or UserRole.CUSTOMER,
        'permissions': permissions,
        'is_active': True,
        'created_at': datetime.utcnow(),
        'updated_at': datetime.utcnow()
    }