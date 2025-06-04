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


from auth import auth_bp

# Import your other resource registration functions
from product import register_product_resources
from order import register_order_resources
from payment import register_payment_resources
from report import register_report_resources
from custom_image import register_custom_image_resources
from pickup_point import register_pickup_point_resources


# Initialize Flask app
app = Flask(__name__)

# Set app configuration
app.config.from_object(Config)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'app.db')

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Ensure SESSION_SQLALCHEMY is set to use the existing db instance
app.config['SESSION_TYPE'] = 'sqlalchemy'  # Store sessions in the database
app.config['SESSION_SQLALCHEMY'] = db  # Use existing SQLAlchemy instance

# Initialize extensions
jwt = JWTManager(app)
db.init_app(app)
migrate = Migrate(app, db)
api = Api(app)

mail = Mail(app)
Session(app)  



# Register authentication blueprint
app.register_blueprint(auth_bp, url_prefix="/auth")

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