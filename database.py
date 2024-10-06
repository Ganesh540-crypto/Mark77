from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import click
from flask.cli import with_appcontext
import os
import subprocess
from flask import current_app

db = SQLAlchemy()
migrate = Migrate()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(64), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    year = db.Column(db.String(20))
    branch = db.Column(db.String(64))
    department = db.Column(db.String(64))
    password_hash = db.Column(db.String(128))
    reset_token = db.Column(db.String(128))
    reset_token_expiry = db.Column(db.DateTime)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(64), db.ForeignKey('user.user_id'), nullable=False)
    check_in_time = db.Column(db.DateTime)
    check_out_time = db.Column(db.DateTime)
    block_name = db.Column(db.String(64))
    period = db.Column(db.String(20))
    wifi_name = db.Column(db.String(64))
    duration = db.Column(db.Integer)
    status = db.Column(db.String(20), default='absent')

class TimeTable(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(64), db.ForeignKey('user.user_id'), nullable=False)
    day = db.Column(db.String(20))
    period = db.Column(db.String(20))
    start_time = db.Column(db.String(20))
    end_time = db.Column(db.String(20))
    block_name = db.Column(db.String(64))
    wifi_name = db.Column(db.String(64))

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    faculty_id = db.Column(db.String(64), db.ForeignKey('user.user_id'), nullable=False)
    student_id = db.Column(db.String(64), db.ForeignKey('user.user_id'), nullable=False)
    message = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)

class CorrectionRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(64), db.ForeignKey('user.user_id'), nullable=False)
    attendance_id = db.Column(db.Integer, db.ForeignKey('attendance.id'), nullable=False)
    reason = db.Column(db.String(256), nullable=False)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('correction_requests', lazy=True))
    attendance = db.relationship('Attendance', backref=db.backref('correction_requests', lazy=True))

class UserActivity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(64), db.ForeignKey('user.user_id'), nullable=False)
    activity_type = db.Column(db.String(50), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    details = db.Column(db.String(255))

    def __repr__(self):
        return f'<UserActivity {self.id}: {self.user_id} - {self.activity_type}>'

def backup_database(app):
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"backup_{timestamp}.db"
        db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
        subprocess.run(["sqlite3", db_path, f".backup {backup_file}"], check=True)
        return backup_file
    except Exception as e:
        app.logger.error(f"Database backup failed: {str(e)}")
        return None

def restore_database(app, backup_file):
    if not os.path.exists(backup_file):
        app.logger.error(f"Backup file not found: {backup_file}")
        return False
    try:
        db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
        subprocess.run(["sqlite3", db_path, f".restore {backup_file}"], check=True)
        return True
    except Exception as e:
        app.logger.error(f"Database restore failed: {str(e)}")
        return False

@click.command('init-db')
@with_appcontext
def init_db_command():
    db.create_all()
    click.echo('Initialized the database.')

@click.command('backup-db')
@with_appcontext
def backup_db_command():
    backup_file = backup_database(current_app)
    if backup_file:
        click.echo(f"Database backed up to {backup_file}")
    else:
        click.echo("Database backup failed")

@click.command('restore-db')
@click.argument('backup_file')
@with_appcontext
def restore_db_command(backup_file):
    if restore_database(current_app, backup_file):
        click.echo(f"Database restored from {backup_file}")
    else:
        click.echo("Database restore failed or backup file not found")

def init_db(app):
    if not hasattr(app, 'extensions') or 'sqlalchemy' not in app.extensions:
        db.init_app(app)
        migrate.init_app(app, db)
    
    # Register CLI commands
    app.cli.add_command(init_db_command)
    app.cli.add_command(backup_db_command)
    app.cli.add_command(restore_db_command)

    # Initialize the database if it doesn't exist
    with app.app_context():
        db.create_all()

def get_db_connection():
    return db