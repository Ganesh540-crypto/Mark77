from flask_restx import Namespace, Resource, fields
from flask import request, current_app
from datetime import datetime, timedelta
from database import db, Attendance, TimeTable, User, Notification, CorrectionRequest
from auth import token_required
from flask_mail import Mail, Message
import matplotlib.pyplot as plt
import io
import base64

student_ns = Namespace('student', description='Student operations')

# Define the models for request bodies
attendance_model = student_ns.model('Attendance', {
    'wifi_name': fields.String(required=True, description='Wi-Fi name'),
    'block_name': fields.String(required=True, description='Block name')
})

checkout_model = student_ns.model('Checkout', {
    'attendance_id': fields.String(required=True, description='Attendance ID for checkout')
})

correction_request_model = student_ns.model('CorrectionRequest', {
    'attendance_id': fields.String(required=True, description='Attendance ID'),
    'reason': fields.String(required=True, description='Reason for correction request')
})

@student_ns.route('/mark_attendance')
class MarkAttendance(Resource):
    @student_ns.expect(attendance_model)  # Expecting the attendance model
    @token_required
    def post(self, current_user):
        """Marks attendance for the student."""
        try:
            data = request.get_json()
            wifi_name = data.get('wifi_name')
            block_name = data.get('block_name')

            if not wifi_name or not block_name:
                return {'status': 'error', 'message': 'Wi-Fi name and block name are required.'}, 400

            now = datetime.now()
            day_of_week = now.strftime('%A').lower()

            period_info = TimeTable.query.filter(
                TimeTable.user_id == current_user,
                TimeTable.day == day_of_week,
                TimeTable.start_time <= now.time(),
                TimeTable.end_time >= now.time()
            ).first()

            period = period_info.period if period_info else "free_period"
            is_late = now.time() > datetime.strptime(period_info.start_time, "%H:%M").time() if period_info else False

            new_attendance = Attendance(
                user_id=current_user,
                check_in_time=now,
                block_name=block_name,
                period=period,
                wifi_name=wifi_name,
                status='present' if not is_late else 'late'
            )
            db.session.add(new_attendance)

            if is_late:
                student = User.query.filter_by(user_id=current_user).first()
                faculty = User.query.filter_by(role='faculty', department=student.department).first()
                if faculty:
                    notification = Notification(
                        faculty_id=faculty.user_id,
                        student_id=current_user,
                        message=f"Student {student.name} is late for {period} class."
                    )
                    db.session.add(notification)

            db.session.commit()
            return {'status': 'success', 'message': 'Attendance marked successfully.'}, 200

        except Exception as e:
            db.session.rollback()
            return {'status': 'error', 'message': str(e)}, 500

@student_ns.route('/checkout')
class Checkout(Resource):
    @student_ns.expect(checkout_model)  # Expecting the checkout model
    @token_required
    def post(self, current_user):
        """Checks out the student from the current attendance record."""
        try:
            attendance_record = Attendance.query.filter_by(
                user_id=current_user, 
                check_out_time=None
            ).order_by(Attendance.check_in_time.desc()).first()

            if not attendance_record:
                return {'status': 'error', 'message': 'No active check-in found.'}, 400

            check_out_time = datetime.now()
            duration = (check_out_time - attendance_record.check_in_time).total_seconds() // 60

            attendance_record.check_out_time = check_out_time
            attendance_record.duration = duration
            attendance_record.status = 'present'

            db.session.commit()
            return {'status': 'success', 'message': 'Checked out successfully.'}, 200

        except Exception as e:
            db.session.rollback()
            return {'status': 'error', 'message': str(e)}, 500

@student_ns.route('/attendance_report')
class AttendanceReport(Resource):
    @token_required
    def get(self, current_user):
        """Generates an attendance report for the student."""
        try:
            total_periods = Attendance.query.filter_by(user_id=current_user).count()
            attended_periods = Attendance.query.filter_by(user_id=current_user, status='present').count()
            attendance_percentage = (attended_periods / total_periods) * 100 if total_periods > 0 else 0

            attendance_status = 'green' if attendance_percentage >= 75 else 'yellow' if attendance_percentage >= 65 else 'red'

            weekly_report = db.session.query(
                db.func.strftime('%W', Attendance.check_in_time).label('week'),
                db.func.count().label('total_periods'),
                db.func.sum(db.case([(Attendance.status == 'present', 1)], else_=0)).label('attended_periods')
            ).filter(Attendance.user_id == current_user
            ).group_by('week'
            ).order_by(db.desc('week')
            ).limit(4).all()

            return {
                'status': 'success',
                'attendance_percentage': attendance_percentage,
                'attendance_status': attendance_status,
                'total_periods': total_periods,
                'attended_periods': attended_periods,
                'weekly_report': [{'week': w.week, 'total_periods': w.total_periods, 'attended_periods': w.attended_periods} for w in weekly_report]
            }, 200

        except Exception as e:
            return {'status': 'error', 'message': str(e)}, 500

