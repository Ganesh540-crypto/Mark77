from database import db, User, Attendance, TimeTable, Notification
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

def seed_database():
    # Create faculty
    faculty = User(
        user_id='FAC001',
        name='Professor Smith',
        role='faculty',
        email='smith@faculty.com',
        department='CSE',
        password_hash=generate_password_hash('Faculty3@123')
    )
    db.session.add(faculty)

    # Create students
    students = [
        User(
            user_id='STU001',
            name='John Doe',
            role='student',
            email='john@student.com',
            year='3',
            branch='CSE',
            password_hash=generate_password_hash('Student1@123')
        ),
        User(
            user_id='STU002',
            name='Jane Smith',
            role='student',
            email='jane@student.com',
            year='3',
            branch='CSE',
            password_hash=generate_password_hash('Student2@123')
        ),
        User(
            user_id='STU003',
            name='Mike Johnson',
            role='student',
            email='mike@student.com',
            year='3',
            branch='CSE',
            password_hash=generate_password_hash('Student3@123')
        )
    ]
    for student in students:
        db.session.add(student)

    # Create timetable entries
    timetable_entries = [
        TimeTable(
            user_id='STU001',
            day='Monday',
            period='1',
            start_time='09:00',
            end_time='10:00',
            block_name='Block-A',
            wifi_name='Campus-Wifi'
        ),
        TimeTable(
            user_id='STU002',
            day='Monday',
            period='1',
            start_time='09:00',
            end_time='10:00',
            block_name='Block-A',
            wifi_name='Campus-Wifi'
        ),
        TimeTable(
            user_id='STU003',
            day='Monday',
            period='1',
            start_time='09:00',
            end_time='10:00',
            block_name='Block-A',
            wifi_name='Campus-Wifi'
        )
    ]
    for entry in timetable_entries:
        db.session.add(entry)

    # Create attendance records
    attendance_records = [
        Attendance(
            user_id='STU001',
            check_in_time=datetime.now(),
            check_out_time=datetime.now() + timedelta(hours=1),
            block_name='Block-A',
            period='1',
            wifi_name='Campus-Wifi',
            status='present'
        ),
        Attendance(
            user_id='STU002',
            check_in_time=datetime.now(),
            check_out_time=datetime.now() + timedelta(hours=1),
            block_name='Block-A',
            period='1',
            wifi_name='Campus-Wifi',
            status='present'
        ),
        Attendance(
            user_id='STU003',
            check_in_time=datetime.now(),
            check_out_time=datetime.now() + timedelta(hours=1),
            block_name='Block-A',
            period='1',
            wifi_name='Campus-Wifi',
            status='absent'
        )
    ]
    for record in attendance_records:
        db.session.add(record)

    # Create notifications
    notifications = [
        Notification(
            faculty_id='FAC001',
            student_id='STU001',
            message='Attendance marked for today',
            is_read=False
        ),
        Notification(
            faculty_id='FAC001',
            student_id='STU002',
            message='Attendance marked for today',
            is_read=False
        )
    ]
    for notification in notifications:
        db.session.add(notification)

    # Commit all changes
    db.session.commit()

if __name__ == '__main__':
    seed_database()
