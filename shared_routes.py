from flask_restx import Namespace, Resource, fields
from flask import request, jsonify, current_app
from auth import token_required
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
from datetime import datetime, timedelta, timezone
from database import db, User, UserActivity
import secrets
from zxcvbn import zxcvbn
from create_app import limiter

shared_ns = Namespace('shared', description='Shared operations')

# Define the user model for registration
user_model = shared_ns.model('User', {
    'id': fields.String(required=True, description='User ID'),
    'name': fields.String(required=True, description='User name'),
    'role': fields.String(required=True, description='User role (student or faculty)'),
    'email': fields.String(required=True, description='User email'),
    'password': fields.String(required=True, description='User password'),
    'year': fields.String(required=False, description='Student year (required if role is student)'),
    'branch': fields.String(required=False, description='Student branch (required if role is student)'),
    'department': fields.String(required=False, description='Faculty department (required if role is faculty)')
})

# Define the login model
login_model = shared_ns.model('Login', {
    'username': fields.String(required=True, description='User ID or email'),
    'password': fields.String(required=True, description='User password')
})

# Define the forgot password model
forgot_password_model = shared_ns.model('ForgotPassword', {
    'user_id': fields.String(required=True, description='User ID for password reset')
})

# Define the reset password model
reset_password_model = shared_ns.model('ResetPassword', {
    'user_id': fields.String(required=True, description='User ID'),
    'reset_token': fields.String(required=True, description='Password reset token'),
    'new_password': fields.String(required=True, description='New password for the user')
})

@shared_ns.route('/register')
class Register(Resource):
    @shared_ns.expect(user_model)
    @shared_ns.response(201, 'User registered successfully.')
    @shared_ns.response(400, 'Error in registration.')
    def post(self):
        """Registers a new user (student or faculty)."""
        try:
            data = request.get_json()
            user_id = data.get('id')

            # Check if user_id already exists
            if User.query.filter_by(user_id=user_id).first():
                return {'status': 'error', 'message': 'User ID already exists.'}, 400

            # Proceed with the rest of the registration logic
            name = data.get('name')
            role = data.get('role', '').lower()
            email = data.get('email')
            password = data.get('password')
            year = data.get('year') if role == 'student' else None
            branch = data.get('branch') if role == 'student' else None
            department = data.get('department') if role == 'faculty' else None

            if role not in ['student', 'faculty']:
                return {'status': 'error', 'message': 'Role must be student or faculty.'}, 400

            if not is_password_valid(password):
                return {'status': 'error', 'message': 'Password does not meet complexity requirements.'}, 400

            is_strong, suggestions = is_password_strong(password)
            if not is_strong:
                return {'status': 'error', 'message': 'Password is not strong enough', 'suggestions': suggestions}, 400
            
            if role == 'student' and not all([year, branch]):
                return {'status': 'error', 'message': 'Year and branch are required for students.'}, 400
            
            if role == 'faculty' and not department:
                return {'status': 'error', 'message': 'Department is required for faculty.'}, 400
            
            if User.query.filter_by(email=email).first():
                return {'status': 'error', 'message': 'Email already registered.'}, 400
            hashed_password = generate_password_hash(password)

            new_user = User(
                user_id=user_id,
                name=name,
                role=role,
                email=email,
                year=year,
                branch=branch,
                department=department,
                password_hash=hashed_password
            )

            db.session.add(new_user)
            db.session.commit()

            log_user_activity(new_user.user_id, 'register')

            return {'status': 'success', 'message': 'User registered successfully.'}, 201

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error during registration: {str(e)}")
            return {'status': 'error', 'message': 'An unexpected error occurred.'}, 500@shared_ns.route('/login')
        
