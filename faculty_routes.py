from flask import request, jsonify, send_file
from flask_restx import Namespace, Resource
from database import db, User, TimeTable, Attendance, Notification, CorrectionRequest
from auth import token_required
import csv
from io import StringIO

faculty_ns = Namespace('faculty', description='Faculty operations')

@faculty_ns.route('/enter_timetable')
class EnterTimetable(Resource):
    @token_required
    def post(self, current_user):
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
                db.func.sum(db.case([(Attendance.status == 'present', 1)], else_=0)).label('present_count')
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
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        sort_by = request.args.get('sort_by', 'attendance_percentage')
        order = request.args.get('order', 'desc')

        try:
            query = db.session.query(
                User.user_id,
                User.name,
                db.func.count(Attendance.id).label('total_classes'),
                db.func.sum(db.case([(Attendance.status == 'present', 1)], else_=0)).label('attended_classes')
            ).outerjoin(Attendance
            ).filter(User.role == 'student'
            ).group_by(User.user_id)

            if sort_by == 'attendance_percentage':
                order_column = db.func.cast(db.func.sum(db.case([(Attendance.status == 'present', 1)], else_=0)), db.Float) / db.func.cast(db.func.count(Attendance.id), db.Float)
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
            analytics = {
                'total_students': db.session.query(User).filter(User.role == 'student').count(),
                'total_classes': db.session.query(Attendance).filter(Attendance.user_id.in_(db.session.query(User.user_id).filter(User.role == 'student'))).count(),
                'total_attendances': db.session.query(Attendance).filter(Attendance.user_id.in_(db.session.query(User.user_id).filter(User.role == 'student'))).filter(Attendance.status == 'present').count(),
                'average_attendance': round(db.session.query(Attendance).filter(Attendance.user_id.in_(db.session.query(User.user_id).filter(User.role == 'student'))).filter(Attendance.status == 'present').count() / db.session.query(User).filter(User.role == 'student').count(), 2)
            }
            
            return {'status': 'success', 'data': analytics}, 200
        except Exception as e:
            return {'status': 'error', 'message': str(e)}, 500

@faculty_ns.route('/update_attendance')
class UpdateAttendance(Resource):
    @token_required
    def post(self, current_user):
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
                db.func.sum(db.case([(Attendance.status == 'present', 1)], else_=0)).label('attended_classes')
            ).join(Attendance, User.user_id == Attendance.user_id
            ).filter(User.role == 'student'
            ).group_by(User.user_id
            ).having(db.func.sum(db.case([(Attendance.status == 'present', 1)], else_=0)) * 100 / db.func.count(Attendance.id) <= percentage
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
        try:
            print("Executing detained students query")  # Debug print
            detained_students = db.session.query(
                User.user_id,
                User.name,
                db.func.count(Attendance.id).label('total_classes'),
                db.func.sum(db.case([(Attendance.status == 'present', 1)], else_=0)).label('attended_classes')
            ).join(Attendance, User.user_id == Attendance.user_id
            ).filter(User.role == 'student'
            ).group_by(User.user_id
            ).having(db.func.sum(db.case([(Attendance.status == 'present', 1)], else_=0)) * 100 / db.func.count(Attendance.id) < 75
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
        try:
            percentage = request.args.get('percentage', type=float)
            
            if percentage:
                students = db.session.query(User, Attendance).join(Attendance, User.user_id == Attendance.user_id).filter(User.role == 'student').group_by(User.user_id).having((Attendance.attended_classes / Attendance.total_classes * 100) <= percentage).all()
            else:
                students = db.session.query(User, Attendance).join(Attendance, User.user_id == Attendance.user_id).filter(User.role == 'student').group_by(User.user_id).all()
            
            output = StringIO()
            writer = csv.writer(output)
            writer.writerow(['User ID', 'Name', 'Total Classes', 'Attended Classes', 'Attendance Percentage'])
            
            for s in students:
                attendance_percentage = round((s[1].attended_classes / s[1].total_classes * 100), 2) if s[1].total_classes > 0 else 0
                writer.writerow([s[0].user_id, s[0].name, s[1].total_classes, s[1].attended_classes, attendance_percentage])
            
            output.seek(0)
            return send_file(output, mimetype='text/csv', as_attachment=True, attachment_filename='attendance_report.csv')
        except Exception as e:
            return {'status': 'error', 'message': str(e)}, 500

@faculty_ns.route('/notifications')
class FacultyNotifications(Resource):
    @token_required
    def get(self, current_user):
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

    @token_required
    def post(self, current_user):
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