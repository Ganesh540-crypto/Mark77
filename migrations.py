
from flask_migrate import Migrate
from create_app import app
from database import get_db_connection

migrate = Migrate(app, get_db_connection())

# Run migrations using Flask-Migrate CLI commands