@shared_ns.route('/login')
class Login(Resource):
    @shared_ns.expect(login_model)
    @shared_ns.response(200, 'Login successful.')
    @shared_ns.response(401, 'Invalid username or password.')
    def post(self):
        """Authenticates a user and returns a JWT token."""
        try:
            data = request.get_json()
            username = data.get('username')
            password = data.get('password')

            if not username or not password:
                return {'status': 'error', 'message': 'Missing username or password'}, 400

            user = User.query.filter_by(user_id=username).first()

            if user and check_password_hash(user.password_hash, password):
                token = jwt.encode(
                    {'user_id': user.user_id, 'exp': datetime.now(timezone.utc) + timedelta(hours=24)},
                    current_app.config['SECRET_KEY'],
                    algorithm="HS256"
                )
                log_user_activity(user.user_id, 'login')
                return {'status': 'success', 'token': token}, 200
            
            return {'status': 'error', 'message': 'Invalid username or password'}, 401
        except Exception as e:
            return {'status': 'error', 'message': str(e)}, 500

@shared_ns.route('/forgot_password')
class ForgotPassword(Resource):
    @shared_ns.expect(forgot_password_model)  # Expecting the forgot password model
    @shared_ns.response(200, 'Password reset token generated successfully.')
    @shared_ns.response(404, 'User not found.')
    def post(self):
        """Generates a password reset token for the user."""
        try:
            data = request.get_json()
            user_id = data.get('user_id')

            if not user_id:
                return {'status': 'error', 'message': 'User ID is required.'}, 400

            user = User.query.filter_by(user_id=user_id).first()

            if not user:
                return {'status': 'error', 'message': 'User not found.'}, 404

            reset_token = secrets.token_urlsafe(32)
            reset_token_expiry = datetime.utcnow() + timedelta(hours=1)

            user.reset_token = reset_token
            user.reset_token_expiry = reset_token_expiry
            db.session.commit()

            return {
                'status': 'success', 
                'message': 'Password reset token generated successfully.',
                'reset_token': reset_token
            }, 200

        except Exception as e:
            db.session.rollback()
            return {'status': 'error', 'message': str(e)}, 500

@shared_ns.route('/reset_password')
class ResetPassword(Resource):
    @shared_ns.expect(reset_password_model)  # Expecting the reset password model
    @shared_ns.response(200, 'Password reset successfully.')
    @shared_ns.response(400, 'All fields are required.')
    def post(self):
        """Resets the user's password using the reset token."""
        try:
            data = request.get_json()
            user_id = data.get('user_id')
            reset_token = data.get('reset_token')
            new_password = data.get('new_password')

            if not all([user_id, reset_token, new_password]):
                return {'status': 'error', 'message': 'All fields are required.'}, 400

            user = User.query.filter_by(user_id=user_id, reset_token=reset_token).first()

            if not user or user.reset_token_expiry < datetime.utcnow():
                return {'status': 'error', 'message': 'Invalid or expired reset token.'}, 400

            user.password_hash = generate_password_hash(new_password)
            user.reset_token = None
            user.reset_token_expiry = None
            db.session.commit()

            return {'status': 'success', 'message': 'Password reset successfully.'}, 200

        except Exception as e:
            db.session.rollback()
            return {'status': 'error', 'message': str(e)}, 500

@shared_ns.route('/refresh')
class RefreshToken(Resource):
    @token_required
    def post(self, current_user):
        """Refreshes the JWT token for the authenticated user."""
        try:
            new_token = jwt.encode(
                {'user_id': current_user, 'exp': datetime.now(timezone.utc) + timedelta(hours=24)},
                current_app.config['SECRET_KEY'],
                algorithm="HS256"
            )
            return {'status': 'success', 'token': new_token}, 200
        except Exception as e:
            return {'status': 'error', 'message': str(e)}, 500

def is_password_strong(password):
    result = zxcvbn(password)
    if result['score'] < 3:
        return False, result['feedback']['suggestions']
    return True, []

def log_user_activity(user_id, activity_type, details=None):
    new_activity = UserActivity(user_id=user_id, activity_type=activity_type, details=details)
    db.session.add(new_activity)
    db.session.commit()

def is_password_valid(password):
    if len(password) < 8:
        return False
    if not any(char.isupper() for char in password):
        return False
    if not any(char.islower() for char in password):
        return False
    if not any(char.isdigit() for char in password):
        return False
    return True