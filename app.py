from flask import Flask
from flask_jwt_extended import JWTManager
from flask_sqlalchemy import SQLAlchemy
from flask_session import Session
from flask_mail import Mail
from flask_restful import Api
from flask_migrate import Migrate
from config import Config
import os
from model import db 

from flask_cors import CORS
from auth.routes import auth_bp
from auth.admin import admin_bp
from auth.oauth import oauth_bp
from auth.profile import profile_bp 

# Import your other resource registration functions
from product import register_product_resources
from order import register_order_resources
from payment import register_payment_resources
from report import register_report_resources
from custom_image import register_custom_image_resources
from pickup_point import register_pickup_point_resources


# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)

# Set app configuration
DATABASE_URL = os.getenv("EXTERNAL_DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("EXTERNAL_DATABASE_URL environment variable is not set")

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL

db.init_app(app)
app.config['JWT_COOKIE_SECURE'] = True
app.config['JWT_TOKEN_LOCATION'] = ['cookies']
app.config['JWT_ACCESS_COOKIE_NAME'] = 'access_token'
app.config['JWT_HEADER_NAME'] = 'Authorization'
app.config['JWT_HEADER_TYPE'] = 'Bearer'
app.config['JWT_COOKIE_CSRF_PROTECT'] = False
app.config['JWT_COOKIE_SECURE'] = True
app.config['JWT_COOKIE_SAMESITE'] = "None"
app.config['SESSION_TYPE'] = 'sqlalchemy'
app.config['SESSION_SQLALCHEMY'] = db

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

CORS(app,
     origins=["http://localhost:8080"],
     supports_credentials=True,
     expose_headers=["Set-Cookie"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
     allow_headers=["Content-Type", "Authorization"])

Session(app)
api = Api(app)
jwt = JWTManager(app)


migrate = Migrate(app, db)


mail = Mail(app)




# Register authentication blueprint
app.register_blueprint(admin_bp, url_prefix="/auth")
app.register_blueprint(auth_bp, url_prefix="/auth")

app.register_blueprint(oauth_bp, url_prefix="/auth")
app.register_blueprint(profile_bp, url_prefix="/auth")



# Register resources from your other files (using Flask-RESTful Api)
register_product_resources(api)
register_order_resources(api)
register_payment_resources(api)
register_report_resources(api)
register_custom_image_resources(api)
register_pickup_point_resources(api)

# Run the app
if __name__ == "__main__":
    # This block ensures tables are created when running app.py directly
    with app.app_context():
        db.create_all()
    app.run(debug=True)