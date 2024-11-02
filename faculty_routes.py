from flask import request, jsonify, send_file
from flask_restx import Namespace, Resource, fields
from database import db, User, TimeTable, Attendance, Notification, CorrectionRequest
from auth import token_required
import csv
from io import StringIO
from sqlalchemy import func, case
from datetime import datetime, timedelta
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
import io

faculty_ns = Namespace('faculty', description='Faculty operations')

# Define the models for request bodies
timetable_model = faculty_ns.model('Timetable', {
    'timetable_user_id': fields.String(required=True, description='User ID of the student for whom the timetable is being entered'),
    'day': fields.String(required=True, description='Day of the week'),
    'period': fields.String(required=True, description='Period name'),
    'start_time': fields.String(required=True, description='Start time of the class'),
    'end_time': fields.String(required=True, description='End time of the class'),
    'block_name': fields.String(required=True, description='Block name'),
    'wifi_name': fields.String(required=True, description='Wi-Fi name')
})

update_attendance_model = faculty_ns.model('UpdateAttendance', {
    'attendance_id': fields.String(required=True, description='Attendance ID to update'),
    'new_status': fields.String(required=True, description='New status for attendance (present, absent, late)')
})

notification_model = faculty_ns.model('Notification', {
    'notification_id': fields.String(required=True, description='Notification ID to mark as read')
})

@faculty_ns.route('/enter_timetable')
class EnterTimetable(Resource):
    @faculty_ns.expect(timetable_model)  # Expecting the timetable model
    @token_required
    def post(self, current_user):
        """Enters a new timetable for a student."""
        try:
            data = request.get_json()
            timetable_user_id = data.get('timetable_user_id')
            day = data.get('day', '').lower()
            period = data.get('period')
            start_time = data.get('start_time')
            end_time = data.get('end_time')
            block_name = data.get('block_name')
            wifi_name = data.get('wifi_name')

            if not all([timetable_user_id, day, period, start_time, end_time, wifi_name]):
                return {'status': 'error', 'message': 'All fields are required.'}, 400

            faculty = User.query.filter_by(user_id=current_user, role='faculty').first()
            if not faculty:
                return {'status': 'error', 'message': 'Only faculty can enter timetable.'}, 403

            new_timetable = TimeTable(
                user_id=timetable_user_id,
                day=day,
                period=period,
                start_time=start_time,
                end_time=end_time,
                block_name=block_name,
                wifi_name=wifi_name
            )
            db.session.add(new_timetable)
            db.session.commit()

            return {'status': 'success', 'message': 'Timetable entered successfully.'}, 201

        except Exception as e:
            db.session.rollback()
            return {'status': 'error', 'message': str(e)}, 500

@faculty_ns.route('/attendance_statistics')
class AttendanceStatistics(Resource):
    @token_required
    def get(self, current_user):
        try:
            stats = db.session.query(
                TimeTable.period,
                db.func.count(db.distinct(Attendance.user_id)).label('total_students'),
    func.sum(case([(Attendance.status == 'present', 1)], else_=0)).label('present_count')
            ).outerjoin(Attendance, (TimeTable.user_id == Attendance.user_id) & (TimeTable.period == Attendance.period)
            ).filter(TimeTable.user_id == current_user
            ).group_by(TimeTable.period).all()
            
            return {"status": "success", "data": [{'period': s.period, 'total_students': s.total_students, 'present_count': s.present_count} for s in stats]}, 200
        except Exception as e:
            return {"status": "error", "message": str(e)}, 500

