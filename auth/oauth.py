# auth/oauth.py
"""OAuth authentication handlers"""

import uuid
import logging
from datetime import datetime
from flask import Blueprint, jsonify, request, session, redirect
from werkzeug.security import generate_password_hash

from .utils import generate_token
from .decorators import role_required
from model import db, User, UserRole
from config import Config

logger = logging.getLogger(__name__)

oauth_bp = Blueprint('oauth', __name__)

@oauth_bp.route('/login/google')
def google_login():
    """Initiate Google OAuth login"""
    from oauth_config import oauth
    
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

@oauth_bp.route("/callback/google")
def google_callback():
    """Handle Google OAuth callback"""
    from oauth_config import oauth
    
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