@student_ns.route('/view_timetable')
class ViewTimetable(Resource):
    @token_required
    def get(self, current_user):
        """Views the student's timetable."""
        try:
            timetable = TimeTable.query.filter_by(user_id=current_user).order_by(
                db.case(
                    {'monday': 1, 'tuesday': 2, 'wednesday': 3, 'thursday': 4, 'friday': 5, 'saturday': 6, 'sunday': 7},
                    value=TimeTable.day
                ),
                TimeTable.start_time
            ).all()

            if not timetable:
                return {'status': 'error', 'message': 'No timetable found for this user.'}, 404

            formatted_timetable = [{
                'day': t.day,
                'period': t.period,
                'start_time': t.start_time,
                'end_time': t.end_time,
                'block_name': t.block_name,
                'wifi_name': t.wifi_name
            } for t in timetable]
            return {'status': 'success', 'timetable': formatted_timetable}, 200

        except Exception as e:
            return {'status': 'error', 'message': str(e)}, 500

@student_ns.route('/attendance_history')
class AttendanceHistory(Resource):
    @token_required
    def get(self, current_user):
        """Retrieves the attendance history for the student."""
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        try:
            attendance = Attendance.query.filter_by(user_id=current_user).order_by(
                Attendance.check_in_time.desc()
            ).paginate(page=page, per_page=per_page, error_out=False)
            
            attendance_data = [{
                'id': a.id,
                'check_in_time': a.check_in_time.isoformat() if a.check_in_time else None,
                'check_out_time': a.check_out_time.isoformat() if a.check_out_time else None,
                'block_name': a.block_name,
                'period': a.period,
                'wifi_name': a.wifi_name,
                'duration': str(a.duration) if a.duration else None,
                'status': a.status
            } for a in attendance.items]

            return {
                'status': 'success',
                'data': attendance_data,
                'page': page,
                'per_page': per_page,
                'total_pages': attendance.pages,
                'total_items': attendance.total
            }, 200
        except Exception as e:
            return {'status': 'error', 'message': str(e)}, 500

@student_ns.route('/notify_upcoming_classes')
class NotifyUpcomingClasses(Resource):
    @token_required
    def get(self, current_user):
        """Notifies the student of upcoming classes."""
        try:
            tomorrow = (datetime.now() + timedelta(days=1)).strftime('%A').lower()
            classes = TimeTable.query.filter_by(user_id=current_user, day=tomorrow).order_by(TimeTable.start_time).all()
            
            if classes:
                user = User.query.filter_by(user_id=current_user).first()
                msg = Message("Upcoming Classes", recipients=[user.email])  # Use email from User
                msg.body = f"You have {len(classes)} classes tomorrow:\n" + \
                           "\n".join([f"{c.period} at {c.start_time} in {c.block_name}" for c in classes])
                Mail(current_app).send(msg)
                
                return {"status": "success", "message": "Notification sent"}, 200
            else:
                return {"status": "info", "message": "No classes tomorrow"}, 200
        except Exception as e:
            return {'status': 'error', 'message': str(e)}, 500

@student_ns.route('/request_correction')
class RequestCorrection(Resource):
    @student_ns.expect(correction_request_model)  # Expecting the correction request model
    @token_required
    def post(self, current_user):
        """Submits a correction request for attendance."""
        try:
            data = request.get_json()
            attendance_id = data.get('attendance_id')
            reason = data.get('reason')
            
            if not attendance_id or not reason:
                return {'status': 'error', 'message': 'Attendance ID and reason are required.'}, 400

            new_request = CorrectionRequest(
                user_id=current_user,
                attendance_id=attendance_id,
                reason=reason,
                status='pending'
            )
            db.session.add(new_request)
            db.session.commit()
            
            return {"status": "success", "message": "Correction request submitted"}, 200
        except Exception as e:
            db.session.rollback()
            return {'status': 'error', 'message': str(e)}, 500

@student_ns.route('/attendance_chart')
class AttendanceChart(Resource):
    @token_required
    def get(self, current_user):
        """Generates an attendance chart for the student."""
        try:
            data = db.session.query(
                db.func.strftime('%W', Attendance.check_in_time).label('week'),
                db.func.count().label('total_classes'),
                db.func.sum(db.case([(Attendance.status == 'present', 1)], else_=0)).label('attended_classes')
            ).filter(Attendance.user_id == current_user
            ).group_by('week'
            ).order_by('week').all()
            
            weeks = [row.week for row in data]
            attendance_rate = [row.attended_classes / row.total_classes * 100 for row in data]
            
            plt.figure(figsize=(10, 5))
            plt.plot(weeks, attendance_rate, marker='o')
            plt.title('Weekly Attendance Rate')
            plt.xlabel('Week')
            plt.ylabel('Attendance Rate (%)')
            plt.ylim(0, 100)
            
            img = io.BytesIO()
            plt.savefig(img, format='png')
            img.seek(0)
            
            return {"status": "success", "chart": base64.b64encode(img.getvalue()).decode()}, 200
        except Exception as e:
            return {'status': 'error', 'message': str(e)}, 500

