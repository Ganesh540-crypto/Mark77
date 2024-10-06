# rate_limiter.py

from flask import request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

def rate_limit_error_handler(e):
    return jsonify(error="Rate limit exceeded", description=str(e.description)), 429

def init_rate_limiter(app):
    limiter.init_app(app)
    app.errorhandler(429)(rate_limit_error_handler)

def limit_rate(limit_string):
    return limiter.limit(limit_string)
