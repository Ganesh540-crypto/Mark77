from flask.cli import FlaskGroup
from create_app import create_app
from database import db, init_app

app = create_app()
cli = FlaskGroup(create_app=create_app)

# Initialize the database CLI commands
init_app(app)

if __name__ == '__main__':
    cli()