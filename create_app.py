import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_restx import Api
from database import db, init_db
from flask_cors import CORS
import logging
from logging.handlers import RotatingFileHandler
from flask_mail import Mail
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from configuration import Config
from werkzeug.exceptions import HTTPException

limiter = Limiter(key_func=get_remote_address)

migrate = Migrate()

def create_app():
    app = Flask(__name__)
    
    app.config.from_object(Config)
    
    # Initialize the database
    init_db(app)
    
    migrate.init_app(app, db)
    CORS(app)
    Mail(app)
    limiter.init_app(app)

    # Set up logging
    if not app.debug:
        if not os.path.exists('logs'):
            os.mkdir('logs')
        file_handler = RotatingFileHandler('logs/college_attendance.log', maxBytes=10240, backupCount=10)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        
        # Also log to console
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        app.logger.addHandler(console_handler)

        app.logger.setLevel(logging.INFO)
        app.logger.info('College Attendance startup')

    api = Api(app, version='1.0', title='College Attendance API',
              description='A simple college attendance API')
    
    @app.errorhandler(Exception)
    def handle_exception(e):
        # Pass through HTTP errors
        if isinstance(e, HTTPException):
            return e

        # Now you're handling non-HTTP exceptions only
        app.logger.error(f"An error occurred: {str(e)}")
        return {"error": str(e)}, 500

    return app, api