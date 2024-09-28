from flask import request, jsonify, current_app, make_response
from functools import wraps
import jwt

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return {'status': 'error', 'message': 'Authorization header is missing!'}, 401
        
        try:
            # Split the header into "Bearer" and the token
            auth_type, token = auth_header.split(None, 1)
            
            if auth_type.lower() != 'bearer':
                return {'status': 'error', 'message': 'Invalid token type. Use Bearer token.'}, 401
            
            data = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = data['user_id']
        except ValueError:
            return {'status': 'error', 'message': 'Invalid token format'}, 401
        except jwt.ExpiredSignatureError:
            return {'status': 'error', 'message': 'Token has expired'}, 401
        except jwt.InvalidTokenError:
            return {'status': 'error', 'message': 'Invalid token'}, 401
        
        return f(current_user=current_user, *args, **kwargs)
    return decorated