@faculty_ns.route('/student_analytics')
class StudentAnalytics(Resource):
    @token_required
    def get(self, current_user):
        """Retrieves analytics for students."""
        try:
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 10, type=int)
            sort_by = request.args.get('sort_by', 'attendance_percentage')
            order = request.args.get('order', 'desc')
            search = request.args.get('search', '')
            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')

            query = db.session.query(
                User.user_id,
                User.name,
                func.count(Attendance.id).label('total_classes'),
                func.sum(case([(Attendance.status == 'present', 1)], else_=0)).label('attended_classes')
            ).outerjoin(Attendance, User.user_id == Attendance.user_id
            ).filter(User.role == 'student')

            if search:
                query = query.filter(User.name.ilike(f'%{search}%'))

            if start_date:
                query = query.filter(Attendance.check_in_time >= start_date)
            if end_date:
                query = query.filter(Attendance.check_in_time <= end_date)

            query = query.group_by(User.user_id)

            if sort_by == 'attendance_percentage':
                order_column = func.cast(func.sum(case([(Attendance.status == 'present', 1)], else_=0)), db.Float) / func.cast(func.count(Attendance.id), db.Float)
            elif sort_by == 'name':
                order_column = User.name
            else:
                order_column = User.user_id

            if order == 'desc':
                query = query.order_by(order_column.desc())
            else:
                query = query.order_by(order_column.asc())

            pagination = query.paginate(page=page, per_page=per_page, error_out=False)
            students = pagination.items

            analytics = []
            for student in students:
                attendance_percentage = (student.attended_classes / student.total_classes * 100) if student.total_classes > 0 else 0
                zone = 'green' if attendance_percentage >= 75 else 'yellow' if attendance_percentage >= 65 else 'red'
                analytics.append({
                    'user_id': student.user_id,
                    'name': student.name,
                    'attendance_percentage': round(attendance_percentage, 2),
                    'zone': zone
                })

            return {
                'status': 'success', 
                'data': analytics,
                'page': page,
                'per_page': per_page,
                'total_pages': pagination.pages,
                'total_students': pagination.total
            }, 200
        except Exception as e:
            return {'status': 'error', 'message': str(e)}, 500

@faculty_ns.route('/overall_analytics')
class OverallAnalytics(Resource):
    @token_required
    def get(self, current_user):
        try:
            # Overall statistics
            total_students = db.session.query(func.count(User.user_id)).filter(User.role == 'student').scalar()
            total_classes = db.session.query(func.count(Attendance.id)).scalar()
            total_present = db.session.query(func.count(Attendance.id)).filter(Attendance.status == 'present').scalar()
            average_attendance = (total_present / total_classes * 100) if total_classes > 0 else 0

            # Attendance trend over last 30 days
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            daily_attendance = db.session.query(
                func.date(Attendance.check_in_time).label('date'),
                func.count(Attendance.id).label('total'),
                func.sum(case([(Attendance.status == 'present', 1)], else_=0)).label('present')
            ).filter(Attendance.check_in_time.between(start_date, end_date)
            ).group_by(func.date(Attendance.check_in_time)).all()
            attendance_trend = [{
                'date': day.date.strftime('%Y-%m-%d'),
                'attendance_rate': (day.present / day.total * 100) if day.total > 0 else 0
            } for day in daily_attendance]

            # Distribution of attendance zones
            zone_distribution = db.session.query(
                func.case(
                    (func.sum(case((Attendance.status == 'present', 1), else_=0)) * 100 / func.count(Attendance.id) >= 75, 'green'),
                    (func.sum(case((Attendance.status == 'present', 1), else_=0)) * 100 / func.count(Attendance.id) >= 65, 'yellow'),
                    else_='red'
                ).label('zone'),                func.count(User.user_id).label('count')
            ).join(Attendance, User.user_id == Attendance.user_id
            ).filter(User.role == 'student'
            ).group_by(User.user_id
            ).group_by('zone').all()

            zone_data = {zone.zone: zone.count for zone in zone_distribution}

            return {
                'status': 'success',
                'data': {
                    'total_students': total_students,
                    'total_classes': total_classes,
                    'average_attendance': round(average_attendance, 2),
                    'attendance_trend': attendance_trend,
                    'zone_distribution': zone_data
                }
            }, 200
        except Exception as e:
            return {'status': 'error', 'message': str(e)}, 500

@faculty_ns.route('/update_attendance')
class UpdateAttendance(Resource):
    @faculty_ns.expect(update_attendance_model)  # Expecting the update attendance model
    @token_required
    def post(self, current_user):
        """Updates the attendance status for a specific record."""
        try:
            data = request.get_json()
            attendance_id = data.get('attendance_id')
            new_status = data.get('new_status')
            
            if new_status not in ['present', 'absent', 'late']:
                return {'status': 'error', 'message': 'Invalid status'}, 400
            
            attendance = Attendance.query.get(attendance_id)
            if not attendance:
                return {'status': 'error', 'message': 'Attendance record not found'}, 404
            
            attendance.status = new_status
            db.session.commit()
            return {'status': 'success', 'message': 'Attendance updated successfully'}, 200
        except Exception as e:
            db.session.rollback()
            return {'status': 'error', 'message': str(e)}, 500