@student_ns.route('/profile')
class StudentProfile(Resource):
    @token_required
    def get(self, current_user):
        """Retrieves the student's profile information."""
        try:
            student = User.query.filter_by(user_id=current_user, role='student').first()
            if not student:
                return {'status': 'error', 'message': 'Student not found'}, 404
            
            return {
                'status': 'success',
                'data': {
                    'user_id': student.user_id,
                    'name': student.name,
                    'email': student.email,  # Include email
                    'year': student.year,
                    'branch': student.branch
                }
            }, 200
        except Exception as e:
            return {'status': 'error', 'message': str(e)}, 500

    @token_required
    def put(self, current_user):
        """Updates the student's profile information."""
        try:
            data = request.get_json()
            student = User.query.filter_by(user_id=current_user, role='student').first()
            if not student:
                return {'status': 'error', 'message': 'Student not found'}, 404
            
            # Update fields if provided
            student.name = data.get('name', student.name)
            student.email = data.get('email', student.email)  # Update email
            student.year = data.get('year', student.year)
            student.branch = data.get('branch', student.branch)

            db.session.commit()
            return {'status': 'success', 'message': 'Profile updated successfully'}, 200
        except Exception as e:
            db.session.rollback()
            return {'status': 'error', 'message': str(e)}, 500

@student_ns.route('/attendance_analytics')
class AttendanceAnalytics(Resource):
    @token_required
    def get(self, current_user):
        """Retrieves attendance analytics for the last 30 days."""
        try:
            # Get attendance data for the last 30 days
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            
            attendance_data = db.session.query(
                db.func.date(Attendance.check_in_time).label('date'),
                db.func.count(Attendance.id).label('total_classes'),
                db.func.sum(db.case([(Attendance.status == 'present', 1)], else_=0)).label('attended_classes')
            ).filter(
                Attendance.user_id == current_user,
                Attendance.check_in_time.between(start_date, end_date)
            ).group_by(db.func.date(Attendance.check_in_time)).all()

            dates = [data.date.strftime('%Y-%m-%d') for data in attendance_data]
            attendance_rates = [data.attended_classes / data.total_classes * 100 if data.total_classes > 0 else 0 for data in attendance_data]

            # Create a line chart
            plt.figure(figsize=(12, 6))
            plt.plot(dates, attendance_rates, marker='o')
            plt.title('Attendance Rate Over Last 30 Days')
            plt.xlabel('Date')
            plt.ylabel('Attendance Rate (%)')
            plt.ylim(0, 100)
            plt.xticks(rotation=45)
            plt.tight_layout()

            # Convert plot to base64 encoded string
            img = io.BytesIO()
            plt.savefig(img, format='png')
            img.seek(0)
            plot_url = base64.b64encode(img.getvalue()).decode()

            # Calculate overall attendance rate
            overall_attendance_rate = sum(attendance_rates) / len(attendance_rates) if attendance_rates else 0

            return {
                'status': 'success',
                'data': {
                    'overall_attendance_rate': round(overall_attendance_rate, 2),
                    'daily_attendance_rates': dict(zip(dates, attendance_rates)),
                    'attendance_chart': plot_url
                }
            }, 200

        except Exception as e:
            return {'status': 'error', 'message': str(e)}, 500

@student_ns.route('/search')
class SearchAttendance(Resource):
    @token_required
    def get(self, current_user):
        """Searches attendance records based on query parameters."""
        try:
            query = request.args.get('query', '')
            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')

            attendance_query = Attendance.query.filter(Attendance.user_id == current_user)

            if start_date:
                attendance_query = attendance_query.filter(Attendance.check_in_time >= start_date)
            if end_date:
                attendance_query = attendance_query.filter(Attendance.check_in_time <= end_date)

            if query:
                attendance_query = attendance_query.filter(
                    db.or_(
                        Attendance.period.ilike(f'%{query}%'),
                        Attendance.block_name.ilike(f'%{query}%'),
                        Attendance.status.ilike(f'%{query}%')
                    )
                )

            results = attendance_query.order_by(Attendance.check_in_time.desc()).limit(50).all()

            attendance_data = [{
                'id': record.id,
                'date': record.check_in_time.strftime('%Y-%m-%d'),
                'period': record.period,
                'block_name': record.block_name,
                'status': record.status,
                'check_in_time': record.check_in_time.strftime('%H:%M:%S'),
                'check_out_time': record.check_out_time.strftime('%H:%M:%S') if record.check_out_time else None
            } for record in results]

            return {
                'status': 'success',
                'data': attendance_data
            }, 200

        except Exception as e:
            return {'status': 'error', 'message': str(e)}, 500