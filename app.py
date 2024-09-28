from create_app import create_app
from database import db, init_db
from shared_routes import shared_ns
from student_routes import student_ns
from faculty_routes import faculty_ns

app, api = create_app()

api.add_namespace(shared_ns)
api.add_namespace(student_ns)
api.add_namespace(faculty_ns)

# Initialize the database
with app.app_context():
    init_db()

if __name__ == '__main__':
    app.run(debug=True)