@faculty_ns.route('/pending_requests')
class PendingRequests(Resource):
    @token_required
    def get(self, current_user):
        """Retrieves pending correction requests."""
        try:
            faculty = User.query.filter_by(user_id=current_user, role='faculty').first()
            if not faculty:
                return {'status': 'error', 'message': 'Access denied'}, 403

            pending_requests = CorrectionRequest.query.filter_by(status='pending').all()

            requests_data = [{
                'id': req.id,
                'user_id': req.user_id,
                'attendance_id': req.attendance_id,
                'reason': req.reason,
                'created_at': req.created_at.isoformat()
            } for req in pending_requests]

            return {'status': 'success', 'data': requests_data}, 200

        except Exception as e:
            return {'status': 'error', 'message': str(e)}, 500

@faculty_ns.route('/students_by_attendance')
class StudentsByAttendance(Resource):
    @token_required
    def get(self, current_user):
        try:
            percentage = request.args.get('percentage', type=float)
            if percentage is None:
                return {'status': 'error', 'message': 'Percentage parameter is required'}, 400
            
            students = db.session.query(
                User.user_id,
                User.name,
                db.func.count(Attendance.id).label('total_classes'),
                func.sum(case([(Attendance.status == 'present', 1)], else_=0))
.label('attended_classes')
            ).join(Attendance, User.user_id == Attendance.user_id
            ).filter(User.role == 'student'
            ).group_by(User.user_id
            ).having(db.func.sum(db.case((Attendance.status == 'present', 1), else_=0))
 * 100 / db.func.count(Attendance.id) <= percentage
            ).all()

            result = [{
                'user_id': s.user_id,
                'name': s.name,
                'attendance_percentage': round((s.attended_classes / s.total_classes * 100), 2) if s.total_classes > 0 else 0
            } for s in students]
            
            return {'status': 'success', 'data': result}, 200
        except Exception as e:
            return {'status': 'error', 'message': str(e)}, 500

@faculty_ns.route('/detained_students')
class DetainedStudents(Resource):
    @token_required
    def get(self, current_user):
        """Retrieves a list of detained students based on attendance."""
        try:
            print("Executing detained students query")  # Debug print
            detained_students = db.session.query(
                User.user_id,
                User.name,
                db.func.count(Attendance.id).label('total_classes'),
                db.func.sum(db.case((Attendance.status == 'present', 1), else_=0))
.label('attended_classes')
            ).join(Attendance, User.user_id == Attendance.user_id
            ).filter(User.role == 'student'
            ).group_by(User.user_id
            ).having(db.func.sum(db.case((Attendance.status == 'present', 1), else_=0))
 * 100 / db.func.count(Attendance.id) < 75
            ).all()

            print(f"Query result: {detained_students}")  # Debug print

            result = [{
                'user_id': s.user_id,
                'name': s.name,
                'attendance_percentage': round((s.attended_classes / s.total_classes * 100), 2) if s.total_classes > 0 else 0
            } for s in detained_students]
            
            print(f"Formatted result: {result}")  # Debug print

            return {'status': 'success', 'data': result}, 200
        except Exception as e:
            print(f"Error occurred: {str(e)}")  # Debug print
            return {'status': 'error', 'message': str(e)}, 500

@faculty_ns.route('/export_attendance')
class ExportAttendance(Resource):
    @token_required
    def get(self, current_user):
        """Exports attendance data in CSV or PDF format."""
        try:
            export_format = request.args.get('format', 'csv')
            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')

            query = db.session.query(
                User.user_id,
                User.name,
                func.count(Attendance.id).label('total_classes'),
                func.sum(case([(Attendance.status == 'present', 1)], else_=0)).label('attended_classes')
            ).join(Attendance, User.user_id == Attendance.user_id
            ).filter(User.role == 'student')

            if start_date:
                query = query.filter(Attendance.check_in_time >= start_date)
            if end_date:
                query = query.filter(Attendance.check_in_time <= end_date)

            query = query.group_by(User.user_id)
            results = query.all()

            data = [{
                'User ID': result.user_id,
                'Name': result.name,
                'Total Classes': result.total_classes,
                'Attended Classes': result.attended_classes,
                'Attendance Percentage': round((result.attended_classes / result.total_classes * 100), 2) if result.total_classes > 0 else 0
            } for result in results]

            if export_format == 'csv':
                output = StringIO()
                writer = csv.DictWriter(output, fieldnames=data[0].keys())
                writer.writeheader()
                writer.writerows(data)
                output.seek(0)
                return send_file(output, mimetype='text/csv', as_attachment=True, attachment_filename='attendance_report.csv')

            elif export_format == 'pdf':
                buffer = io.BytesIO()
                doc = SimpleDocTemplate(buffer, pagesize=letter)
                elements = []

                table_data = [list(data[0].keys())] + [list(row.values()) for row in data]
                t = Table(table_data)
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 14),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                    ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica')
                ]))
                elements.append(t)
                doc.build(elements)

                buffer.seek(0)
                return send_file(buffer, mimetype='application/pdf', as_attachment=True, attachment_filename='attendance_report.pdf')

        except Exception as e:
            return {'status': 'error', 'message': str(e)}, 500

