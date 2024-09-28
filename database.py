from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import click
from flask.cli import with_appcontext
import os
import subprocess
from flask import current_app

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(64), nullable=False)
    role = db.Column(db.String(20), nullable=False)
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
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('correction_requests', lazy=True))
    attendance = db.relationship('Attendance', backref=db.backref('correction_requests', lazy=True))

def init_db():
    with current_app.app_context():
        db.create_all()

def backup_database(app):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"backup_{timestamp}.db"
    db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
    subprocess.run(["sqlite3", db_path, f".backup {backup_file}"])
    return backup_file

def restore_database(app, backup_file):
    if os.path.exists(backup_file):
        db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
        subprocess.run(["sqlite3", db_path, f".restore {backup_file}"])
        return True
    return False

@click.command('init-db')
@with_appcontext
def init_db_command():
    init_db(current_app)
    click.echo('Initialized the database.')

@click.command('backup-db')
@with_appcontext
def backup_db_command():
    backup_file = backup_database(current_app)
    click.echo(f"Database backed up to {backup_file}")

@click.command('restore-db')
@click.argument('backup_file')
@with_appcontext
def restore_db_command(backup_file):
    if restore_database(current_app, backup_file):
        click.echo(f"Database restored from {backup_file}")
    else:
        click.echo("Backup file not found")

def init_app(app):
    app.cli.add_command(init_db_command)
    app.cli.add_command(backup_db_command)
    app.cli.add_command(restore_db_command)
