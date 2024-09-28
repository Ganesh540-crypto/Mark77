from flask import Flask
from flask_restx import Api
from database import db
from flask_cors import CORS
import os
import logging
from logging.handlers import RotatingFileHandler

def create_app():
    app = Flask(__name__)
    
    # Set the database URI
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///college_attendance.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = 'your_secret_key_here'  # Replace with a real secret key
    
    db.init_app(app)
    CORS(app)

    api = Api(app, version='1.0', title='College Attendance API',
              description='A simple college attendance API')

    # Set up logging
    if not app.debug:
        if not os.path.exists('logs'):
            os.mkdir('logs')
        file_handler = RotatingFileHandler('logs/college_attendance.log', maxBytes=10240, backupCount=10)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info('College Attendance startup')

    return app, api

app, api = create_app()