@faculty_ns.route('/notifications')
class FacultyNotifications(Resource):
    @token_required
    def get(self, current_user):
        """Retrieves unread notifications for the faculty."""
        try:
            faculty = User.query.filter_by(user_id=current_user, role='faculty').first()
            if not faculty:
                return {'status': 'error', 'message': 'Access denied'}, 403

            notifications = Notification.query.filter_by(faculty_id=current_user, is_read=False).order_by(Notification.created_at.desc()).all()

            notifications_data = [{
                'id': notif.id,
                'student_id': notif.student_id,
                'message': notif.message,
                'created_at': notif.created_at.isoformat()
            } for notif in notifications]

            return {'status': 'success', 'notifications': notifications_data}, 200

        except Exception as e:
            return {'status': 'error', 'message': str(e)}, 500

    @faculty_ns.expect(notification_model)  # Expecting the notification model
    @token_required
    def post(self, current_user):
        """Marks a notification as read."""
        try:
            faculty = User.query.filter_by(user_id=current_user, role='faculty').first()
            if not faculty:
                return {'status': 'error', 'message': 'Access denied'}, 403

            data = request.get_json()
            notification_id = data.get('notification_id')

            if not notification_id:
                return {'status': 'error', 'message': 'Notification ID is required'}, 400

            notification = Notification.query.get(notification_id)
            if not notification or notification.faculty_id != current_user:
                return {'status': 'error', 'message': 'Notification not found'}, 404

            notification.is_read = True
            db.session.commit()

            return {'status': 'success', 'message': 'Notification marked as read'}, 200

        except Exception as e:
            db.session.rollback()
            return {'status': 'error', 'message': str(e)}, 500

@faculty_ns.route('/profile')
class FacultyProfile(Resource):
    @token_required
    def get(self, current_user):
        """Retrieves the faculty's profile information."""
        try:
            faculty = User.query.filter_by(user_id=current_user, role='faculty').first()
            if not faculty:
                return {'status': 'error', 'message': 'Faculty not found'}, 404
            
            return {
                'status': 'success',
                'data': {
                    'user_id': faculty.user_id,
                    'name': faculty.name,
                    'email': faculty.email,  # Include email
                    'department': faculty.department
                }
            }, 200
        except Exception as e:
            return {'status': 'error', 'message': str(e)}, 500

    @token_required
    def put(self, current_user):
        """Updates the faculty's profile information."""
        try:
            data = request.get_json()
            faculty = User.query.filter_by(user_id=current_user, role='faculty').first()
            if not faculty:
                return {'status': 'error', 'message': 'Faculty not found'}, 404
            
            # Update fields if provided
            faculty.name = data.get('name', faculty.name)
            faculty.email = data.get('email', faculty.email)  # Update email
            faculty.department = data.get('department', faculty.department)

            db.session.commit()
            return {'status': 'success', 'message': 'Profile updated successfully'}, 200
        except Exception as e:
            db.session.rollback()
            return {'status': 'error', 'message': str(e)}, 500

@faculty_ns.route('/view_timetable')
class ViewTimetable(Resource):
    @token_required
    def get(self, current_user):
        try:
            timetable = TimeTable.query.filter_by(user_id=current_user).order_by(
                db.case(
                    {'monday': 1, 'tuesday': 2, 'wednesday': 3, 'thursday': 4, 'friday': 5},
                    value=TimeTable.day
                ),
                TimeTable.start_time
            ).all()

            timetable_data = [{
                'day': entry.day,
                'period': entry.period,
                'start_time': entry.start_time,
                'end_time': entry.end_time,
                'block_name': entry.block_name,
                'wifi_name': entry.wifi_name
            } for entry in timetable]

            return {'status': 'success', 'data': timetable_data}, 200
        except Exception as e:
            return {'status': 'error', 'message': str(e)}, 500
