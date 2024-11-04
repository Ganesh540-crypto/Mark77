from flask_migrate import Migrate
import os
from create_app import create_app
from database import db
from shared_routes import shared_ns
from student_routes import student_ns
from faculty_routes import faculty_ns

app, api = create_app()

# Add namespaces to the API
api.add_namespace(shared_ns)
api.add_namespace(student_ns)
api.add_namespace(faculty_ns)

# Set up database migration
migrate = Migrate(app, db)

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
