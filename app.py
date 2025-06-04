from flask import Flask
from flask_jwt_extended import JWTManager
from flask_sqlalchemy import SQLAlchemy
from flask_session import Session
from flask_mail import Mail
from flask_restful import Api
from flask_migrate import Migrate
from config import Config
import os
from model import db  # Assuming you have a models.py file with db = SQLAlchemy()

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
Session(app)  # Initialize session after setting SESSION_SQLALCHEMY

# Register authentication blueprint


# Run the app
if __name__ == "__main__":
    app.run(debug=True)