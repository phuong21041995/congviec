import os
import glob
import random
from datetime import datetime, timedelta, date, timezone, time
from sqlalchemy import func, or_, and_
import io
import pandas as pd
from collections import defaultdict
from calendar import monthrange
import bleach
import json
import calendar
import re

from bleach.css_sanitizer import CSSSanitizer
from flask import (Blueprint, current_app, flash, jsonify, redirect,
                   render_template, request, send_from_directory, url_for, send_file,session)
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload, subqueryload
from werkzeug.utils import secure_filename
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import (DailyReportData,KeyResult, Log,
                        Objective, Project, Task, UploadedFile, User, Column, Note, PracticeLog, Build,ProductionData, SubTask,TaskComment,Attendance,DailyPlan,DailyPerformance,WeeklyPlan, MonthlyPlan,
                        SalaryConfig, MonthlySalary,LineStatus)
from app.constants import STATUS_META, TASK_STATUSES
from app.utils import get_date_range, get_time_range_from_filter, _vn_day_bounds_to_utc, to_vn_time, to_utc_time
from sqlalchemy import select
from app.models import Habit, HabitLog


    
bp = Blueprint('main', __name__)
# TÌM VÀ THAY THẾ TOÀN BỘ HÀM NÀY MỘT LẦN NỮA
# Trong routes.py
@bp.before_request
def make_session_permanent():
    session.permanent = True
    # Dòng này đảm bảo mỗi khi user F5 lại trang, thời gian 7 ngày sẽ được reset lại từ đầu
    current_app.permanent_session_lifetime = timedelta(days=30)
# =======================================================
# API TÓM TẮT CÔNG VIỆC (OFFLINE - BẢN CUỐI)
# Gửi về HTML thay vì Markdown
# =======================================================
@bp.route('/api/summarize-tasks', methods=['POST'])
@login_required
def api_summarize_tasks():
    data = request.json
    tasks_data = data.get('tasks', []) # Đây là list [ {'what':..., 'who':..., 'status':...} ]
    period = data.get('period', 'period') # Nhận 'Week 45 (03/11-09/11)' từ JS
    
    if not tasks_data:
        return jsonify({'success': False, 'message': 'No tasks provided.'}), 400

    try:
        # 1. Nhóm các task theo TRẠNG THÁI
        tasks_by_status = defaultdict(list)
        all_task_tuples = [] # Lưu (task_what, task_html) để tìm "issues"

        for task in tasks_data:
            task_what = task.get('what', 'No content')
            task_status = task.get('status', 'Pending')
            task_who = task.get('who')
            
            # Giảm padding từ py-2 xuống py-1
            display_who = f" <small class='text-muted'>({task_who})</small>" if task_who else ""
            formatted_task_html = f"<li class='list-group-item py-1 px-3 border-0'>{task_what}{display_who}</li>" # Dùng py-1
            
            tasks_by_status[task_status].append(formatted_task_html)
            all_task_tuples.append((task_what, formatted_task_html))

        # 2. Xây dựng chuỗi HTML tóm tắt (Phiên bản nâng cấp)
        summary_html_parts = []
        
        # Mapping biểu tượng
        STATUS_ICONS = {
            'In Progress': 'fa-solid fa-person-digging text-primary',
            'Pending': 'fa-solid fa-hourglass-half text-muted',
            'Review': 'fa-solid fa-magnifying-glass text-warning',
            'Done': 'fa-solid fa-circle-check text-success',
            'Drop': 'fa-solid fa-circle-xmark text-danger',
            'Default': 'fa-solid fa-circle-question text-info'
        }

        # Phần 1: Bối cảnh (SỬA LẠI: Dùng inline style thay vì class mb-1)
        summary_html_parts.append(f"<p style='margin-bottom: 5px !important;' class='text-dark'><strong>Tóm tắt hoạt động cho {period}.</strong></p>")
        
        # Phần 2: Hạng mục công việc (SỬA LẠI: Dùng inline style thay vì class mb-1)
        summary_html_parts.append(f"""
        <div class='card shadow-sm border-light' style='margin-bottom: 5px !important;'>
          <div class='card-header bg-white py-2'>
            <h6 class='mb-0 text-dark'><i class="fa-solid fa-list-check me-2 text-primary"></i>1. Các hạng mục công việc (theo trạng thái)</h6>
          </div>
          <div class='card-body p-0'>
            <div class='list-group list-group-flush'>
        """) # Mở card-body và list-group
        
        STATUS_ORDER = ['In Progress', 'Pending', 'Review', 'Done', 'Drop']
        found_statuses = set()
        
        for status in STATUS_ORDER:
            if status in tasks_by_status:
                icon_class = STATUS_ICONS.get(status, STATUS_ICONS['Default'])
                # Header cho mỗi status (Dùng py-1)
                summary_html_parts.append(f"<div class='list-group-item list-group-item-light fw-bold py-1 px-3'><i class='{icon_class} me-2'></i>{status}</div>")
                # Thêm các task
                summary_html_parts.extend(tasks_by_status[status])
                found_statuses.add(status)
        
        # Thêm các status khác (nếu có)
        for status, tasks_html in tasks_by_status.items():
            if status not in found_statuses:
                icon_class = STATUS_ICONS.get(status, STATUS_ICONS['Default'])
                # (Dùng py-1)
                summary_html_parts.append(f"<div class='list-group-item list-group-item-light fw-bold py-1 px-3'><i class='{icon_class} me-2'></i>{status}</div>")
                summary_html_parts.extend(tasks_html)

        summary_html_parts.append("</div></div></div>") # Đóng list-group, card-body, card

        # Phần 3: Vấn đề & Theo dõi (Card này không có margin-bottom nên giữ nguyên)
        summary_html_parts.append(f"""
        <div class='card shadow-sm border-light'>
          <div class='card-header bg-white py-2'>
            <h6 class='mb-0 text-dark'><i class="fa-solid fa-triangle-exclamation me-2 text-danger"></i>2. Vấn đề & Theo dõi</h6>
          </div>
        """)
        
        issue_keywords = ['fix', 'issue', 'delay', 'retest', 'check', 'lỗi', 'error', 'follow', 'verify', 'investigate']
        
        issues_found_html = set()
        for task_what, task_html in all_task_tuples:
            task_lower = task_what.lower()
            for keyword in issue_keywords:
                if keyword in task_lower:
                    issues_found_html.add(task_html)
                    break
        
        if not issues_found_html:
            summary_html_parts.append("<div class='card-body py-2 px-3'><p class='mb-0 text-muted'>Không có vấn đề nổi bật.</p></div>")
        else:
            # (Dùng p-0 cho card-body)
            summary_html_parts.append("<div class='card-body p-0'><ul class='list-group list-group-flush'>")
            summary_html_parts.extend(list(issues_found_html))
            summary_html_parts.append("</ul></div>")

        summary_html_parts.append("</div>") # Đóng card

        # Nối tất cả lại
        summary_html = "".join(summary_html_parts)

        # Trả về chuỗi HTML
        return jsonify({'success': True, 'summary': summary_html})

    except Exception as e:
        current_app.logger.error(f"Error in OFFLINE api_summarize_tasks: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'Lỗi khi tạo tóm tắt offline: {str(e)}'}), 500
@bp.route('/switch-db/<string:db_key>')
@login_required
def switch_db(db_key):
    """Lưu lựa chọn database của người dùng vào session."""
    if db_key in ['personal', 'shared']:
        session['db_key'] = db_key
        flash(f"Switched to {db_key} database.", "success")
    else:
        session['db_key'] = 'shared' # Mặc định an toàn
        flash("Invalid database key. Switched to shared database.", "warning")

    # Quay trở lại trang trước đó hoặc trang chủ
    return redirect(request.referrer or url_for('main.home'))
    
@bp.context_processor
def inject_layout_data():
    """Injects data needed for the base layout and modals into all templates."""
    all_projects = Project.query.order_by(Project.position, Project.name).all()
    all_users = User.query.order_by(User.username).all()
    status_choices = ['Planned', 'Active', 'On Hold', 'Done']
    return dict(
        all_projects_for_layout=all_projects,
        all_users_for_layout=all_users,
        status_choices_for_layout=status_choices,
        timedelta=timedelta
    )


def recalculate_kr_progress(kr_id):
    """
    Tính toán lại tiến độ của một Key Result dựa trên các task con.
    SỬA LỖI: Đảm bảo kr.target luôn là tổng số task.
    """
    kr = KeyResult.query.get(kr_id)
    if kr:
        tasks_list = list(kr.tasks)
        if tasks_list:
            total_tasks = len(tasks_list)
            done_tasks = sum(1 for task in tasks_list if task.status == 'Done')
            kr.current = float(done_tasks)
            kr.target = float(total_tasks)
        else:
            kr.current = 0
            kr.target = 0
        # Không cần commit ở đây, sẽ commit ở hàm gọi
    return kr

# File: app/main/routes.py

@bp.route('/api/update-task-dnd', methods=['POST'])
def update_task_dnd():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'Invalid data'}), 400

    task_id = data.get('taskId')
    new_date_str = data.get('task_date')
    new_user_id = data.get('who_id') # Luôn nhận được ID người dùng cũ

    # Kiểm tra các trường bắt buộc
    if not all([task_id, new_date_str, new_user_id]):
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400

    task = Task.query.get(task_id)
    if not task:
        return jsonify({'success': False, 'message': 'Task not found'}), 404

    try:
        task.task_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()
        new_hour = data.get('hour')
        task.hour = int(new_hour) if new_hour is not None else None
        task.who_id = int(new_user_id) # Gán trực tiếp, không cần kiểm tra None

        db.session.commit()
        return jsonify({'success': True, 'message': 'Task updated successfully'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in update_task_dnd: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500
# =======================================================
# ADMIN USER MANAGEMENT
# =======================================================

@bp.route('/admin/users')
@login_required
def admin_users():
    if not current_user.is_admin:
        flash("Bạn không có quyền truy cập trang này.", "danger")
        return redirect(url_for('main.home'))
    users = User.query.order_by(User.id).all()
    return render_template('admin_users.html', page_name='admin_users', users=users, current_user=current_user)

@bp.route('/api/admin/create-user', methods=['POST'])
@login_required
def api_admin_create_user():
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Permission denied'}), 403
    data = request.json
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '').strip()
    if not username or not password:
        return jsonify({'success': False, 'message': 'Username và Password là bắt buộc.'}), 400
    if User.query.filter((User.username == username) | (User.email == email)).first():
        return jsonify({'success': False, 'message': 'User hoặc Email đã tồn tại.'}), 400
    try:
        new_user = User(username=username, email=email)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Tạo user thành công!'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@bp.route('/api/admin/change-password', methods=['POST'])
@login_required
def api_admin_change_password():
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Permission denied'}), 403
    data = request.json
    user_id = data.get('user_id')
    new_password = data.get('new_password', '').strip()
    if not user_id or not new_password:
        return jsonify({'success': False, 'message': 'Thiếu thông tin.'}), 400
    user = User.query.get(user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User không tồn tại.'}), 404
    try:
        user.set_password(new_password)
        db.session.commit()
        return jsonify({'success': True, 'message': f'Đã đổi mật khẩu cho {user.username}'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

# [MỚI] API XÓA USER
@bp.route('/api/admin/delete-user/<int:user_id>', methods=['POST'])
@login_required
def api_admin_delete_user(user_id):
    # 1. Check quyền Admin
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Permission denied'}), 403
    
    # 2. Không cho phép tự xóa mình
    if user_id == current_user.id:
        return jsonify({'success': False, 'message': 'Không thể tự xóa tài khoản của chính mình!'}), 400

    user = User.query.get(user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User không tồn tại.'}), 404
        
    try:
        # Xóa user (Các dữ liệu liên quan như Task, Log sẽ tự động xóa hoặc set null tùy vào config database cascade)
        # Lưu ý: Nếu database không có cascade delete, lệnh này có thể lỗi. 
        # Tuy nhiên với cấu hình relationship thông thường trong Flask-SQLAlchemy (cascade="all, delete-orphan"), nó sẽ ổn.
        username = user.username
        db.session.delete(user)
        db.session.commit()
        return jsonify({'success': True, 'message': f'Đã xóa user {username} vĩnh viễn.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Lỗi khi xóa: {str(e)}'}), 500
# ==============================================================================
# ROUTE API TẬP TRUNG CHO UPLOAD FILE
# ==============================================================================

@bp.route('/api/upload-attachment', methods=['POST'])
@login_required
def upload_attachment():
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file part'}), 400
    
    file = request.files['file']
    task_id = request.form.get('task_id')
    report_id = request.form.get('daily_report_id') # [MỚI]
    
    if file:
        original_filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        saved_filename = f"{timestamp}_{original_filename}"
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], saved_filename)
        
        try:
            file.save(file_path)
            new_file = UploadedFile(
                original_filename=original_filename,
                saved_filename=saved_filename,
                file_type=os.path.splitext(original_filename)[1].lower(),
                file_size=os.path.getsize(file_path),
                uploader_id=current_user.id,
                upload_source='attachment'
            )
            
            if task_id and task_id not in ['null', 'undefined']: 
                new_file.task_id = int(task_id)
            if report_id and report_id not in ['null', 'undefined']: # [MỚI] Link vào report
                new_file.daily_report_id = int(report_id)
            
            db.session.add(new_file)
            db.session.commit()
            return jsonify({ 'success': True, 'file': new_file.to_dict() })
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500

@bp.route('/uploads/<filename>')

def uploaded_file(filename):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)
@bp.route('/upload-image', methods=['POST'])
@login_required
def upload_image():
    if 'file' in request.files:
        file = request.files['file']
        if file.filename != '':
            original_filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            saved_filename = f"{timestamp}_{original_filename}"
            file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], saved_filename))
            return jsonify({'location': url_for('main.uploaded_file', filename=saved_filename)})
    return jsonify({'error': 'Upload failed'}), 400
@bp.route('/delete-uploaded-file/<int:file_id>', methods=['POST'])
@login_required
def delete_uploaded_file(file_id):
    """API chung để xóa bất kỳ file đính kèm nào."""
    current_app.logger.info(f"--- YÊU CẦU XÓA FILE ID: {file_id} ---")
    uploaded_file = UploadedFile.query.get(file_id)

    if not uploaded_file:
        current_app.logger.warning(f"Không tìm thấy file có ID {file_id} trong database.")
        return jsonify({'success': False, 'message': 'File not found in database.'}), 404

    try:
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], uploaded_file.saved_filename)
        current_app.logger.info(f"Đường dẫn file vật lý: {file_path}")
        
        if os.path.exists(file_path):
            os.remove(file_path)
            current_app.logger.info(f"Đã xóa file vật lý thành công: {uploaded_file.saved_filename}")
        else:
            current_app.logger.warning(f"Không tìm thấy file vật lý tại đường dẫn trên, sẽ chỉ xóa trong DB.")
        
        db.session.delete(uploaded_file)
        db.session.commit()
        
        current_app.logger.info(f"Đã xóa bản ghi file khỏi DB thành công cho ID: {file_id}")
        return jsonify({'success': True, 'message': 'File deleted successfully!'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Lỗi nghiêm trọng khi xóa file {file_id}: {str(e)}')
        return jsonify({'success': False, 'message': f'An error occurred on the server: {str(e)}'}), 500
# === KẾT THÚC ĐOẠN CODE CẦN THÊM ===
@bp.route('/')
@login_required
def root():
    return redirect(url_for('main.home'))

@bp.route('/calendar')
@bp.route('/calendar/<string:view_mode>/<string:date_str>')
@login_required
def index(view_mode='week', date_str=None):
    # Lấy user_id từ URL, mặc định là 'all' để hiển thị tất cả
    selected_user_id = request.args.get('user_id', 'all')

    if date_str is None:
        date_str = datetime.today().strftime('%Y-%m-%d')

    # Tính toán các khoảng thời gian dựa trên view_mode
    start_date, end_date, date_display = get_date_range(view_mode, date_str)
    if view_mode == 'week' and '(' in date_display:
        date_display = date_display.split('(')[0].strip()
    base_date = datetime.strptime(date_str, '%Y-%m-%d').date()

    if view_mode == 'day':
        prev_period_date = (base_date - timedelta(days=1)).strftime('%Y-%m-%d')
        next_period_date = (base_date + timedelta(days=1)).strftime('%Y-%m-%d')
    elif view_mode == 'week':
        prev_period_date = (start_date - timedelta(days=7)).strftime('%Y-%m-%d')
        next_period_date = (start_date + timedelta(days=7)).strftime('%Y-%m-%d')
    else:  # month
        prev_period_date = (start_date - timedelta(days=1)).replace(day=1).strftime('%Y-%m-%d')
        next_period_date = (end_date + timedelta(days=1)).strftime('%Y-%m-%d')

    # Chuẩn bị dữ liệu cho các dropdown điều hướng
    year = base_date.year
    first_day_of_year = datetime(year, 1, 1)
    weeks_in_year = [{'num': (first_day_of_year + timedelta(days=i*7)).isocalendar()[1], 'date_str': (first_day_of_year + timedelta(days=i*7)).strftime('%Y-%m-%d')} for i in range(53) if (first_day_of_year + timedelta(days=i*7)).year == year]
    months_in_year = [{'name': datetime(year, i, 1).strftime('%B'), 'date_str': datetime(year, i, 1).strftime('%Y-%m-%d')} for i in range(1, 13)]
    
    # Lấy dữ liệu chung
    all_users = User.query.order_by(User.username).all()
    logs = Log.query.order_by(Log.timestamp.desc()).limit(20).all()
    all_projects = Project.query.order_by(Project.name).all()
    all_builds = Build.query.order_by(Build.name).all()
    all_objectives = Objective.query.order_by(Objective.content).all()
    all_key_results = KeyResult.query.order_by(KeyResult.content).all()

    # Xây dựng context ban đầu sẽ được gửi tới template
    context = {
        'page_name': 'calendar',
        'view_mode': view_mode,
        'date_str': date_str,
        'date_display': date_display,
        'base_date': base_date,
        'prev_period_date': prev_period_date,
        'next_period_date': next_period_date,
        'today_date_str': datetime.today().strftime('%Y-%m-%d'),
        'weeks_in_year': weeks_in_year,
        'months_in_year': months_in_year,
        'users': all_users,
        'logs': logs,
        'selected_user_id': selected_user_id,
        'all_projects': all_projects,
        'all_builds': all_builds,
        'all_objectives': all_objectives,
        'all_key_results': all_key_results
    }

    # Xây dựng câu truy vấn Task cơ bản
    base_query = Task.query.options(joinedload(Task.attachments), joinedload(Task.assignee))
    
    # Áp dụng bộ lọc user nếu người dùng đã chọn
    if selected_user_id != 'all':
        base_query = base_query.filter(Task.who_id == selected_user_id)

    # 1. Xác định khoảng thời gian truy vấn dữ liệu cho lịch
    if view_mode == 'month':
        start_of_grid = start_date - timedelta(days=start_date.weekday())
        end_of_grid = start_of_grid + timedelta(days=41) # 6 tuần * 7 ngày
        task_query_range = base_query.filter(Task.task_date.between(start_of_grid, end_of_grid))
    else:
        task_query_range = base_query.filter(Task.task_date.between(start_date, end_date))

    # 2. Lấy tất cả task trong khoảng thời gian đã xác định
    all_tasks_in_range = task_query_range.order_by(Task.task_date.desc()).all()

    # 3. Tính toán dữ liệu SUMMARY (bao gồm cả đếm status cho biểu đồ)
    summary_data = []
    tasks_by_user = defaultdict(list)
    # Chỉ lấy task trong khoảng thời gian hiển thị chính (ví dụ: 1 tuần) để tính summary
    tasks_for_summary = [t for t in all_tasks_in_range if start_date <= t.task_date <= end_date]
    
    for task in tasks_for_summary:
        if task.assignee:
            tasks_by_user[task.assignee].append(task)
    
    for user, tasks in tasks_by_user.items():
        status_counts = defaultdict(int)
        for task in tasks:
            status_counts[task.status] += 1
        
        summary_data.append({
            'user': user.to_dict(),
            'task_count': len(tasks),
            'tasks': [t.to_dict() for t in sorted(tasks, key=lambda x: x.task_date)],
            'status_counts': dict(status_counts)
        })
   
    summary_data.sort(key=lambda x: x['user']['username'])  
    context['summary_data'] = summary_data

    # 4. Tính toán dữ liệu LỊCH (tasks_by_date)
    tasks_by_date = defaultdict(list)
    for task in all_tasks_in_range:
        tasks_by_date[task.task_date.strftime('%Y-%m-%d')].append(task.to_dict())
    context['tasks_by_date'] = tasks_by_date

    # 5. Cập nhật context riêng cho từng view mode
    if view_mode == 'month':
        context.update({
            'calendar_dates': [start_of_grid + timedelta(days=i) for i in range(42)],
            'current_month': start_date.month
        })
    else:
        context.update({'hours': range(8, 21)})
        if view_mode == 'day':
            context['week_dates'] = [start_date]
            day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            context['week_days_display'] = [(day_names[start_date.weekday()], start_date.strftime('%a'))]
            # Tính toán thống kê cho biểu đồ ngày
            day_tasks = tasks_by_date.get(start_date.strftime('%Y-%m-%d'), [])
            context['day_stats'] = {
                status: sum(1 for t in day_tasks if t['status'] == status) 
                for status in ['Pending', 'In Progress', 'Review', 'Done', 'Drop']
            }
        else:  # 'week' view
            context['week_dates'] = [start_date + timedelta(days=i) for i in range(7)]
            context['week_days_display'] = [("Mon", "Mon"), ("Tue", "Tue"), ("Wed", "Wed"), ("Thu", "Thu"), ("Fri", "Fri"), ("Sat", "Sat"), ("Sun", "Sun")]

    return render_template('index.html', **context)


# Thêm hàm hỗ trợ tính toán lặp lại
def generate_recurring_dates(start_date, recurrence, end_date):
    """Sinh ra danh sách ngày lặp lại"""
    dates = []
    current_date = start_date
    
    # Giới hạn an toàn để tránh vòng lặp vô tận (ví dụ: tối đa 365 lần hoặc 2 năm)
    safety_limit = 100 
    count = 0

    while current_date < end_date and count < safety_limit:
        if recurrence == 'daily':
            current_date += timedelta(days=1)
        elif recurrence == 'weekly':
            current_date += timedelta(weeks=1)
        elif recurrence == 'monthly':
            # Logic cộng tháng đơn giản (cần cẩn thận với ngày 31)
            # Dùng thư viện dateutil.relativedelta thì tốt hơn, nhưng đây là pure python
            year = current_date.year + (current_date.month // 12)
            month = (current_date.month % 12) + 1
            day = min(current_date.day, [31, 29 if (year%4==0 and year%100!=0) or (year%400==0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month-1])
            current_date = date(year, month, day)
        
        if current_date <= end_date:
            dates.append(current_date)
        count += 1
        
    return dates

@bp.route('/save-task', methods=['POST'])
@login_required
def save_task():
    """
    Lưu Task. 
    [LOGIC CHUẨN]: 
    - Start Date mặc định là Hôm Nay.
    - End Date giữ nguyên theo User nhập.
    - Nếu Start > End (do End là quá khứ) -> Lùi Start về bằng End.
    - Nếu User chọn Start > End (cố tình) -> Đẩy End lên bằng Start.
    """
    try:
        data = request.form
        task_id = data.get('taskId')
        what = data.get('taskWhat', '').strip()
        
        # 1. Lấy dữ liệu Ngày tháng
        task_date_str = data.get('taskDate')       # End Date / Due Date
        start_date_str = data.get('taskStartDate') # Start Date

        if not what:
            return jsonify({'success': False, 'message': 'Task title is required.'}), 400
        
        # Parse End Date (Ưu tiên giữ nguyên input của user)
        task_date = None
        if task_date_str:
            task_date = datetime.strptime(task_date_str, '%Y-%m-%d').date()
        else:
            task_date = date.today()

        # Parse Start Date
        start_date = None
        if start_date_str:
             # Case A: User CHỌN ngày bắt đầu cụ thể
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            
            # Nếu user cố tình chọn Start > End (Vô lý) -> Tự động đẩy End về tương lai cho khớp
            if task_date and start_date > task_date:
                task_date = start_date
        else:
            # Case B: User KHÔNG chọn ngày bắt đầu -> Mặc định là Hôm nay
            start_date = date.today()
            
            # Nếu Hôm nay (Start) > Deadline User nhập (End) -> Đây là task quá khứ/bổ sung
            # Giữ nguyên End Date (để yên đó), lùi Start Date về bằng End Date
            if task_date and start_date > task_date:
                start_date = task_date
        hour_val = data.get('taskHour')
        hour = str(hour_val).strip() if hour_val else None
        

        who_id = int(data.get('taskWho')) if data.get('taskWho') else None
        key_result_id = int(data.get('taskKeyResult')) if data.get('taskKeyResult') else None
        recurrence = data.get('taskRecurrence', 'none')
        end_date_str = data.get('taskRecurrenceEndDate')
        recurrence_end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str and recurrence != 'none' else None

        # --- 2. Lấy hoặc tạo đối tượng Task ---
        if task_id:
            task = Task.query.get_or_404(task_id)
            log_content = f"Updated task ID {task.id}"
        else:
            task = Task()
            db.session.add(task)
            log_content = "Created new task"

        # --- 3. Cập nhật dữ liệu ---
        task.what = what
        task.start_date = start_date # [Lưu Start Date]
        task.task_date = task_date   # [Lưu End Date]
        task.hour = hour
        task.who_id = who_id
        task.status = data.get('taskStatus', 'Pending')
        task.priority = data.get('taskPriority', 'Medium')
        task.note = bleach.clean(data.get('taskNote', ''))
        task.key_result_id = key_result_id
        task.recurrence = recurrence
        task.recurrence_end_date = recurrence_end_date
        
        # --- 4. Xử lý Subtasks (Checklist) ---
        subtasks_json = data.get('subTasks')
        if subtasks_json:
            subtasks_data = json.loads(subtasks_json)
            existing_subtasks = {st.id: st for st in task.sub_tasks}
            
            for item_data in subtasks_data:
                item_id = item_data.get('id')
                content = (item_data.get('content') or "").strip()
                if not content: continue

                if item_id and int(item_id) in existing_subtasks:
                    subtask = existing_subtasks.pop(int(item_id))
                    subtask.content = content
                    subtask.is_done = item_data.get('is_done', False)
                else:
                    new_subtask = SubTask(content=content, is_done=item_data.get('is_done', False))
                    task.sub_tasks.append(new_subtask)
            
            for subtask_to_delete in existing_subtasks.values():
                db.session.delete(subtask_to_delete)
        
        db.session.flush()

        # --- 5. Xử lý File Upload ---
        files = request.files.getlist('attachments[]')
        for file in files:
            if file and file.filename != '':
                original_filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
                random_str = str(random.randint(1000, 9999))
                saved_filename = f"{timestamp}_{random_str}_{original_filename}"
                
                file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], saved_filename)
                file.save(file_path)
                file_size = os.path.getsize(file_path)
                _, file_ext = os.path.splitext(original_filename)

                new_file = UploadedFile(
                    original_filename=original_filename,
                    saved_filename=saved_filename,
                    file_type=file_ext.lower(),
                    file_size=file_size,
                    uploader_id=current_user.id,
                    upload_source='attachment',
                    task_id=task.id 
                )
                db.session.add(new_file)
        
        db.session.add(Log(action=f"{log_content}: '{what}'", user_id=current_user.id))
        db.session.commit()
        
        db.session.refresh(task)
        return jsonify({'success': True, 'task': task.to_dict(), 'message': 'Task saved!'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in save_task: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500


@bp.route('/api/task/<int:task_id>')
@login_required
def api_get_task(task_id):
    # Tải sẵn sub_tasks để tối ưu khi lấy dữ liệu
    task = Task.query.options(
        joinedload(Task.attachments), 
        joinedload(Task.assignee),
        subqueryload(Task.sub_tasks) 
    ).get_or_404(task_id)
    return jsonify({'success': True, 'task': task.to_dict()})



@bp.route('/update-task-time', methods=['POST'])
@login_required
def update_task_time():
    data = request.json
    task = Task.query.get_or_404(data.get('taskId'))
    new_date = datetime.strptime(data.get('newDate'), '%Y-%m-%d').date()
    new_hour = data.get('newHour')
    
    task.task_date, task.hour = new_date, new_hour
    db.session.add(Log(action=f"Dời lịch CV ID {task.id}: '{task.what}' sang {new_date.strftime('%d/%m/%Y')}", user_id=current_user.id))
    db.session.commit()
    return jsonify({'success': True, 'task': task.to_dict(), 'message': 'Updated success'})

@bp.route('/delete-task/<int:task_id>', methods=['POST'])
@login_required
def delete_task(task_id):
    # Dùng get() thay vì get_or_404 để kiểm soát thông báo lỗi tốt hơn
    task = Task.query.get(task_id)
    
    if not task:
        # Trả về 404 nhưng kèm message JSON để frontend không bị crash nếu lỡ task đã bị xóa
        return jsonify({'success': False, 'message': 'Công việc không tồn tại hoặc đã bị xóa.'}), 404

    try:
        # Ghi log trước khi xóa
        db.session.add(Log(action=f"Deleted task ID {task.id}: '{task.what}'", user_id=current_user.id))
        
        # Xóa task (Database sẽ tự động xóa Subtasks/Files nhờ cascade nếu đã config model đúng)
        db.session.delete(task)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Đã xóa công việc.'})
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting task {task_id}: {e}")
        return jsonify({'success': False, 'message': f'Lỗi server: {str(e)}'}), 500

@bp.route('/okr')
@bp.route('/okr/<string:view_mode>/<string:date_str>')
@login_required
def okr_page(view_mode='week', date_str=None):
    if date_str is None: date_str = datetime.today().strftime('%Y-%m-%d')
    start_date, end_date, date_display = get_date_range(view_mode, date_str)
    base_date = datetime.strptime(date_str, '%Y-%m-%d').date()

    # Lấy tham số lọc từ URL
    project_filter_id = request.args.get('project_id', type=int)

    # Điều hướng
    if view_mode == 'week': prev_period_date, next_period_date = (start_date - timedelta(days=7)).strftime('%Y-%m-%d'), (start_date + timedelta(days=7)).strftime('%Y-%m-%d')
    elif view_mode == 'month': prev_period_date, next_period_date = (start_date - timedelta(days=1)).replace(day=1).strftime('%Y-%m-%d'), (end_date + timedelta(days=1)).strftime('%Y-%m-%d')
    else: prev_period_date, next_period_date = start_date.replace(year=start_date.year - 1).strftime('%Y-%m-%d'), start_date.replace(year=start_date.year + 1).strftime('%Y-%m-%d')
    
    # Lấy tất cả Objectives trong khoảng thời gian để tính toán
    all_objectives_in_range = Objective.query.options(
        joinedload(Objective.project),
        joinedload(Objective.key_results).joinedload(KeyResult.tasks)
    ).filter(Objective.start_date.between(start_date, end_date)).all()

    # --- TÍNH TOÁN DỮ LIỆU CHO DASHBOARD ---
    total_stats = {'o': 0, 'kr': 0, 'task': 0}
    stats_by_project = defaultdict(lambda: {'name': '', 'o_count': 0, 'kr_count': 0, 'task_count': 0, 'progress': []})
    
    for obj in all_objectives_in_range:
        total_stats['o'] += 1
        total_stats['kr'] += len(obj.key_results)
        
        project_id = obj.project.id if obj.project else 0 # 0 cho "Unassigned"
        project_name = obj.project.name if obj.project else "Unassigned"
        stats_by_project[project_id]['name'] = project_name
        stats_by_project[project_id]['o_count'] += 1
        stats_by_project[project_id]['kr_count'] += len(obj.key_results)
        stats_by_project[project_id]['progress'].append(obj.progress)

        for kr in obj.key_results:
            total_stats['task'] += len(kr.tasks)
            stats_by_project[project_id]['task_count'] += len(kr.tasks)

    # Tính tiến độ trung bình cho mỗi project
    for pid in stats_by_project:
        progress_list = stats_by_project[pid]['progress']
        if progress_list:
            stats_by_project[pid]['avg_progress'] = sum(progress_list) / len(progress_list)
        else:
            stats_by_project[pid]['avg_progress'] = 0

    # --- LỌC DỮ LIỆU CHO TAB CHI TIẾT ---
    objectives_for_display = all_objectives_in_range
    filtered_project_name = None
    if project_filter_id is not None:
        if project_filter_id == 0: # Unassigned
            objectives_for_display = [o for o in all_objectives_in_range if o.project_id is None]
            filtered_project_name = "Unassigned"
        else:
            objectives_for_display = [o for o in all_objectives_in_range if o.project_id == project_filter_id]
            project = Project.query.get(project_filter_id)
            if project:
                filtered_project_name = project.name
    
    # Dữ liệu chung khác
    users = User.query.all()
    projects = Project.query.all()
    builds = Build.query.all()
    logs = Log.query.order_by(Log.timestamp.desc()).limit(20).all()
    year = base_date.year
    first_day_of_year = datetime(year, 1, 1)
    weeks_in_year = [{'num': (first_day_of_year + timedelta(days=i*7)).isocalendar()[1], 'date_str': (first_day_of_year + timedelta(days=i*7)).strftime('%Y-%m-%d')} for i in range(53) if (first_day_of_year + timedelta(days=i*7)).year == year]
    months_in_year = [{'name': datetime(year, i, 1).strftime('%B'), 'date_str': datetime(year, i, 1).strftime('%Y-%m-%d')} for i in range(1, 13)]
    
    context = {
        'view_mode': view_mode, 'date_str': date_str, 'date_display': date_display,
        'objectives': objectives_for_display,
        'prev_period_date': prev_period_date, 'next_period_date': next_period_date,
        'weeks_in_year': weeks_in_year, 'months_in_year': months_in_year,
        'today_date_str': datetime.today().strftime('%Y-%m-%d'),
        'today_date_obj': date.today(),
        'users': users, 'projects': projects, 'builds': builds, 'page_name': 'okr',
        'logs': logs,
        'total_stats': total_stats,
        'stats_by_project': stats_by_project,
        'project_filter_id': project_filter_id,
        'filtered_project_name': filtered_project_name,
        'all_projects': Project.query.order_by(Project.name).all(),
        'all_builds': Build.query.order_by(Build.name).all(),
        'all_objectives': Objective.query.order_by(Objective.content).all(),
        'all_key_results': KeyResult.query.order_by(KeyResult.content).all()
    }
    return render_template('okr.html', **context)

@bp.route('/add-project', methods=['POST'])
@login_required
def add_project():
    name = request.form.get('name')
    start_date_str = request.form.get('start_date')
    end_date_str = request.form.get('end_date')

    if not name:
        flash('Tên dự án không được để trống.', 'danger')
        return redirect(url_for('main.global_timeline'))

    # Check for duplicate name
    existing_project = Project.query.filter_by(name=name).first()
    if existing_project:
        flash(f'Tên dự án "{name}" đã tồn tại. Vui lòng chọn tên khác.', 'warning')
        return redirect(url_for('main.global_timeline'))

    # If not a duplicate, continue
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None
    
    new_project = Project(
        name=name,
        description=request.form.get('description'),
        status=request.form.get('status', 'Active'),
        start_date=start_date,
        end_date=end_date,
        owner_id=request.form.get('owner_id') or None, # <-- THÊM/SỬA DÒNG NÀY
        note=request.form.get('note'), # <-- THÊM DÒNG NÀY
        plan_link=request.form.get('plan_link') # <<< THÊM DÒNG NÀY
    )
    db.session.add(new_project)
    db.session.commit()
    flash('Created new project!', 'success')
    
    return redirect(url_for('main.global_timeline'))
# ADD THIS LINE
@bp.route('/add-objective', methods=['POST'])
@login_required
def add_objective():
    data = request.form
    content = data.get('content')
    project_id = data.get('project_id')

    if not content:
        flash('Objective content is required.', 'danger')
        if project_id:
            return redirect(url_for('main.global_timeline', project_id=project_id, tab='okr'))
        return redirect(url_for('main.okr_page'))

    start_date_str = data.get('start_date_obj')
    end_date_str = data.get('end_date_obj')
    
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else date.today()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None

    colors = ['#0d6efd', '#1cc88a', '#36b9cc', '#f6c23e', '#e74a3b', '#6f42c1']
    new_obj = Objective(
        content=content, 
        start_date=start_date, 
        end_date=end_date,
        color=random.choice(colors), 
        owner_id=data.get('owner_id') or None, 
        project_id=project_id or None, 
        build_id=data.get('build_id') or None,
        note=data.get('note') # <-- THÊM DÒNG NÀY
    )
    db.session.add(new_obj)
    db.session.commit()
    
    db.session.add(Log(action=f"Created new Objective: '{new_obj.content}'", user_id=current_user.id))
    db.session.commit()
    
    flash('New objective created!', 'success')
    
    if project_id:
        return redirect(url_for('main.project_workspace', project_id=project_id, tab='okr'))
    
    return redirect(url_for('main.okr_page'))
    
@bp.route('/add-key-result', methods=['POST'])
@login_required
def add_key_result():
    data = request.get_json()
    if not data or not data.get('objective_id') or not data.get('content'):
        return jsonify({'success': False, 'message': 'Missing required information'}), 400
    try:
        new_kr = KeyResult(
            objective_id=data['objective_id'], 
            content=data['content'], 
            owner_id=current_user.id, # Gán mặc định
            target=0, current=0
        )
        db.session.add(new_kr)
        db.session.commit()
        # SỬA LỖI: Gọi đúng phương thức to_dict_for_obj_detail vừa tạo
        return jsonify({ 'success': True, 'kr': new_kr.to_dict_for_obj_detail() })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in add_key_result: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500
    
@bp.route('/api/task/<int:task_id>/update-status-okr', methods=['POST'])
@login_required
def update_task_from_okr(task_id):
    task = Task.query.get_or_404(task_id)
    
    # Lấy trạng thái từ checkbox (true/false)
    is_checked = request.json.get('checked')
    old_status = task.status
    task.status = 'Done' if is_checked else 'Pending'

    # [MỚI] Nếu Done -> Dời End Date về hôm nay
    if task.status == 'Done':
        task.task_date = date.today()
        # [FIX QUAN TRỌNG] Kéo Start Date về nếu bị ngược thời gian
        if task.start_date and task.start_date > task.task_date:
            task.start_date = task.task_date

    # Ghi log
    status_text = "Hoàn thành" if task.status == 'Done' else "Chuyển về Pending"
    db.session.add(Log(action=f"{status_text} Task ID {task.id}: '{task.what}'", user_id=current_user.id))

    # Xử lý cập nhật tiến độ KR (nếu có)
    if not task.key_result_id:
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Task status updated (task is not linked to an OKR).'
        })
    
    # Tính toán lại tiến độ KR
    kr = recalculate_kr_progress(task.key_result_id)
    db.session.commit()
    
    db.session.refresh(kr)
    db.session.refresh(kr.objective)

    return jsonify({
        'success': True, 
        'message': 'Task status and KR progress updated',
        'kr_id': kr.id, 
        'objective_id': kr.objective_id,
        'kr_progress': kr.progress, 
        'obj_progress': kr.objective.progress, 
        'kr_current': kr.current, 
        'kr_target': kr.target
    })


@bp.route('/api/objective/<int:obj_id>')
@login_required
def api_get_objective(obj_id):
    obj = Objective.query.get_or_404(obj_id)
    return jsonify({
        'success': True,
        'objective': {
            'id': obj.id, 'content': obj.content,
            'owner_id': obj.owner_id or '', 'project_id': obj.project_id or '',
            'build_id': obj.build_id or '', 'note': obj.note or '',
            'start_date': obj.start_date.isoformat() if obj.start_date else '',
            'end_date': obj.end_date.isoformat() if obj.end_date else ''
        }
    })
        

@bp.route('/delete/<item_type>/<int:item_id>', methods=['POST'])
@login_required
def delete_item(item_type, item_id):
    # ... (Hàm này giữ nguyên như cũ)
    model_map = {'objective': Objective, 'key_result': KeyResult, 'task': Task}
    Model = model_map.get(item_type)
    if not Model: return jsonify({'success': False, 'message': 'Type not suitable'}), 400
    
    item = Model.query.get_or_404(item_id)
    response_data = {'success': True}
    
    # Ghi log trước khi xóa
    item_name = item.what if hasattr(item, 'what') else item.content
    db.session.add(Log(action=f"Xóa {item_type} ID {item.id}: '{item_name}'", user_id=current_user.id))

    # Xóa item và commit
    db.session.delete(item)
    db.session.commit()
    
    return jsonify(response_data)
    
@bp.route('/task/<int:task_id>/save-report', methods=['POST'])
@login_required
def save_task_report(task_id):
    task = Task.query.get_or_404(task_id)
    
    report_content = request.form.get('report_content')
    if report_content is not None:
        allowed_tags = list(bleach.ALLOWED_TAGS) + [
            'p', 'br', 'strong', 'em', 'u', 'ol', 'ul', 'li', 
            'img', 'a', 'span', 'div'
        ]
        allowed_attrs = {
            **bleach.ALLOWED_ATTRIBUTES, 
            'img': ['src', 'alt', 'style', 'width', 'height'], 
            'a': ['href', 'title'], 
            'span':['style'], 
            'div':['style']
        }
        task.report = bleach.clean(
            report_content, 
            tags=allowed_tags, 
            attributes=allowed_attrs 
        )

    db.session.commit()
    flash('Saved!', 'success')
    return redirect(url_for('main.okr_page'))

@bp.route('/search')
@login_required
def search():
    """
    Route xử lý tìm kiếm toàn bộ dữ liệu.
    """
    query = request.args.get('q', '').strip()
    results = {
        'projects': [],
        'objectives': [],
        'key_results': [],
        'tasks': [],
        'sub_tasks': [],
        'notes': [],
        'files': []
    }

    if not query:
        # Nếu không có query, trả về trang trống với thông báo
        return render_template('search_results.html', query=query, results=results)

    # 1. Tìm kiếm Projects
    results['projects'] = Project.query.filter(Project.name.ilike(f'%{query}%')).all()

    # 2. Tìm kiếm Objectives
    results['objectives'] = Objective.query.filter(Objective.content.ilike(f'%{query}%')).all()

    # 3. Tìm kiếm Key Results
    results['key_results'] = KeyResult.query.filter(KeyResult.content.ilike(f'%{query}%')).all()

    # 4. Tìm kiếm Tasks (cả 'what' và 'note')
    results['tasks'] = Task.query.filter(
        db.or_(
            Task.what.ilike(f'%{query}%'),
            Task.note.ilike(f'%{query}%')
        )
    ).all()

    # 5. Tìm kiếm SubTasks (Checklist)
    results['sub_tasks'] = SubTask.query.filter(SubTask.content.ilike(f'%{query}%')).all()

    # 6. Tìm kiếm Notes (cả 'title' và 'content')
    results['notes'] = Note.query.filter(
        db.or_(
            Note.title.ilike(f'%{query}%'),
            Note.content.ilike(f'%{query}%')
        )
    ).all()
    
    # 7. Tìm kiếm Uploaded Files
    results['files'] = UploadedFile.query.filter(UploadedFile.original_filename.ilike(f'%{query}%')).all()

    return render_template('search_results.html', query=query, results=results)
@bp.route('/api/projects')
@login_required
def api_projects_list():
    projects = Project.query.options(joinedload(Project.builds)).order_by(Project.name).all()
    projects_list = []
    for p in projects:
        project_dict = {
            'id': p.id,
            'name': p.name,
            'builds': [{'id': b.id, 'name': b.name} for b in p.builds]
        }
        projects_list.append(project_dict)
    return jsonify({'success': True, 'projects': projects_list})

# Mở file: app/routes.py
@bp.route('/api/builds/<int:project_id>')
@login_required
def api_builds_list(project_id):
    project = Project.query.get_or_404(project_id)
    # SỬA LẠI: Đổi key 'builds' thành 'items'
    builds = [{'id': b.id, 'name': b.name} for b in project.builds]
    return jsonify({'success': True, 'items': builds})

# Mở file: app/routes.py
@bp.route('/api/objectives/<int:build_id>')
@login_required
def api_objectives_list(build_id):
    build = Build.query.get_or_404(build_id)
    # SỬA LẠI: Đổi key 'content' thành 'name' và key 'objectives' thành 'items'
    objectives = [{'id': o.id, 'name': o.content} for o in build.objectives]
    return jsonify({'success': True, 'items': objectives})
    
# Mở file: app/routes.py
@bp.route('/api/key-results/<int:objective_id>')
@login_required
def api_key_results_list(objective_id):
    objective = Objective.query.get_or_404(objective_id)
    # SỬA LẠI: Đổi key 'content' thành 'name' và key 'key_results' thành 'items'
    key_results = [{'id': kr.id, 'name': kr.content} for kr in objective.key_results]
    return jsonify({'success': True, 'items': key_results})


@bp.route('/uploads-manager')
@login_required
def uploads_manager():
    import shutil

    query_param = request.args.get('q', type=str, default='')
    context_filter = request.args.get('context', 'all')
    user_filter = request.args.get('user', 'all')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    files_q = UploadedFile.query
    if query_param:
        files_q = files_q.filter(UploadedFile.original_filename.ilike(f"%{query_param}%"))

    if context_filter == 'direct':
        files_q = files_q.filter(UploadedFile.upload_source == 'direct')
    elif context_filter == 'attachment':
        files_q = files_q.filter(UploadedFile.upload_source == 'attachment')

    if user_filter != 'all':
        files_q = files_q.filter(UploadedFile.uploader_id == user_filter)

    pagination = files_q.order_by(UploadedFile.upload_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    files = pagination.items

    try:
        disk_root = os.path.abspath(current_app.config['UPLOAD_FOLDER'])
        total, used, free = shutil.disk_usage(disk_root)
    except Exception:
        total = used = free = 0

    total_gb = total / (1024**3)
    used_gb = used / (1024**3)
    free_gb = free / (1024**3)

    all_files = UploadedFile.query.all()
    uploaded_total_bytes = sum((f.file_size or 0) for f in all_files)
    uploaded_gb = uploaded_total_bytes / (1024**3)
    other_gb = max(used_gb - uploaded_gb, 0.0)

    by_ext = defaultdict(lambda: {'count': 0, 'bytes': 0})
    for f in all_files:
        ext = (f.file_type or '').lower() or '(khác)'
        by_ext[ext]['count'] += 1
        by_ext[ext]['bytes'] += (f.file_size or 0)

    files_by_type = sorted(
        [(k, v['count'], v['bytes']) for k, v in by_ext.items()],
        key=lambda t: t[2],
        reverse=True
    )[:8]

    chart_data = {
        'total_gb': round(total_gb, 2),
        'uploaded_size_gb': round(uploaded_gb, 2),
        'other_data_size_gb': round(other_gb, 2),
        'free_space_gb': round(free_gb, 2),
        'files_by_type': files_by_type
    }

    all_users = User.query.all()
    context_choices = [
        {'value': 'all', 'text': 'All'},
        {'value': 'direct', 'text': 'Upload here'},
        {'value': 'attachment', 'text': 'Other tab'}
    ]

    return render_template(
        'uploads_manager.html',
        page_name='uploads_manager',
        files=files,
        pagination=pagination,
        query=query_param,
        context_filter=context_choices,
        user_filter=user_filter,
        context_choices=context_choices,
        all_users=all_users,
        chart_data=chart_data,
        total_files=len(all_files),
        per_page=per_page
    )
# SỬA LỖI NÀY - Tìm hàm có tên @bp.route('/api/dhtmlx-data')
@bp.route('/api/dhtmlx-data')
@login_required
def api_dhtmlx_data():
    project_id = request.args.get('project_id', type=int)
    if not project_id:
        return jsonify({"data": []})

    # Tải trước tất cả dữ liệu liên quan để tránh N+1 query
    project = Project.query.options(
        subqueryload(Project.builds).subqueryload(Build.objectives)
        .subqueryload(Objective.key_results).subqueryload(KeyResult.tasks)
        .joinedload(Task.assignee) # Dùng joinedload cho quan hệ cuối cùng (assignee)
    ).get_or_404(project_id)

    gantt_data = []

    def add_days_if_date(d, days):
        return (d + timedelta(days=days)) if d else None

    if project.start_date and project.end_date:
        gantt_data.append({
            "id": f"proj-{project.id}", "text": project.name,
            "start_date": project.start_date.isoformat(),
            "end_date": add_days_if_date(project.end_date, 1).isoformat(),
            "type": "project", "open": True,
            "progress": project.progress / 100.0  # <<< THÊM DÒNG NÀY
        })

    for build in project.builds:
        if not build.start_date or not build.end_date:
            continue
        gantt_data.append({
            "id": f"build-{build.id}", "text": build.name,
            "start_date": build.start_date.isoformat(),
            "end_date": add_days_if_date(build.end_date, 1).isoformat(),
            "type": "build", "parent": f"proj-{project.id}", "open": True,
            "progress": build.progress / 100.0  # <<< THÊM DÒNG NÀY
        })

        for obj in build.objectives:
            if not obj.start_date: continue
            obj_end = obj.end_date or obj.start_date
            gantt_data.append({
                "id": f"obj-{obj.id}", "text": obj.content,
                "start_date": obj.start_date.isoformat(),
                "end_date": add_days_if_date(obj_end, 1).isoformat(),
                "type": "objective", "parent": f"build-{build.id}", "open": True,
                "progress": obj.progress / 100.0
            })

            for kr in obj.key_results:
                task_dates = [t.task_date for t in kr.tasks if t.task_date]
                start_date = kr.start_date or (min(task_dates) if task_dates else None)
                end_date = kr.end_date or (max(task_dates) if task_dates else None)

                if not start_date: continue
                end_date = end_date or start_date

                gantt_data.append({
                    "id": f"kr-{kr.id}", "text": kr.content,
                    "start_date": start_date.isoformat(),
                    "end_date": add_days_if_date(end_date, 1).isoformat(),
                    "type": "key_result", "parent": f"obj-{obj.id}", "open": True,
                    "progress": kr.progress / 100.0
                })

                for task in kr.tasks: # Bây giờ task.assignee đã được tải sẵn
                    if not task.task_date: continue
                    gantt_data.append({
                        "id": f"task-{task.id}", "text": task.what,
                        "start_date": task.task_date.isoformat(),
                        "end_date": add_days_if_date(task.task_date, 1).isoformat(),
                        "type": "task", "parent": f"kr-{kr.id}",
                        "assignee_name": task.assignee.username if task.assignee else "",
                        "progress": 1.0 if task.status == 'Done' else 0.0,
                    })
                        
    return jsonify({"data": gantt_data})

# ==============================================================================
# START: SỬA LỖI VÀ TÁI CẤU TRÚC HÀM project_workspace
# ==============================================================================
@bp.route('/projects')
@login_required
def project_workspace():
    selected_project_id = request.args.get('project_id', type=int)
    active_tab = request.args.get('tab', 'info')
    
    if not selected_project_id:
        flash("Please select a project to view its workspace.", "info")
        return redirect(url_for('main.home'))

    project = Project.query.options(
        joinedload(Project.owner),
        subqueryload(Project.builds)
    ).get_or_404(selected_project_id)
    
    # [AUDIT BUILD PROGRESS] - TÍNH TOÁN LẠI TIẾN ĐỘ BUILD
    # Logic: Duyệt qua từng build -> Đếm task con -> Tính % thực tế
    for build in project.builds:
        # Truy vấn đếm task: Task -> KeyResult -> Objective -> Build
        b_tasks_query = db.session.query(Task.status)\
            .join(KeyResult)\
            .join(Objective)\
            .filter(Objective.build_id == build.id)
            
        total_tasks = b_tasks_query.count()
        done_tasks = b_tasks_query.filter(Task.status == 'Done').count()
        
        # Gán thuộc tính tạm thời "real_progress" để hiển thị
        build.total_tasks_count = total_tasks
        build.done_tasks_count = done_tasks
        
        if total_tasks > 0:
            build.real_progress = int((done_tasks / total_tasks) * 100)
        else:
            build.real_progress = 0
            
        # LƯU Ý: Không gán build.progress = ... nữa để tránh lỗi AttributeError

# Truy vấn dữ liệu (Đã có sẵn trong code của bạn, giữ nguyên phần options)
    objectives_in_project = Objective.query.options(
        subqueryload(Objective.key_results)
        .subqueryload(KeyResult.tasks)
        .joinedload(Task.assignee),
        joinedload(Objective.owner)
    ).filter(Objective.project_id == selected_project_id).order_by(Objective.position).all()

    # --- ĐOẠN THÊM MỚI: TÍNH TOÁN TRƯỚC TẠI BACKEND ---
    for obj in objectives_in_project:
        t_count = 0
        d_count = 0
        for kr in obj.key_results:
            tasks = kr.tasks
            t_count += len(tasks)
            d_count += sum(1 for t in tasks if t.status == 'Done')
        
        # Gán trực tiếp vào object để dùng ở template
        obj.total_tasks_count = t_count
        obj.done_tasks_count = d_count
        obj.progress_pct = (d_count * 100 / t_count) if t_count > 0 else 0
    # --- KẾT THÚC ĐOẠN THÊM MỚI ---

    objectives_by_build_id = defaultdict(list)
    for obj in objectives_in_project:
        objectives_by_build_id[obj.build_id].append(obj)

    okr_tab_data = {
        'all_builds': sorted(project.builds, key=lambda b: b.position),
        'objectives_by_build_id': objectives_by_build_id
    }
    
    today_date_obj = date.today()
    all_project_tasks_base_query = Task.query.join(KeyResult).join(Objective).filter(Objective.project_id == selected_project_id)

    selected_project_data = {
        'project': project,
        'stats': {
            'o': len(objectives_in_project),
            'kr': KeyResult.query.join(Objective).filter(Objective.project_id == selected_project_id).count(),
            'task': all_project_tasks_base_query.count(),
            'progress': project.progress,
            'open_tasks': all_project_tasks_base_query.filter(Task.status != 'Done').count()
        },
        'days_remaining': (project.end_date - today_date_obj).days if project.end_date else None,
        'logs': Log.query.order_by(Log.timestamp.desc()).limit(15).all()
    }
    context_data = {
        'filters': {}, 'grouped_tasks': {},
        'kanban_statuses': list(STATUS_META.keys()), 'status_meta': STATUS_META,
    }
    
    if active_tab == 'okr':
        context_data.update(okr_tab_data)

    elif active_tab == 'kanban':
        period = request.args.get('period', 'total')
        user_filter = request.args.get('user_id', 'all')
        overdue_filter = request.args.get('overdue')
        
        tasks_query = all_project_tasks_base_query.options(
            joinedload(Task.assignee), 
            joinedload(Task.attachments), 
            subqueryload(Task.sub_tasks)
        )

        if period == 'day': start_date, end_date = today_date_obj, today_date_obj
        elif period == 'month':
            start_date = today_date_obj.replace(day=1)
            end_date = start_date + timedelta(days=monthrange(today_date_obj.year, today_date_obj.month)[1] - 1)
        elif period == 'week':
            start_date = today_date_obj - timedelta(days=today_date_obj.weekday())
            end_date = start_date + timedelta(days=6)
        else:
            start_date, end_date = None, None

        if start_date and end_date: 
            tasks_query = tasks_query.filter(Task.task_date.between(start_date, end_date))
        
        if user_filter != 'all': 
            tasks_query = tasks_query.filter(Task.who_id == user_filter)
        
        if overdue_filter == '1': 
            tasks_query = tasks_query.filter(Task.task_date < today_date_obj, Task.status != 'Done')

        tasks_to_display = tasks_query.all()
        
        tasks_by_status = defaultdict(list)
        for task in tasks_to_display: 
            tasks_by_status[task.status].append(task)
        
        context_data['filters'] = {'user': user_filter, 'period': period, 'overdue': overdue_filter}
        context_data['grouped_tasks'] = dict(tasks_by_status)

    elif active_tab == 'calendar':
        view_mode = request.args.get('view_mode', 'month')
        date_str = request.args.get('date_str', today_date_obj.strftime('%Y-%m-%d'))
        start_date, end_date, date_display = get_date_range(view_mode, date_str)
        base_date = datetime.strptime(date_str, '%Y-%m-%d').date()

        # Logic điều hướng
        if view_mode == 'day':
            prev_period_date, next_period_date = (base_date - timedelta(days=1)).strftime('%Y-%m-%d'), (base_date + timedelta(days=1)).strftime('%Y-%m-%d')
        elif view_mode == 'week':
            prev_period_date, next_period_date = (start_date - timedelta(days=7)).strftime('%Y-%m-%d'), (start_date + timedelta(days=7)).strftime('%Y-%m-%d')
        else: # month
            prev_period_date, next_period_date = (start_date - timedelta(days=1)).replace(day=1).strftime('%Y-%m-%d'), (end_date + timedelta(days=1)).strftime('%Y-%m-%d')
        
        # Query tasks cho lịch
        calendar_dates = []
        if view_mode == 'month':
            start_of_month = base_date.replace(day=1)
            start_of_grid = start_of_month - timedelta(days=start_of_month.weekday())
            calendar_dates = [start_of_grid + timedelta(days=i) for i in range(42)]
            task_query_range = all_project_tasks_base_query.filter(Task.task_date.between(start_of_grid, calendar_dates[-1]))
        else:
            task_query_range = all_project_tasks_base_query.filter(Task.task_date.between(start_date, end_date))

        tasks_in_range = task_query_range.options(joinedload(Task.assignee)).order_by(Task.hour).all()
        
        tasks_by_date = defaultdict(list)
        for task in tasks_in_range:
            tasks_by_date[task.task_date.strftime('%Y-%m-%d')].append(task.to_dict())

        context_data.update({
            'view_mode': view_mode, 'date_str': date_str, 'date_display': date_display,
            'base_date': base_date, 'tasks_by_date': dict(tasks_by_date),
            'calendar_dates': calendar_dates, 'prev_period_date': prev_period_date,
            'next_period_date': next_period_date,
            'week_dates': [start_date + timedelta(days=i) for i in range(7)] if view_mode != 'month' else [],
            'week_days_display': [("Mon", "Mon"), ("Tue", "Tue"), ("Wed", "Wed"), ("Thu", "Thu"), ("Fri", "Fri"), ("Sat", "Sat"), ("Sun", "Sun")],
        })
    
    elif active_tab == 'files':
        context_data['files'] = UploadedFile.query.join(Task).join(KeyResult).join(Objective).filter(Objective.project_id == selected_project_id).order_by(UploadedFile.upload_date.desc()).all()


    return render_template('project_workspace.html',
                           page_name='projects',
                           selected_project_data=selected_project_data,
                           selected_project_id=selected_project_id,
                           active_tab=active_tab,
                           today_date_obj=today_date_obj,
                           **context_data
                           )
# ==============================================================================
# END: SỬA LỖI HÀM project_workspace
# ==============================================================================
# Thêm vào routes.py
@bp.route('/api/builds/update-order', methods=['POST'])
@login_required
def update_build_order():
    """API để lưu lại vị trí của các Build (Lists) khi kéo thả"""
    data = request.json
    build_ids = data.get('order', [])
    
    try:
        for index, b_id in enumerate(build_ids):
            build = Build.query.get(int(b_id))
            if build:
                build.position = index
        db.session.commit()
        return jsonify({'success': True, 'message': 'Build order updated.'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating build order: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@bp.route('/update-project/<int:project_id>', methods=['POST'])
@login_required
def update_project_details(project_id):
    project = Project.query.get_or_404(project_id)
    
    project.name = request.form.get('name')
    project.description = request.form.get('description')
    project.status = request.form.get('status')
    project.owner_id = request.form.get('owner_id') or None # <-- THÊM DÒNG NÀY
    project.note = request.form.get('note')
    project.plan_link = request.form.get('plan_link')    # <-- THÊM DÒNG NÀY
    start_date_str = request.form.get('start_date')
    end_date_str = request.form.get('end_date')
    project.start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
    project.end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None
    db.session.commit()
    
    flash(f'Project "{project.name}" updated successfully!', 'success')
    return redirect(url_for('main.project_workspace', project_id=project_id))

# app/routes.py

@bp.route('/delete-project/<int:project_id>', methods=['POST'])
@login_required
def delete_project(project_id):
    project = Project.query.get_or_404(project_id)
    try:
        db.session.delete(project)
        db.session.commit()
        flash(f'Project "{project.name}" deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting project: {str(e)}', 'danger')
    
    # SỬA LẠI DÒNG NÀY:
    return redirect(url_for('main.global_timeline'))

@bp.route('/add-build', methods=['POST'])
@login_required
def add_build():
    name = (request.form.get('name') or '').strip()
    project_id = request.form.get('project_id')
    start_date_str = (request.form.get('start_date') or '').strip()
    end_date_str = (request.form.get('end_date') or '').strip()
    schedule_link = (request.form.get('schedule_link') or '').strip()

    if not name or not project_id:
        flash('Build Name and Project are required.', 'danger')
        return redirect(request.referrer or url_for('main.global_timeline'))

    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None
    
    new_build = Build(
        name=name, 
        project_id=project_id,
        start_date=start_date,
        end_date=end_date,
        schedule_link=schedule_link,
        owner_id=request.form.get('owner_id') or None, # <-- THÊM DÒNG NÀY
        note=request.form.get('note'),
        report_link=request.form.get('report_link')        # <-- THÊM DÒNG NÀY
    )
    db.session.add(new_build)
    db.session.commit()
    flash('New build created!', 'success')
    return redirect(url_for('main.global_timeline', project_id=project_id, tab='info'))

@bp.route('/update-build/<int:build_id>', methods=['POST'])
@login_required
def update_build_details(build_id):
    build = Build.query.get_or_404(build_id)
    build.name = request.form.get('name')
    start_date_str = request.form.get('start_date')
    end_date_str = request.form.get('end_date')
    build.start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
    build.end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None
    
    build.owner_id = request.form.get('owner_id') or None # <-- THÊM DÒNG NÀY
    build.note = request.form.get('note') # <-- THÊM DÒNG NÀY
    build.schedule_link = request.form.get('schedule_link')
    build.report_link = request.form.get('report_link')

    db.session.commit()
    flash(f'Build "{build.name}" updated successfully!', 'success')
    return redirect(url_for('main.project_workspace', project_id=build.project_id))

@bp.route('/kanban')
@login_required
def kanban_board():
    period = request.args.get('period', 'week')
    user_filter = request.args.get('user_id', 'all')
    overdue_filter = request.args.get('overdue')
    
    today = date.today()
    if period == 'day':
        start_date = end_date = today
    elif period == 'month':
        start_date = today.replace(day=1)
        end_date = start_date + timedelta(days=monthrange(today.year, today.month)[1] - 1)
    elif period == 'total':
        start_date = None
        end_date = None
    else:
        start_date = today - timedelta(days=today.weekday())
        end_date = start_date + timedelta(days=6)

    tasks_query = Task.query.options(joinedload(Task.assignee), joinedload(Task.attachments))
    
    if start_date and end_date:
        tasks_query = tasks_query.filter(Task.task_date.between(start_date, end_date))
        
    if user_filter != 'all':
        tasks_query = tasks_query.filter(Task.who_id == user_filter)
        
    if overdue_filter == '1':
        tasks_query = tasks_query.filter(Task.task_date < today, Task.status != 'Done')
        
    all_tasks = tasks_query.order_by(Task.task_date.desc()).all()

    status_meta = {
        'Pending': {'color': '#6c757d', 'icon': 'fa-solid fa-hourglass-half'},
        'In Progress': {'color': '#3B82F6', 'icon': 'fa-solid fa-person-digging'},
        'Review': {'color': '#ffc107', 'icon': 'fa-solid fa-magnifying-glass'},
        'Done': {'color': '#28a745', 'icon': 'fa-solid fa-circle-check'},
        'Drop': {'color': '#dc3545', 'icon': 'fa-solid fa-circle-xmark'}
    }
    kanban_statuses = list(status_meta.keys())

    tasks_by_status = defaultdict(list)
    for task in all_tasks:
        tasks_by_status[task.status].append(task)

    summary_data = []
    tasks_by_user = defaultdict(lambda: {'tasks': [], 'status_counts': defaultdict(int)})
    for task in all_tasks:
        if task.assignee:
            user_key = task.assignee
            tasks_by_user[user_key]['tasks'].append(task)
            tasks_by_user[user_key]['status_counts'][task.status] += 1
            
    for user, data in tasks_by_user.items():
        summary_data.append({
            'user': user.to_dict(),
            'task_count': len(data['tasks']),
            'status_counts': dict(data['status_counts'])
        })
    summary_data.sort(key=lambda x: x['user']['username'])

    overall_status_counts = defaultdict(int)
    for task in all_tasks:
        overall_status_counts[task.status] += 1

    all_users = User.query.order_by(User.username).all()
    all_projects = Project.query.order_by(Project.name).all()
    all_builds = Build.query.order_by(Build.name).all()
    all_objectives = Objective.query.order_by(Objective.content).all()
    all_key_results = KeyResult.query.order_by(KeyResult.content).all()

    context = {
        'page_name': 'kanban',
        'title': 'Kanban Board',
        'grouped_tasks': dict(tasks_by_status),
        'kanban_statuses': kanban_statuses,
        'status_meta': status_meta,
        'users': all_users,
        'today_date_obj': today,
        'filters': {
            'user': user_filter, 
            'period': period, 
            'overdue': overdue_filter
        },
        'summary_data': summary_data,
        'overall_status_counts': dict(overall_status_counts),
        'all_projects': all_projects,
        'all_builds': all_builds,
        'all_objectives': all_objectives,
        'all_key_results': all_key_results
    }
    
    return render_template('kanban.html', **context)

@bp.route('/api/task/<int:task_id>/update-content', methods=['POST'])
@login_required
def update_task_content(task_id):
    task = Task.query.get_or_404(task_id)
    new_content = request.json.get('content', '').strip()
    if not new_content:
        return jsonify({'success': False, 'message': 'Must not empty'}), 400

    old_content, task.what = task.what, new_content
    db.session.add(Log(action=f"Update content job ID {task.id} from '{old_content}' to '{task.what}'.", user_id=current_user.id))
    db.session.commit()
    return jsonify({'success': True, 'message': 'Content updated!', 'new_content': task.what})
# BẮT ĐẦU KHỐI CODE DÀNH RIÊNG CHO NOTES - THAY THẾ TOÀN BỘ PHẦN NÀY

@bp.route('/notes')
@login_required
def notes():
    """
    Render trang Notes Board.
    - Dữ liệu note bây giờ đã bao gồm cả label từ DB.
    """
    all_columns = Column.query.order_by(Column.position).all()
    notes_by_column_id = defaultdict(list)
    
    # Tải sẵn thông tin creator để tối ưu
    all_notes = Note.query.options(joinedload(Note.creator)).order_by(Note.timestamp.desc()).all()
    for note in all_notes:
        notes_by_column_id[note.column_id].append(note)

    return render_template(
        'notes.html', 
        all_columns=all_columns, 
        notes_by_column_id=notes_by_column_id, 
        page_name='notes'
    )

@bp.route('/api/notes', methods=['POST'])
@login_required
def notes_api():
    """
    API để tạo một Note mới (card).
    - Đơn giản hóa để chỉ nhận title và column_id.
    """
    data = request.json
    title = data.get('title', '').strip()
    column_id = data.get('column_id')

    if not title or not column_id:
        return jsonify({'success': False, 'message': 'Title and column are required.'}), 400
    
    try:
        note = Note(
            title=title, 
            column_id=int(column_id),
            content="",
            creator_id=current_user.id,
            label=None # Label mặc định là null
        )
        db.session.add(note)
        db.session.commit()
        
        return jsonify({'success': True, 'note': note.to_dict(), 'message': 'Note created successfully!'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating note via API: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'An error occurred: {str(e)}'}), 500

# [TÌM VÀ THAY THẾ HÀM note_item_api TRONG routes.py]

@bp.route('/api/notes/<int:note_id>', methods=['GET', 'POST', 'PUT', 'DELETE'])
@login_required
def note_item_api(note_id):
    """
    API để xử lý một Note (card) cụ thể.
    - Đã fix lỗi không lưu Title/Content khi gửi JSON.
    """
    note = Note.query.get_or_404(note_id)

    if request.method == 'GET':
        return jsonify({'success': True, 'note': note.to_dict()})

    if request.method in ['POST', 'PUT']:
        try:
            # Cấu hình Sanitizer chung cho cả JSON và Form
            allowed_tags = list(bleach.ALLOWED_TAGS) + ['div', 'p', 'br', 'strong', 'em', 'u', 'ol', 'ul', 'li', 'img', 'a', 'span', 'table', 'thead', 'tbody', 'tr', 'td', 'th', 'colgroup', 'col', 'h1', 'h2', 'h3', 'h4', 'blockquote', 'code', 'pre', 'hr', 'input']
            allowed_attrs = {**bleach.ALLOWED_ATTRIBUTES, 'img': ['src', 'alt', 'style', 'width', 'height'], 'a': ['href', 'title', 'target'], '*': ['style', 'width', 'height', 'class', 'id', 'type', 'checked']}
            css_sanitizer = CSSSanitizer(allowed_css_properties=['color', 'background-color', 'text-align', 'font-weight', 'text-decoration', 'margin', 'padding'])

            if request.is_json:
                # --- [FIX QUAN TRỌNG] Xử lý dữ liệu JSON ---
                data = request.get_json()
                
                # Cập nhật thông tin cơ bản
                if 'title' in data: 
                    note.title = data['title']
                
                if 'content' in data: 
                    # Clean nội dung để tránh XSS nhưng giữ lại format
                    raw_content = data['content']
                    note.content = bleach.clean(raw_content, tags=allowed_tags, attributes=allowed_attrs, css_sanitizer=css_sanitizer)
                
                if 'column_id' in data: 
                    note.column_id = int(data['column_id'])
                
                # Cập nhật Label
                if 'label' in data:
                    valid_labels = ['Red', 'Green', 'Blue']
                    note.label = data['label'] if data['label'] in valid_labels else None

            else: 
                # --- Xử lý FormData (Khi có file đính kèm) ---
                data = request.form
                
                if 'title' in data: note.title = data['title']
                if 'content' in data: 
                    note.content = bleach.clean(data['content'], tags=allowed_tags, attributes=allowed_attrs, css_sanitizer=css_sanitizer)
                if 'column_id' in data: note.column_id = int(data['column_id'])
                
                # Upload file
                files = request.files.getlist('attachments[]')
                for file in files:
                    if file and file.filename != '':
                        original_filename = secure_filename(file.filename)
                        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
                        saved_filename = f"{timestamp}_{original_filename}"
                        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], saved_filename)
                        file.save(file_path)
                        file_size = os.path.getsize(file_path)
                        _, file_ext = os.path.splitext(original_filename)
                        new_file = UploadedFile(
                            original_filename=original_filename, saved_filename=saved_filename,
                            file_type=file_ext.lower(), file_size=file_size,
                            uploader_id=current_user.id, upload_source='attachment', note_id=note.id
                        )
                        db.session.add(new_file)
            
            db.session.commit()
            
            # Trả về data mới nhất để Frontend cập nhật UI ngay lập tức
            return jsonify({'success': True, 'message': 'Note updated!', 'note': note.to_dict()})
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating note {note_id}: {e}", exc_info=True)
            return jsonify({'success': False, 'message': f'Lỗi server: {str(e)}'}), 500

    if request.method == 'DELETE':
        # ... (Phần DELETE giữ nguyên)
        try:
            for attachment in note.attachments:
                try:
                    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], attachment.saved_filename)
                    if os.path.exists(file_path): os.remove(file_path)
                except Exception: pass
                db.session.delete(attachment)
            db.session.delete(note)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Note deleted'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500

# Các hàm xử lý Column không thay đổi
@bp.route('/api/columns', methods=['POST'])
@login_required
def create_column():
    data = request.json
    if not data or not data.get('name'):
        return jsonify({'success': False, 'message': 'Column name cannot be empty'}), 400
    max_pos = db.session.query(func.max(Column.position)).scalar() or -1
    new_column = Column(name=data['name'], position=max_pos + 1)
    db.session.add(new_column)
    db.session.commit()
    return jsonify({'success': True, 'column': {'id': new_column.id, 'name': new_column.name, 'position': new_column.position}})

@bp.route('/api/columns/<int:column_id>', methods=['DELETE'])
@login_required
def delete_column(column_id):
    column = Column.query.get_or_404(column_id)
    if column.notes:
        notes_in_column = Note.query.filter_by(column_id=column.id).all()
        for note in notes_in_column:
             db.session.delete(note)
    db.session.delete(column)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Column and its notes deleted'})

@bp.route('/api/columns/<int:column_id>/rename', methods=['POST'])
@login_required
def rename_column(column_id):
    column = Column.query.get_or_404(column_id)
    new_name = request.json.get('name', '').strip()
    if not new_name:
        return jsonify({'success': False, 'message': 'Column must be not empty'}), 400
    column.name = new_name
    db.session.commit()
    return jsonify({'success': True, 'new_name': column.name})

@bp.route('/api/columns/update-order', methods=['POST'])
@login_required
def update_column_order():
    column_ids = request.json.get('order', [])
    for index, col_id in enumerate(column_ids):
        column = Column.query.get(int(col_id))
        if column:
            column.position = index
    db.session.commit()
    return jsonify({'success': True, 'message': 'Arranged column'})

# KẾT THÚC KHỐI CODE DÀNH RIÊNG CHO NOTES


# ==============================================================================
# HÀM TRỢ GIÚP LẤY GIỜ VIỆT NAM
# ==============================================================================
VN_TZ = timezone(timedelta(hours=7))

def to_vn_time(dt):
    """Đổi timestamp trong DB (UTC/naive) sang giờ VN (aware)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(VN_TZ)

def get_vn_now():
    return datetime.now(VN_TZ)

def get_vn_today():
    return get_vn_now().date()

def _vn_day_bounds_to_utc(target_date: date):
    """Trả về [start_utc, end_utc) bao trùm 1 ngày theo giờ VN, đưa về UTC-naive để so sánh trong DB."""
    start_vn = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=VN_TZ)
    end_vn   = start_vn + timedelta(days=1)
    # DB của bạn là "timestamp without time zone" => so sánh naive UTC
    start_utc = start_vn.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc   = end_vn.astimezone(timezone.utc).replace(tzinfo=None)
    return start_utc, end_utc

def _vn_range_to_utc(start_date: date, end_date_inclusive: date):
    start_utc, _ = _vn_day_bounds_to_utc(start_date)
    _, end_utc   = _vn_day_bounds_to_utc(end_date_inclusive)
    return start_utc, end_utc
# ==============================================================================

# QUÁN TÂM (NHẬT KÝ TU TẬP)
# ==============================================================================

def calculate_streak(user_id):
    """Tính chuỗi ngày thực hành liên tục theo giờ VN."""
    rows = db.session.query(PracticeLog.log_ts).filter(PracticeLog.user_id == user_id).all()
    if not rows:
        return 0

    # Lấy tất cả ngày (giờ VN) đã có log
    logged_dates = {to_vn_time(ts).date() for (ts,) in rows}
    streak = 0
    cursor = get_vn_today()
    while cursor in logged_dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak

# -------------------------------
# DASHBOARD
# -------------------------------
@bp.route('/practice-log')
@login_required
def practice_log_dashboard():
    streak = calculate_streak(current_user.id)
    recent_logs = (PracticeLog.query
                   .filter_by(user_id=current_user.id)
                   .order_by(PracticeLog.log_ts.desc())
                   .limit(15).all())

    # render dùng giờ VN
    for log in recent_logs:
        log.log_ts = to_vn_time(log.log_ts)

    return render_template(
        'practice_log.html',
        page_name='practice_log',
        streak=streak,
        recent_logs=recent_logs,
        timedelta=timedelta
    )
@bp.route('/api/practice-log/<int:log_id>', methods=['GET'])
@login_required
def get_deep_log(log_id):
    """API để lấy chi tiết một ghi chép."""
    log = PracticeLog.query.filter_by(id=log_id, user_id=current_user.id).first_or_404()
    log_dict = log.to_dict()
    vn_time = to_vn_time(log.log_ts)
    log_dict['log_date'] = vn_time.strftime('%Y-%m-%d')
    log_dict['log_time_vn'] = vn_time.strftime('%H:%M')
    if 'tag' in log_dict and log_dict['tag']:
        log_dict['tag'] = log_dict['tag'].strip()
    return jsonify({'success': True, 'log': log_dict})

@bp.route('/api/practice-log/by-date')
@login_required
def get_logs_by_date():
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({'success': False, 'message': 'Thiếu ngày.'}), 400

    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'success': False, 'message': 'Định dạng ngày không hợp lệ.'}), 400

    start_utc, end_utc = _vn_day_bounds_to_utc(target_date)

    logs = (PracticeLog.query
            .filter(PracticeLog.user_id == current_user.id,
                    PracticeLog.log_ts >= start_utc,
                    PracticeLog.log_ts <  end_utc)
            .order_by(PracticeLog.log_ts.asc())
            .all())

    logs_list = []
    for log in logs:
        d = log.to_dict()
        vn_time = to_vn_time(log.log_ts)
        d['log_ts_vn']  = vn_time.isoformat()
        d['log_date']   = vn_time.strftime('%Y-%m-%d')
        d['log_time_vn']= vn_time.strftime('%H:%M')
        if d.get('tag'):
            d['tag'] = d['tag'].strip()
        logs_list.append(d)

    return jsonify({'success': True, 'logs': logs_list})

def _infer_tag_from_craving(craving_val: str) -> str:
    c = (craving_val or "").strip()
    if "Tham" in c:
        return "Tham"
    if "Sân" in c:
        return "Sân"
    if "Si" in c:
        return "Si"
    return "Chánh niệm"

@bp.route('/api/practice-log/save', methods=['POST'])
@login_required
def save_practice_log():
    data = request.form
    log_id = data.get('log_id')

    if log_id:
        log = PracticeLog.query.filter_by(id=log_id, user_id=current_user.id).first_or_404()
    else:
        log = PracticeLog(user_id=current_user.id)
        log_date_str = data.get('log_date')
        log_time_str = data.get('log_time', '00:00')
        if log_date_str:
            log_datetime_vn = datetime.strptime(f"{log_date_str} {log_time_str}", '%Y-%m-%d %H:%M').replace(tzinfo=VN_TZ)
            log.log_ts = log_datetime_vn.astimezone(timezone.utc).replace(tzinfo=None)  # lưu UTC-naive
        else:
            log.log_ts = get_vn_now().astimezone(timezone.utc).replace(tzinfo=None)

    log.situation     = (data.get('situation') or "").strip()
    log.sense_door    = (data.get('sense_door') or "").strip()
    log.contemplation = (data.get('contemplation') or "").strip()
    log.outcome       = (data.get('outcome') or "").strip()
    log.note          = (data.get('note') or "Quán chiếu sâu...").strip()

    active_tab_id = data.get('active_tab_id')
    def _extract(base):
        v = (data.get(base) or "").strip()
        if v: return v
        if active_tab_id:
            return (data.get(f"{base}_{active_tab_id}") or "").strip()
        return ""
    sense_object = _extract('sense_object')
    feeling      = _extract('feeling')
    craving      = _extract('craving')

    if sense_object or not log_id: log.sense_object = sense_object
    if feeling or not log_id:      log.feeling      = feeling
    if craving or not log_id:      log.craving      = craving

    # Ưu tiên suy ra tag từ Ái
    def _infer_tag_from_craving(c: str) -> str:
        c = (c or "").strip()
        if "Tham" in c: return "Tham"
        if "Sân"  in c: return "Sân"
        if "Si"   in c: return "Si"
        return ""

    incoming_tag = (data.get('tag') or "").strip()
    inferred = _infer_tag_from_craving(craving)
    if inferred:
        log.tag = inferred
    elif incoming_tag:
        log.tag = incoming_tag
    else:
        if not log_id:
            log.tag = "Chánh niệm"

    if not log_id:
        db.session.add(log)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Đã lưu lại quán chiếu.', 'final_tag': log.tag})


@bp.route('/api/practice-log/<int:log_id>', methods=['DELETE'])
@login_required
def delete_practice_log(log_id):
    """API để xóa một ghi chép."""
    log = PracticeLog.query.filter_by(id=log_id, user_id=current_user.id).first_or_404()
    db.session.delete(log)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Đã xóa quán chiếu thành công.'})

@bp.route('/api/practice-log/chart-data')
@login_required
def get_chart_data():
    days = request.args.get('days', 30, type=int)
    end_date = get_vn_today()
    start_date = end_date - timedelta(days=days - 1)
    start_utc, end_utc = _vn_range_to_utc(start_date, end_date)

    rows = (PracticeLog.query
            .filter(PracticeLog.user_id == current_user.id,
                    PracticeLog.log_ts >= start_utc,
                    PracticeLog.log_ts <  end_utc)
            .with_entities(PracticeLog.log_ts, PracticeLog.tag)
            .all())

    core_tags = {'Tham', 'Sân', 'Si', 'Chánh niệm'}
    # trend_counts[date_str][tag] = count
    trend_counts = {}
    today_counts = {}

    for ts, tag in rows:
        tag = (tag or '').strip()
        d_vn = to_vn_time(ts).date()
        d_key = d_vn.strftime('%Y-%m-%d')

        trend_counts.setdefault(d_key, {})
        trend_counts[d_key][tag] = trend_counts[d_key].get(tag, 0) + 1

        if d_vn == end_date:
            today_counts[tag] = today_counts.get(tag, 0) + 1

    # build trend_data: chỉ xuất các core tag
    trend_data = []
    for i in range(days):
        d = start_date + timedelta(days=i)
        d_key = d.strftime('%Y-%m-%d')
        counts = trend_counts.get(d_key, {})
        for t in core_tags:
            c = counts.get(t, 0)
            if c:
                trend_data.append({'date': d_key, 'tag': t, 'count': c})

    return jsonify({'trend_data': trend_data, 'today_pie_data': today_counts})
# --- THAY THẾ BẰNG ĐOẠN NÀY ---
@bp.route('/api/practice-log/calendar-view') # <--- QUAN TRỌNG: THÊM DÒNG NÀY
@login_required
def get_practice_calendar_data():
    try:
        vn_now = get_vn_now()
        year  = request.args.get('year', vn_now.year, type=int)
        month = request.args.get('month', vn_now.month, type=int)

        month_start = date(year, month, 1)
        # ngày cuối tháng
        if month == 12:
            next_month_start = date(year + 1, 1, 1)
        else:
            next_month_start = date(year, month + 1, 1)
        month_end = next_month_start - timedelta(days=1)

        start_utc, end_utc = _vn_range_to_utc(month_start, month_end)

        # 1. Lấy dữ liệu Quán chiếu (Deep Logs)
        log_rows = (PracticeLog.query
                .filter(PracticeLog.user_id == current_user.id,
                        PracticeLog.log_ts >= start_utc,
                        PracticeLog.log_ts <  end_utc)
                .with_entities(PracticeLog.log_ts)
                .all())

        # 2. Lấy dữ liệu Thói quen (Habit Logs) - Đã hoàn thành
        habit_rows = (HabitLog.query
                .join(Habit)
                .filter(Habit.user_id == current_user.id,
                        HabitLog.date_logged >= month_start,
                        HabitLog.date_logged <= month_end,
                        HabitLog.is_done == True)
                .with_entities(HabitLog.date_logged)
                .all())

        # 3. Tổng hợp dữ liệu theo ngày
        # Cấu trúc: 'YYYY-MM-DD': {'logs': count, 'habits': count}
        calendar_data = defaultdict(lambda: {'logs': 0, 'habits': 0})

        for (ts,) in log_rows:
            d_key = to_vn_time(ts).date().strftime('%Y-%m-%d')
            calendar_data[d_key]['logs'] += 1
            
        for (d_date,) in habit_rows:
            d_key = d_date.strftime('%Y-%m-%d')
            calendar_data[d_key]['habits'] += 1

        return jsonify({'success': True, 'calendar_data': calendar_data})
    except Exception as e:
        current_app.logger.error(f"Calendar Error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
@bp.route('/api/habits/update', methods=['POST'])
@login_required
def update_habit():
    try:
        data = request.json
        habit_id = data.get('habit_id')
        new_name = data.get('name')
        
        if not habit_id or not new_name:
            return jsonify({'success': False, 'message': 'Thiếu thông tin'}), 400
            
        habit = Habit.query.filter_by(id=habit_id, user_id=current_user.id).first_or_404()
        habit.name = new_name.strip()
        
        db.session.commit()
        return jsonify({'success': True, 'habit': habit.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@bp.route('/api/practice-log/recent-logs')
@login_required
def get_recent_logs():
    """API để lấy 15 ghi nhận mới nhất dưới dạng JSON."""
    recent_logs = PracticeLog.query.filter_by(user_id=current_user.id)\
        .order_by(PracticeLog.log_ts.desc()).limit(15).all()

    logs_list = []
    for log in recent_logs:
        log_dict = log.to_dict()
        vn_time = to_vn_time(log.log_ts)
        
        # --- SỬA: Bổ sung log_date để frontend dùng ---
        log_dict['log_ts_vn'] = vn_time.isoformat()
        log_dict['log_date'] = vn_time.strftime('%Y-%m-%d') # <--- DÒNG QUAN TRỌNG
        log_dict['log_time_vn'] = vn_time.strftime('%H:%M')
        
        if 'tag' in log_dict and log_dict['tag']:
            log_dict['tag'] = log_dict['tag'].strip()
        logs_list.append(log_dict)

    return jsonify({'success': True, 'logs': logs_list})

@bp.route('/api/all-okr-data')
@login_required
def all_okr_data():
    projects = Project.query.order_by(Project.name).all()
    builds = Build.query.order_by(Build.name).all()
 
    objectives = Objective.query.options(subqueryload(Objective.key_results)).order_by(Objective.content).all()
    key_results = KeyResult.query.order_by(KeyResult.content).all()

    projects_list = [{'id': p.id, 'name': p.name, 'builds': [{'id': b.id, 'name': b.name} for b in p.builds]} for p in projects]
    builds_dict = {b.id: {'id': b.id, 'name': b.name, 'project_id': b.project_id} for b in builds}
    objectives_dict = {o.id: {'id': o.id, 'content': o.content, 'build_id': o.build_id, 'key_results': [{'id': kr.id, 'content': kr.content} for kr in o.key_results]} for o in objectives}
    key_results_dict = {kr.id: {'id': kr.id, 'content': kr.content, 'objective_id': kr.objective_id} for kr in key_results}
    
    return jsonify({
        'projects': projects_list,
        'builds': builds_dict,
        'objectives': objectives_dict,
        'key_results': key_results_dict
    })

@bp.route('/api/project/<int:project_id>')
@login_required
def api_get_project(project_id):
    project = Project.query.get_or_404(project_id)
    return jsonify({
        'id': project.id,
        'name': project.name,
        'description': project.description,
        'start_date': project.start_date.isoformat() if project.start_date else '',
        'end_date': project.end_date.isoformat() if project.end_date else '',
        'status': project.status,
        'owner_id': project.owner_id or '', # <-- THÊM DÒNG NÀY
        'note': project.note or '', # <-- THÊM DÒNG NÀY
        'plan_link': project.plan_link or '' # <<< THÊM DÒNG NÀY
    })

@bp.route('/api/build/<int:build_id>')
@login_required
def api_get_build(build_id):
    build = Build.query.get_or_404(build_id)
    return jsonify({
        'id': build.id,
        'name': build.name,
        'project_id': build.project_id,
        'start_date': build.start_date.isoformat() if build.start_date else '',
        'end_date': build.end_date.isoformat() if build.end_date else '',
        'schedule_link': build.schedule_link or '',
        'owner_id': build.owner_id or '', # <-- THÊM DÒNG NÀY
        'note': build.note or '',
        'report_link': build.report_link or ''        # <-- THÊM DÒNG NÀY
    })
@bp.route('/api/gantt-data')
@login_required
def gantt_data():
    project_id = request.args.get('project_id', type=int)
    view_mode = request.args.get('view', 'detailed') # 'detailed' or 'overview'
    
    query = Project.query.options(
        joinedload(Project.builds)
        .joinedload(Build.objectives)
        .joinedload(Objective.key_results)
        .joinedload(KeyResult.tasks)
    )

    if project_id:
        query = query.filter(Project.id == project_id)

    projects = query.all()
    gantt_tasks = []

    for project in projects:
        if project.start_date and project.end_date:
            gantt_tasks.append({
                'id': f'proj-{project.id}', 'name': project.name,
                'start': project.start_date.isoformat(), 'end': project.end_date.isoformat(),
                'progress': 0, 'custom_class': 'gantt-project'
            })

        for build in project.builds:
            if build.start_date and build.end_date:
                gantt_tasks.append({
                    'id': f'build-{build.id}', 'name': build.name,
                    'start': build.start_date.isoformat(), 'end': build.end_date.isoformat(),
                    'progress': 0, 'dependencies': f'proj-{project.id}',
                    'custom_class': 'gantt-build'
                })

        if view_mode == 'detailed':
            all_tasks_in_project = [task for o in project.objectives for kr in o.key_results for task in kr.tasks]
            for task in all_tasks_in_project:
                if task.task_date:
                    task_progress = 100 if task.status == 'Done' else 0
                    end_date = task.task_date + timedelta(days=1)
                    parent_build_id = task.key_result.objective.build_id if task.key_result and task.key_result.objective else None
                    dependency = f'build-{parent_build_id}' if parent_build_id else f'proj-{project.id}'

                    gantt_tasks.append({
                        'id': f'task-{task.id}', 'name': task.what,
                        'start': task.task_date.isoformat(), 'end': end_date.isoformat(),
                        'progress': task_progress, 'dependencies': dependency
                    })

    return jsonify(gantt_tasks)

@bp.route('/timeline')
@login_required
def timeline_page():
    project_id = request.args.get('project_id', type=int)
    project_name = "All Projects"
    if project_id:
        project = Project.query.get(project_id)
        if project:
            project_name = project.name
            
    return render_template('timeline.html', 
                           page_name='timeline', 
                           project_id=project_id, 
                           project_name=project_name)


# NÂNG CẤP API ĐỂ CUNG CẤP THÊM DỮ LIỆU CHO VIỆC TÔ MÀU
def calculate_progress(tasks):
    if not tasks:
        return 0.0
    done_count = sum(1 for t in tasks if t.status == 'Done')
    return round(done_count / len(tasks), 4)  # làm tròn 4 chữ số để Gantt mượt hơn


@bp.route('/api/kr-context/<int:kr_id>')
@login_required
def get_kr_context(kr_id):
    """
    API để lấy thông tin ngữ cảnh đầy đủ của một Key Result.
    Trả về project_id, build_id, objective_id, và kr_id.
    """
    kr = KeyResult.query.options(
        joinedload(KeyResult.objective)
        .joinedload(Objective.build)
        .joinedload(Build.project)
    ).get_or_404(kr_id)

    if not kr.objective or not kr.objective.build or not kr.objective.build.project:
        return jsonify({'success': False, 'message': 'Context information is incomplete for this KR.'}), 404

    return jsonify({
        'success': True,
        'context': {
            'project_id': kr.objective.build.project.id,
            'build_id': kr.objective.build.id,
            'objective_id': kr.objective.id,
            'key_result_id': kr.id
        }
    })
@bp.route('/gantt')
def gantt_redirect():
    project_id = request.args.get('project_id')
    if project_id:
        return redirect(url_for('main.timeline_page', project_id=project_id))
    return redirect(url_for('main.timeline_page'))

@bp.route('/api/key-result/<int:kr_id>')
@login_required
def api_get_key_result(kr_id):
    kr = KeyResult.query.get_or_404(kr_id)
    return jsonify({
        'success': True,
        'key_result': {
            'id': kr.id,
            'content': kr.content,
            'owner_id': kr.owner_id or '',
            'note': kr.note or '',
            'start_date': kr.start_date.isoformat() if kr.start_date else '',
            'end_date': kr.end_date.isoformat() if kr.end_date else ''
        }
    })
# =========================================================

@bp.route('/api/objectives/update-order', methods=['POST'])
@login_required
def update_objective_order():
    data = request.json
    objective_ids = data.get('order', [])

    if not objective_ids:
        return jsonify({'success': False, 'message': 'No order data received.'}), 400

    try:
        for index, obj_id in enumerate(objective_ids):
            objective = Objective.query.get(int(obj_id))
            if objective:
                objective.position = index
        db.session.commit()
        return jsonify({'success': True, 'message': 'Objective order updated successfully.'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating objective order: {e}")
        return jsonify({'success': False, 'message': 'An error occurred.'}), 500


@bp.route('/global-timeline')
@login_required
def global_timeline():
    """Render trang Global Timeline mới với cả 2 view: Timeline và Kanban."""
    view_mode = request.args.get('view', 'timeline')

    users = db.session.scalars(select(User).order_by(User.username)).all()
    all_builds_for_modal = db.session.scalars(select(Build).order_by(Build.name)).all()
    status_choices = ['Planned', 'Active', 'On Hold', 'Done']

    # Query dữ liệu Projects, tải sẵn các builds và owner của build
    # để tối ưu cho cả 2 view, đặc biệt là Kanban.
    projects = Project.query.options(
        subqueryload(Project.builds).joinedload(Build.owner)
    ).order_by(Project.position, Project.name).all()

    return render_template(
        'global_timeline.html',
        page_name='global_timeline',
        users=users,
        projects=projects,
        status_choices=status_choices,
        builds=all_builds_for_modal,
        selected_project_id=None,
        view_mode=view_mode # Biến quan trọng để điều khiển view
    )

# THÊM ROUTE API MỚI NÀY
@bp.route('/api/build/update-project', methods=['POST'])
@login_required
def update_build_project():
    """API để cập nhật Project của một Build khi kéo-thả trên Kanban."""
    data = request.json
    build_id = data.get('build_id')
    new_project_id = data.get('project_id')

    if not build_id or not new_project_id:
        return jsonify({'success': False, 'message': 'Missing build_id or project_id.'}), 400

    build = Build.query.get(build_id)
    if not build:
        return jsonify({'success': False, 'message': 'Build not found.'}), 404

    build.project_id = int(new_project_id)
    try:
        db.session.commit()
        return jsonify({'success': True, 'message': 'Build moved successfully.'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error moving build {build_id} to project {new_project_id}: {e}")
        return jsonify({'success': False, 'message': f'Database error: {str(e)}'}), 500
# === VIS-TIMELINE ROADMAP ===

@bp.route('/global-roadmap')
@login_required
def global_roadmap():
    # Trang hiển thị roadmap (dùng vis-timeline)
    return render_template('global_timeline.html', page_name='global_roadmap')

@bp.route('/vis-roadmap-data')
@login_required
def vis_roadmap_data():
    """
    API cung cấp dữ liệu cho vis-timeline.
    *** NÂNG CẤP: Thêm logic để lọc các project đã hoàn thành (Done) ***
    """
    try:
        # Lấy trạng thái của bộ lọc từ URL, mặc định là hiển thị tất cả (true)
        show_done = request.args.get('show_done', 'true').lower() == 'true'

        def add_days(d, days): return (d + timedelta(days=days)) if d else None
        def phase_class(name: str) -> str:
            if not name: return ""
            n = name.lower().strip()
            if n.startswith("p1"): return "phase-p1"
            if n.startswith("p2"): return "phase-p2"
            if n.startswith("e1") or n.startswith("e"): return "phase-e1"
            if n.startswith("e2"): return "phase-e2"
            if n.startswith("d1") or n.startswith("d"): return "phase-d1"
            if "pvt" in n: return "phase-pvt"
            return "phase-poc"

        # Xây dựng câu truy vấn cơ bản
        projects_query = Project.query.options(subqueryload(Project.builds))

        # Nếu người dùng không muốn xem project "Done", thêm điều kiện lọc
        if not show_done:
            projects_query = projects_query.filter(Project.status != 'Done')

        # Áp dụng sắp xếp và thực thi truy vấn
        projects = projects_query.order_by(Project.start_date.asc().nullslast(), Project.name.asc()).all()
        
        groups, items = [], []

        for index, p in enumerate(projects):
            groups.append({
                "id": p.id, 
                "content": p.name or f"Project {p.id}",
                "order": index
            })

            builds_with_dates = sorted(
                [b for b in p.builds if b.start_date and b.end_date], 
                key=lambda x: x.start_date
            )

            for b in builds_with_dates:
                label = (b.name or "Build").strip()
                items.append({
                    "id": f"build-{b.id}",
                    "group": p.id,
                    "content": label,
                    "start": b.start_date.isoformat(),
                    "end": add_days(b.end_date, 1).isoformat(),
                    "className": f"phase {phase_class(b.name)}",
                    "title": f"{p.name} • {label} • {b.start_date} → {b.end_date}",
                    "project_id": p.id,
                })
        
        return jsonify({"success": True, "groups": groups, "items": items})

    except Exception as e:
        current_app.logger.error(f"Error in vis_roadmap_data: {e}", exc_info=True)
        return jsonify({"success": False, "message": f"An internal server error occurred. Please check server logs."}), 500

@bp.route('/milestone')
@login_required
def milestone():
    """
    Route để hiển thị trang vẽ timeline kiểu Milestone (sự kiện).
    """
    return render_template('milestone.html')


@bp.route('/manual_timeline') # <-- Anh đã có dòng này rồi, nhưng tên blueprint có thể khác
@login_required
def manual_timeline():
    """
    Route để hiển thị trang vẽ timeline bằng tay.
    """
    return render_template('manual_timeline.html')
# app/routes.py
@bp.route('/delete-build/<int:build_id>', methods=['POST'])
@login_required
def delete_build(build_id):
    build = Build.query.get_or_404(build_id)
    project_id_redirect = build.project_id
    try:
        db.session.delete(build)
        db.session.commit()
        flash(f'List "{build.name}" was deleted.', 'success')
        return jsonify({'success': True, 'message': 'List deleted successfully.'})
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting list: {str(e)}', 'danger')
        return jsonify({'success': False, 'message': str(e)}), 500

def process_summary_file(project_id):
    """
    Sửa lại: Không còn phụ thuộc vào bảng Build, lưu trực tiếp build_name.
    """
    project = Project.query.get(project_id)
    if not project:
        current_app.logger.error(f"process_summary_file: Không tìm thấy project ID {project_id}")
        return False, "Project not found"

    try:
        file_name = 'project_summary.xlsx'
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], file_name)
        
        if not os.path.exists(file_path):
            current_app.logger.error(f"File summary không tồn tại: {file_path}")
            return False, "Summary file not found at the configured static path."
            
        df = pd.read_excel(file_path, engine='openpyxl')
    except Exception as e:
        current_app.logger.error(f"Lỗi khi đọc file Excel tại {file_path}: {e}", exc_info=True)
        return False, f"Error reading the Excel file: {e}"

    try:
        df.columns = df.columns.str.strip().str.lower()
        column_map = {
            'project': 'project_name', 'build': 'build_name',
            'process': 'process', 'quantity': 'quantity', 
            'yield': 'yield_rate', 'result': 'result', 'status': 'status',
            'reason': 'reason', 'action': 'action', 'yrt': 'yrt',
            'quantity_yield': 'quantity_yield'
        }
        df.rename(columns=column_map, inplace=True)
        
        if 'project_name' not in df.columns or 'build_name' not in df.columns:
            return False, "Excel file is missing 'Project' or 'Build' column."
        
        project_df = df[df['project_name'] == project.name].copy()
        
        if project_df.empty:
            ProductionData.query.filter_by(project_id=project_id).delete()
            db.session.commit()
            return True, f"No data found for project '{project.name}'."

        ProductionData.query.filter_by(project_id=project_id).delete()

        new_data_list = []
        for index, row in project_df.iterrows():
            build_name = row.get('build_name')
            # Bỏ qua dòng nếu không có build_name
            if not build_name:
                continue

            row_data = row.where(pd.notnull(row), None).to_dict()
            allowed_keys = ['build_name', 'process', 'quantity', 'result', 'yrt', 'yield_rate', 'reason', 'action', 'status', 'quantity_yield']
            filtered_data = {k: v for k, v in row_data.items() if k in allowed_keys}
            
            new_data = ProductionData(project_id=project_id, **filtered_data)
            new_data_list.append(new_data)

        if new_data_list:
            db.session.bulk_save_objects(new_data_list)
        
        db.session.commit()
        return True, "Data processed successfully"
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Lỗi khi xử lý dữ liệu DB cho project {project.name}: {e}", exc_info=True)
        return False, f"Database error during import: {e}"


@bp.route('/api/project/<int:project_id>/dashboard_analytics')
@login_required
def get_dashboard_analytics(project_id):
    """
    CHỈ ĐỌC DATA TỪ DATABASE: Siêu nhanh, không đụng vào file Excel.
    """
    try:
        # [ĐÃ XÓA] success, message = process_summary_file(project_id) -> Không tự auto-quét Excel nữa
        
        # Chỉ query thẳng vào DB (ProductionData)
        data_query = db.session.query(
            ProductionData.process, ProductionData.build_name,
            ProductionData.quantity, ProductionData.quantity_yield,
            ProductionData.result, ProductionData.yrt, ProductionData.yield_rate
        ).filter(ProductionData.project_id == project_id).all()

        if not data_query:
            return jsonify({"message": "No data available for this project."}), 200

        df = pd.DataFrame(data_query, columns=[
            'process', 'build_name', 'quantity', 'quantity_yield', 
            'result', 'yrt', 'yield_rate'
        ])
        
        # Xử lý an toàn NaN cho Dashboard (Code cũ giữ nguyên)
        numeric_cols = ['quantity', 'quantity_yield', 'yrt', 'yield_rate']
        df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors='coerce').fillna(0)

        selected_build = request.args.get('build')
        selected_process = request.args.get('process')
        selected_result = request.args.get('result')

        all_builds = df['build_name'].drop_duplicates().tolist()
        all_processes = sorted(df['process'].unique().tolist())
        all_results = sorted(df['result'].unique().tolist())
        result_map = df.groupby('process')['result'].unique().apply(list).to_dict()
        result_map['all'] = all_results
        
        df_ng_full = df[df['result'] != 'OK'].copy()
        pareto_df = df_ng_full.copy()
        
        if selected_build and selected_build != 'all':
            pareto_df = pareto_df[pareto_df['build_name'] == selected_build]
        if selected_process and selected_process != 'all':
            pareto_df = pareto_df[pareto_df['process'] == selected_process]
        
        pareto_charts_data = {}
        if not pareto_df.empty:
            for metric in ['quantity', 'quantity_yield']:
                pareto_agg = pareto_df.groupby('result')[metric].sum().sort_values(ascending=False)
                pareto_charts_data[metric] = {"labels": pareto_agg.index.tolist(), "values": pareto_agg.values.tolist()}

        analysis_chart_data = None
        df_analysis = df.copy()

        if selected_result == 'OK':
            analysis_chart_data = {"type": "ok", "details": {}}
            processes_to_run = all_processes if not selected_process or selected_process == 'all' else [selected_process]
            for process_name in processes_to_run:
                df_proc = df_analysis[df_analysis['process'] == process_name]
                if df_proc.empty: continue
                
                base_agg_df = df_proc.groupby('build_name').agg({
                    'quantity': 'sum', 'quantity_yield': 'sum',
                    'yrt': 'mean', 'yield_rate': 'mean'
                }).reindex(all_builds).fillna(0)
                
                ok_qty = df_proc[df_proc['result'] == 'OK'].groupby('build_name')['quantity'].sum().reindex(all_builds).fillna(0)
                ok_yield_qty = df_proc[df_proc['result'] == 'OK'].groupby('build_name')['quantity_yield'].sum().reindex(all_builds).fillna(0)
                
                yrt_rate = (ok_qty * 100 / base_agg_df['quantity']).replace([float('inf'), -float('inf')], 0).fillna(0).round(2)
                yield_rate = (ok_yield_qty * 100 / base_agg_df['quantity_yield']).replace([float('inf'), -float('inf')], 0).fillna(0).round(2)
                
                analysis_chart_data["details"][process_name] = {
                    "labels": all_builds,
                    "total_quantity": base_agg_df['quantity'].tolist(),
                    "total_quantity_yield": base_agg_df['quantity_yield'].tolist(),
                    "yrt_rate": yrt_rate.tolist(),
                    "yield_rate": yield_rate.tolist()
                }
        elif selected_result:
            if selected_process and selected_process != 'all':
                df_analysis = df_analysis[df_analysis['process'] == selected_process]
                
            analysis_final_data = {"type": "ng", "labels": all_builds}
            
            for metric in ['quantity', 'quantity_yield']:
                total_by_build = df_analysis.groupby('build_name')[metric].sum()
                failure_by_build = df_analysis[df_analysis['result'] == selected_result].groupby('build_name')[metric].sum()
                
                trend_df = pd.DataFrame(index=all_builds)
                trend_df['total'] = total_by_build
                trend_df['failure'] = failure_by_build
                trend_df = trend_df.fillna(0)
                
                trend_df['rate'] = (trend_df['failure'] * 100 / trend_df['total']).replace([float('inf'), -float('inf')], 0).fillna(0).round(2)
                
                analysis_final_data[f'failure_{metric}'] = trend_df['failure'].tolist()
                analysis_final_data[f'rate_{metric}'] = trend_df['rate'].tolist()
                
            analysis_chart_data = analysis_final_data
            
        return jsonify({
            "pareto_charts": pareto_charts_data,
            "analysis_chart": analysis_chart_data,
            "filters": {
                "builds": all_builds,
                "processes": all_processes,
                "results": all_results
            },
            "result_map": result_map
        })

    except Exception as e:
        current_app.logger.error(f"Lỗi nghiêm trọng trong get_dashboard_analytics: {e}", exc_info=True)
        return jsonify({"error": f"An unexpected server error occurred: {e}"}), 500


# THÊM API MỚI NÀY ĐỂ KÍCH HOẠT QUÉT EXCEL CHO DASHBOARD
@bp.route('/api/project/<int:project_id>/dashboard/sync', methods=['POST'])
@login_required
def sync_dashboard_data(project_id):
    """API riêng biệt gọi hàm process_summary_file() để cày lại Excel"""
    try:
        success, message = process_summary_file(project_id)
        if success:
            return jsonify({'success': True, 'message': 'Đã đồng bộ Project Summary mới nhất từ Excel!'})
        else:
            return jsonify({'success': False, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

        
# ==============================================================================
# SALARY MANAGEMENT ROUTES (MỚI)
# ==============================================================================

@bp.route('/salary_calculator')
@login_required
def salary_calculator():
    # Lấy config hiện tại để fill vào form
    config = SalaryConfig.query.filter_by(user_id=current_user.id).first()
    return render_template('salary_calculator.html', config=config, page_name='salary_calculator')

@bp.route('/api/salary/config', methods=['POST'])
@login_required
def save_salary_config():
    data = request.json
    try:
        config = SalaryConfig.query.filter_by(user_id=current_user.id).first()
        if not config:
            config = SalaryConfig(user_id=current_user.id)
            db.session.add(config)
        
        config.base_salary_gross = float(data.get('base_salary_gross', 0))
        config.insurance_salary = float(data.get('insurance_salary', 0))
        config.dependents_count = int(data.get('dependents_count', 0))
        config.region = int(data.get('region', 1))
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Đã lưu cấu hình lương.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@bp.route('/api/salary/year-data', methods=['GET'])
@login_required
def get_salary_year_data():
    year = request.args.get('year', datetime.now().year, type=int)
    
    # Lấy dữ liệu 12 tháng
    monthly_data = MonthlySalary.query.filter_by(user_id=current_user.id, year=year).all()
    data_map = {m.month: {
        'id': m.id,
        'gross_income': m.gross_income,
        'insurance_deducted': m.insurance_deducted,
        'tax_deducted': m.tax_deducted,
        'net_income': m.net_income,
        'other_deductions': m.other_deductions,
        'note': m.note
    } for m in monthly_data}
    
    # Fill các tháng thiếu
    result = []
    for m in range(1, 13):
        # Nếu chưa có dữ liệu DB, trả về default 0
        item = data_map.get(m, {
            'month': m,
            'gross_income': 0,
            'insurance_deducted': 0,
            'tax_deducted': 0,
            'net_income': 0,
            'other_deductions': 0,
            'note': ''
        })
        item['month'] = m
        result.append(item)
        
    return jsonify({'success': True, 'data': result, 'year': year})

@bp.route('/api/salary/month', methods=['POST'])
@login_required
def save_monthly_salary():
    data = request.json
    year = int(data.get('year'))
    month = int(data.get('month'))
    
    try:
        record = MonthlySalary.query.filter_by(user_id=current_user.id, year=year, month=month).first()
        if not record:
            record = MonthlySalary(user_id=current_user.id, year=year, month=month)
            db.session.add(record)
            
        record.gross_income = float(data.get('gross_income', 0))
        record.insurance_deducted = float(data.get('insurance_deducted', 0))
        record.tax_deducted = float(data.get('tax_deducted', 0))
        record.net_income = float(data.get('net_income', 0))
        record.other_deductions = float(data.get('other_deductions', 0))
        record.note = data.get('note', '')
        
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})
@bp.route('/api/build/add', methods=['POST'])
@login_required
def api_add_build():
    """API để tạo nhanh một Build mới từ Kanban board."""
    data = request.json
    name = (data.get('name') or '').strip()
    project_id = data.get('project_id')

    if not name or not project_id:
        return jsonify({'success': False, 'message': 'Build name and project are required.'}), 400

    try:
        # Lấy project để đảm bảo project_id hợp lệ
        project = Project.query.get_or_404(project_id)
        
        new_build = Build(
            name=name, 
            project_id=project.id,
            owner_id=current_user.id # Mặc định gán cho người tạo
        )
        db.session.add(new_build)
        db.session.commit()
        
        # Trả về dữ liệu của build vừa tạo để frontend render
        return jsonify({'success': True, 'build': new_build.to_dict()})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating build via API: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@bp.route('/api/build/<int:build_id>/rename', methods=['POST'])
@login_required
def api_rename_build(build_id):
    """API để đổi tên nhanh một Build."""
    build = Build.query.get_or_404(build_id)
    new_name = (request.json.get('name') or '').strip()

    if not new_name:
        return jsonify({'success': False, 'message': 'Name cannot be empty.'}), 400
    
    try:
        build.name = new_name
        db.session.commit()
        return jsonify({'success': True, 'message': 'Build renamed successfully.'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error renaming build {build_id}: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
# === START: CẬP NHẬT HÀM HOME ĐỂ THAY THẾ GLOBAL_TIMELINE ===
# === START: CẬP NHẬT HÀM HOME (AUDIT TIẾN ĐỘ) ===
@bp.route('/home')
@login_required
def home():
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    # 1. Xác định bộ lọc người dùng
    selected_user_id = request.args.get('user_id', str(current_user.id))

    # 2. Query Task cơ bản
    tasks_base_query = Task.query.options(
        joinedload(Task.key_result).joinedload(KeyResult.objective).joinedload(Objective.project)
    )
    
    if selected_user_id == 'all':
        pass 
    elif selected_user_id.isdigit():
        tasks_base_query = tasks_base_query.filter(Task.who_id == int(selected_user_id))
    else:
        selected_user_id = str(current_user.id)
        tasks_base_query = tasks_base_query.filter(Task.who_id == current_user.id)

    # 3. Lấy danh sách task và phân loại
    open_tasks_list = tasks_base_query.filter(Task.status.notin_(['Done', 'Drop'])).order_by(Task.task_date.asc().nullslast()).all()
    
    categorized_tasks = {
        'Overdue': [t for t in open_tasks_list if t.task_date and t.task_date < today],
        'Today': [t for t in open_tasks_list if t.task_date == today],
        'This Week': [t for t in open_tasks_list if t.task_date and today < t.task_date <= end_of_week],
        'Later': [t for t in open_tasks_list if t.task_date and t.task_date > end_of_week],
        'No Due Date': [t for t in open_tasks_list if not t.task_date]
    }
    
    # 4. [AUDIT LOGIC] TÍNH TOÁN TIẾN ĐỘ PROJECT CHÍNH XÁC
    # Thay vì chỉ query Project, ta sẽ tính toán lại progress dựa trên Task thật
    raw_projects = Project.query.options(
        subqueryload(Project.builds).joinedload(Build.owner)
    ).order_by(Project.position, Project.name).all()
    
    projects_with_stats = []
    
    for p in raw_projects:
        # Query đếm số lượng task của project này
        # Logic: Project -> Objective -> KeyResult -> Task
        p_tasks_query = db.session.query(Task.status).join(KeyResult).join(Objective).filter(Objective.project_id == p.id)
        
        total_tasks = p_tasks_query.count()
        done_tasks = p_tasks_query.filter(Task.status == 'Done').count()
        
        # Tính % thực tế
        real_progress = 0
        if total_tasks > 0:
            real_progress = int((done_tasks / total_tasks) * 100)
        elif p.status == 'Done':
            real_progress = 100
            
        projects_with_stats.append({
            'id': p.id,
            'name': p.name,
            'status': p.status,
            'progress': real_progress, # Progress đã được audit
            'total_tasks': total_tasks,
            'done_tasks': done_tasks
        })

    # 5. Dữ liệu phụ
    logs = Log.query.order_by(Log.timestamp.desc()).limit(10).all()

    # 6. Thống kê (Stats Widget)
    stats = {
        'open_tasks': len(open_tasks_list),
        'overdue_tasks': len(categorized_tasks['Overdue']),
        'my_projects_count': len(raw_projects),
        'completed_this_week': tasks_base_query.filter(
            Task.status == 'Done',
            Task.task_date.between(start_of_week, end_of_week)
        ).count()
    }

    users_for_filter = db.session.scalars(select(User).order_by(User.username)).all()
    
    return render_template(
        'home.html',
        page_name='home',
        stats=stats,
        categorized_tasks=categorized_tasks,
        projects_with_stats=projects_with_stats, # [CHANGED] Truyền biến mới này sang view
        logs=logs,
        today_string=today.strftime('%A, %d %B %Y'),
        users_for_filter=users_for_filter,
        selected_user_id=selected_user_id
    )
# START: Nâng cấp API để xử lý ngày tháng
@bp.route('/api/update/<item_type>/<int:item_id>', methods=['POST'])
@login_required
def update_okr_item(item_type, item_id):
    model_map = {'objective': Objective, 'key_result': KeyResult, 'task': Task}
    Model = model_map.get(item_type)
    if not Model:
        return jsonify({'success': False, 'message': 'Invalid item type'}), 400

    item = Model.query.get_or_404(item_id)
    data = request.json
    response_data = {'success': True, 'message': f'{item_type.capitalize()} updated.'}

    try:
        # Cập nhật các trường chung
        if 'content' in data:
            if hasattr(item, 'content'): item.content = data.get('content')
            elif hasattr(item, 'what'): item.what = data.get('content')
        if 'note' in data: item.note = data.get('note')
        
        # Cập nhật ngày tháng
        if 'start_date' in data:
            date_str = data.get('start_date')
            item.start_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else None
        if 'end_date' in data:
            date_str = data.get('end_date')
            item.end_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else None

        # Cập nhật trạng thái Task và tính lại tiến độ
        if item_type == 'task' and 'status' in data:
            item.status = data.get('status')
            if item.key_result_id:
                kr = recalculate_kr_progress(item.key_result_id)
                db.session.flush()
                response_data.update({
                    'kr_id': kr.id, 'objective_id': kr.objective_id,
                    'kr_progress': kr.progress, 'obj_progress': kr.objective.progress,
                    'kr_current': kr.current, 'kr_target': kr.target
                })

        db.session.commit()
        return jsonify(response_data)
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating {item_type} {item_id}: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500

@bp.route('/api/objective/<int:obj_id>/details')
@login_required
def api_get_objective_details(obj_id):
    objective = Objective.query.options(
        subqueryload(Objective.key_results)
        .subqueryload(KeyResult.tasks)
        .joinedload(Task.assignee)
    ).get_or_404(obj_id)
    
    objective_data = {
        'id': objective.id, 'content': objective.content, 'note': objective.note,
        'start_date': objective.start_date.isoformat() if objective.start_date else None,
        'end_date': objective.end_date.isoformat() if objective.end_date else None,
        'key_results': [
            {'id': kr.id, 'content': kr.content, 'progress': kr.progress, 
             'current': kr.current, 'target': kr.target,
             'start_date': kr.start_date.isoformat() if kr.start_date else None,
             'end_date': kr.end_date.isoformat() if kr.end_date else None,
             'tasks': [{'id': task.id, 'what': task.what, 'status': task.status, 
                        'assignee': task.assignee.to_dict() if task.assignee else None}
                       for task in sorted(kr.tasks, key=lambda t: t.id)]
            } for kr in sorted(objective.key_results, key=lambda k: k.id)]
    }
    return jsonify({'success': True, 'objective': objective_data})
# END: Nâng cấp API

@bp.route('/api/objective/add', methods=['POST'])
@login_required
def api_add_objective():
    """API để tạo nhanh Objective từ Trello board."""
    data = request.json
    content = (data.get('content') or '').strip()
    build_id = data.get('build_id')
    project_id = data.get('project_id')

    if not content or not project_id:
        return jsonify({'success': False, 'message': 'Content and Project ID are required.'}), 400

    try:
        new_obj = Objective(
            content=content, project_id=project_id,
            build_id=int(build_id) if build_id and build_id != 'none' else None,
            owner_id=current_user.id,
            start_date=date.today() # SỬA LỖI: Tự động thêm ngày bắt đầu
        )
        db.session.add(new_obj)
        db.session.commit()
        return jsonify({'success': True, 'objective': new_obj.to_dict()})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating objective via API: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500

@bp.route('/api/build/add_from_board', methods=['POST'])
@login_required
def api_add_build_from_board():
    data = request.json
    name = (data.get('name') or '').strip()
    project_id = data.get('project_id')
    if not name or not project_id:
        return jsonify({'success': False, 'message': 'Name and Project ID are required.'}), 400
    try:
        new_build = Build(name=name, project_id=project_id, owner_id=current_user.id)
        db.session.add(new_build)
        db.session.commit()
        return jsonify({'success': True, 'build': new_build.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

# ==============================================================================
# HABIT TRACKER API (NÂNG CẤP) - DÁN VÀO CUỐI ROUTES.PY
# ==============================================================================
# Đảm bảo đã import: from app.models import Habit, HabitLog
# from datetime import timezone

def get_today_for_habit():
    # Sử dụng giờ VN (UTC+7)
    return datetime.now(timezone(timedelta(hours=7))).date()

@bp.route('/api/habits/today', methods=['GET'])
@login_required
def get_habits_today():
    try:
        today = get_today_for_habit()
        
        # Lấy thói quen active
        habits = Habit.query.filter_by(user_id=current_user.id, is_active=True).all()
        
        result = []
        for h in habits:
            log = HabitLog.query.filter_by(habit_id=h.id, date_logged=today).first()
            result.append({
                'id': h.id,
                'name': h.name,
                'description': h.description,
                'done': True if log and log.is_done else False
            })
        
        # Sắp xếp: Chưa làm lên trước, đã làm xuống dưới
        result.sort(key=lambda x: x['done'])
        
        return jsonify({'success': True, 'habits': result})
    except Exception as e:
        current_app.logger.error(f"Error getting habits: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500

@bp.route('/api/habits/toggle', methods=['POST'])
@login_required
def toggle_habit():
    try:
        data = request.json
        habit_id = data.get('habit_id')
        today = get_today_for_habit()
        
        habit = Habit.query.filter_by(id=habit_id, user_id=current_user.id).first_or_404()
        log = HabitLog.query.filter_by(habit_id=habit_id, date_logged=today).first()
        
        is_done = False
        if log:
            db.session.delete(log)
            is_done = False
        else:
            new_log = HabitLog(habit_id=habit_id, date_logged=today, is_done=True)
            db.session.add(new_log)
            is_done = True
            
        db.session.commit()
        return jsonify({'success': True, 'done': is_done})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@bp.route('/api/habits/add', methods=['POST'])
@login_required
def add_habit():
    try:
        data = request.json
        name = data.get('name')
        if not name: return jsonify({'success': False, 'message': 'Empty name'}), 400
        
        new_h = Habit(name=name, user_id=current_user.id)
        db.session.add(new_h)
        db.session.commit()
        return jsonify({'success': True, 'habit': new_h.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@bp.route('/api/habits/delete', methods=['POST'])
@login_required
def delete_habit():
    try:
        data = request.json
        habit_id = data.get('habit_id')
        habit = Habit.query.filter_by(id=habit_id, user_id=current_user.id).first_or_404()
        
        # Xóa cứng cho sạch database
        db.session.delete(habit)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500



# =======================================================
# API PHÂN TÍCH HOẠT ĐỘNG NGƯỜI DÙNG (USER ANALYTICS)
# =======================================================
@bp.route('/api/analytics/user-activity')
@login_required
def api_user_activity_analytics():
    try:
        # 1. Lấy tham số (Mặc định 30 ngày gần nhất)
        days = request.args.get('days', 30, type=int)
        target_user_id = request.args.get('user_id', type=int)
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # 2. Query bảng Log
        query = Log.query.filter(Log.timestamp >= start_date)
        
        if target_user_id:
            query = query.filter(Log.user_id == target_user_id)
            
        logs = query.order_by(Log.timestamp.asc()).all()
        
        if not logs:
            return jsonify({'success': True, 'data': [], 'summary': {}})

        # 3. Xử lý dữ liệu bằng Pandas
        data = []
        for log in logs:
            action_lower = log.action.lower()
            
            # [CHANGE] Bỏ qua log đăng nhập/đăng xuất
            if 'login' in action_lower or 'logout' in action_lower:
                continue

            act_type = None
            
            # Phân loại hành động chính
            if any(x in action_lower for x in ['create', 'add', 'tạo', 'new']):
                act_type = 'Create'
            elif any(x in action_lower for x in ['update', 'edit', 'sửa', 'change', 'save']):
                act_type = 'Update'
            elif any(x in action_lower for x in ['delete', 'remove', 'xóa']):
                act_type = 'Delete'
            elif 'complete' in action_lower or 'done' in action_lower:
                act_type = 'Complete'
            
            # Chỉ lấy các hành động có phân loại (bỏ qua rác)
            if act_type:
                data.append({
                    'date': log.timestamp.strftime('%Y-%m-%d'),
                    'type': act_type,
                    'count': 1
                })
            
        df = pd.DataFrame(data)
        
        # 4. Group by Date & Type
        if not df.empty:
            pivot_df = df.pivot_table(index='date', columns='type', values='count', aggfunc='sum', fill_value=0)
            
            idx = pd.date_range(start_date.date(), end_date.date())
            pivot_df.index = pd.DatetimeIndex(pivot_df.index)
            pivot_df = pivot_df.reindex(idx, fill_value=0)
            pivot_df.index = pivot_df.index.strftime('%Y-%m-%d')
            
            chart_labels = pivot_df.index.tolist()
            datasets = []
            
            # [CHANGE] Bỏ màu Login, chỉ giữ các action quan trọng
            colors = {
                'Create': '#198754',   # Xanh lá
                'Update': '#0d6efd',   # Xanh dương
                'Delete': '#dc3545',   # Đỏ
                'Complete': '#0dcaf0', # Xanh ngọc
            }
            
            for col in pivot_df.columns:
                datasets.append({
                    'label': col,
                    'data': pivot_df[col].tolist(),
                    'backgroundColor': colors.get(col, '#6c757d'),
                    'stack': 'combined'
                })
                
            summary = df['type'].value_counts().to_dict()
            
            return jsonify({
                'success': True,
                'chart': {
                    'labels': chart_labels,
                    'datasets': datasets
                },
                'summary': summary
            })
            
        return jsonify({'success': True, 'data': [], 'summary': {}})

    except Exception as e:
        current_app.logger.error(f"Analytics Error: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500
# ... (Các import và code cũ giữ nguyên) ...

# =======================================================
# API XẾP HẠNG HOẠT ĐỘNG ĐỘI NHÓM (TEAM ACTIVITY RANKING)
# Đếm số lần Tạo/Sửa/Xóa của từng User
# =======================================================
@bp.route('/api/analytics/team-activity-ranking')
@login_required
def api_team_activity_ranking():
    try:
        period = request.args.get('period', 'week') # week, month, year, all
        
        today = date.today()
        start_date = None
        end_date = None
        
        # 1. Xác định mốc thời gian
        if period == 'week':
            start_date = today - timedelta(days=today.weekday())
            end_date = start_date + timedelta(days=6)
        elif period == 'month':
            start_date = today.replace(day=1)
            next_month = today.replace(day=28) + timedelta(days=4)
            end_date = next_month - timedelta(days=next_month.day)
        elif period == 'year':
            start_date = today.replace(month=1, day=1)
            end_date = today.replace(month=12, day=31)
            
        # 2. Query Logs (Join User)
        query = db.session.query(Log, User.username).join(User, Log.user_id == User.id)
        
        if start_date:
            query = query.filter(Log.timestamp >= start_date)
        if end_date:
            # end_date là ngày, cần convert sang cuối ngày đó để query timestamp
            query = query.filter(Log.timestamp <= datetime.combine(end_date, datetime.max.time()))
            
        logs = query.all()
        
        # 3. Xử lý dữ liệu (Group by User & Action Type)
        # Cấu trúc: {'username': {'Create': 0, 'Update': 0, 'Delete': 0}}
        user_stats = defaultdict(lambda: {'Create': 0, 'Update': 0, 'Delete': 0})
        
        for log_entry, username in logs:
            action_lower = log_entry.action.lower()
            # Bỏ qua login/logout
            if 'login' in action_lower or 'logout' in action_lower:
                continue
                
            cat = None
            if any(x in action_lower for x in ['create', 'add', 'tạo', 'new']): cat = 'Create'
            elif any(x in action_lower for x in ['update', 'edit', 'sửa', 'change', 'save']): cat = 'Update'
            elif any(x in action_lower for x in ['delete', 'remove', 'xóa']): cat = 'Delete'
            elif 'complete' in action_lower or 'done' in action_lower: cat = 'Update' # Coi complete là 1 dạng update trạng thái
            
            if cat:
                user_stats[username][cat] += 1
                
        # 4. Chuyển đổi sang list để sắp xếp và trả về JSON
        data_list = []
        for user, stats in user_stats.items():
            stats['username'] = user
            stats['total'] = stats['Create'] + stats['Update'] + stats['Delete']
            data_list.append(stats)
            
        if not data_list:
             return jsonify({'success': True, 'labels': [], 'datasets': []})
             
        # Sắp xếp theo tổng số hoạt động giảm dần
        df = pd.DataFrame(data_list)
        df = df.sort_values(by='total', ascending=False).head(15) # Top 15 người chăm chỉ nhất
        
        labels = df['username'].tolist()
        
        # Cấu hình datasets cho Chart.js
        datasets = [
            {
                'label': 'Create',
                'data': df['Create'].tolist(),
                'backgroundColor': '#198754', # Xanh lá
                'barPercentage': 0.6
            },
            {
                'label': 'Update',
                'data': df['Update'].tolist(),
                'backgroundColor': '#0d6efd', # Xanh dương
                'barPercentage': 0.6
            },
            {
                'label': 'Delete',
                'data': df['Delete'].tolist(),
                'backgroundColor': '#dc3545', # Đỏ
                'barPercentage': 0.6
            }
        ]
        
        return jsonify({'success': True, 'labels': labels, 'datasets': datasets})

    except Exception as e:
        current_app.logger.error(f"Activity Ranking Error: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500

# Trong routes.py

@bp.route('/api/task/<int:task_id>/comment', methods=['POST'])
@login_required
def add_task_comment(task_id):
    data = request.json
    raw_content = data.get('content', '').strip()
    
    if not raw_content:
        return jsonify({'success': False, 'message': 'Nội dung không được rỗng.'}), 400

    try:
        # Cấu hình an toàn cho nội dung Chat
        allowed_tags = ['p', 'br', 'strong', 'em', 'u', 'img', 'a', 'span', 'b', 'i', 'div']
        allowed_attrs = {
            'img': ['src', 'alt', 'style', 'class', 'width', 'height'],
            'a': ['href', 'title', 'target'],
            'span': ['style'],
            'div': ['style']
        }
        
        # Làm sạch HTML trước khi lưu vào DB
        clean_content = bleach.clean(raw_content, tags=allowed_tags, attributes=allowed_attrs)

        new_comment = TaskComment(
            content=clean_content, # Lưu nội dung đã làm sạch
            user_id=current_user.id,
            task_id=task_id
        )
        db.session.add(new_comment)
        db.session.commit()
        
        return jsonify({'success': True, 'comment': new_comment.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
# [MỚI] API XÓA COMMENT
@bp.route('/api/comment/<int:comment_id>', methods=['DELETE'])
@login_required
def delete_comment(comment_id):
    try:
        comment = TaskComment.query.get_or_404(comment_id)
        
        # Chỉ cho phép xóa comment của chính mình
        if comment.user_id != current_user.id:
            return jsonify({'success': False, 'message': 'You can only delete your own comments.'}), 403
            
        db.session.delete(comment)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Comment deleted.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500





# ==============================================================================
# ATTENDANCE ROUTES
# ==============================================================================

@bp.route('/attendance')
@login_required
def attendance_dashboard():
    today = datetime.now()
    return render_template(
        'attendance_dashboard.html',
        today_string=today.strftime('%A, %d %B %Y'),
        today_date_str=today.strftime('%Y-%m-%d'),
        page_name='attendance'
    )

@bp.route('/api/attendance/bulk-holiday', methods=['POST'])
@login_required
def bulk_set_holiday():
    try:
        data = request.json
        start_str = data.get('start_date')
        end_str = data.get('end_date')
        note = data.get('note', 'Nghỉ lễ')
        
        if not start_str or not end_str:
            return jsonify({'success': False, 'message': 'Thiếu ngày bắt đầu hoặc kết thúc'}), 400
            
        start_date = datetime.strptime(start_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_str, '%Y-%m-%d').date()
        
        users = User.query.all()
        delta = (end_date - start_date).days + 1
        
        for i in range(delta):
            target_date = start_date + timedelta(days=i)
            for u in users:
                att = Attendance.query.filter_by(user_id=u.id, date=target_date).first()
                if not att:
                    att = Attendance(user_id=u.id, date=target_date)
                    db.session.add(att)
                att.status = 'Holiday'
                att.shift_type = 'Full'
                att.note = note
                
        db.session.commit()
        return jsonify({'success': True, 'message': f'Đã thiết lập nghỉ lễ cho {len(users)} nhân viên trong {delta} ngày.'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@bp.route('/api/attendance/matrix')
@login_required
def attendance_matrix():
    start_str = request.args.get('start')
    end_str = request.args.get('end')
    
    if not start_str or not end_str:
        return jsonify({'success': False, 'message': 'Missing date range'}), 400
        
    start_date = datetime.strptime(start_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_str, '%Y-%m-%d').date()
    
    users = User.query.order_by(User.username).all()
    
    atts = Attendance.query.filter(
        Attendance.date >= start_date,
        Attendance.date <= end_date
    ).all()
    
    data_map = defaultdict(dict)
    for a in atts:
        date_key = a.date.strftime('%Y-%m-%d')
        data_map[a.user_id][date_key] = {
            'status': a.status,
            'shift_type': a.shift_type,
            'note': a.note
        }
        
    date_headers = []
    delta = (end_date - start_date).days + 1
    for i in range(delta):
        curr = start_date + timedelta(days=i)
        date_headers.append({
            'date': curr.strftime('%Y-%m-%d'),
            'day_name': curr.strftime('%a'),
            'day_num': curr.day,
            'is_weekend': curr.weekday() >= 5
        })
        
    matrix_data = []
    for u in users:
        user_row = {
            'id': u.id,
            'username': u.username,
            'attendance': []
        }
        for day_info in date_headers:
            d_key = day_info['date']
            record = data_map[u.id].get(d_key)
            status = 'Pending'
            if record:
                status = record['status']
                if record['shift_type'] == 'Morning_Half': status = 'Leave_Morning'
                elif record['shift_type'] == 'Afternoon_Half': status = 'Leave_Afternoon'
            elif day_info['is_weekend']:
                status = 'Weekend'
            
            user_row['attendance'].append({
                'date': d_key,
                'status': status,
                'note': record['note'] if record else ''
            })
        matrix_data.append(user_row)
        
    return jsonify({'success': True, 'headers': date_headers, 'rows': matrix_data})

@bp.route('/api/attendance/daily-sheet', methods=['GET'])
@login_required
def get_daily_sheet():
    date_str = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    users = User.query.order_by(User.username).all()
    attendances = Attendance.query.filter_by(date=target_date).all()
    att_map = {a.user_id: a for a in attendances}
    result = []
    is_weekend = target_date.weekday() >= 5 
    for u in users:
        att = att_map.get(u.id)
        if att:
            status = att.status
            shift_type = att.shift_type 
            note = att.note
            has_record = True
        else:
            status = 'Weekend' if is_weekend else 'Present'
            shift_type = 'Full'
            note = ''
            has_record = False
        result.append({
            'user_id': u.id, 'username': u.username, 'status': status,
            'shift_type': shift_type, 'note': note, 'has_record': has_record
        })
    return jsonify({'success': True, 'data': result, 'date': date_str})

@bp.route('/api/attendance/update-entry', methods=['POST'])
@login_required
def update_attendance_entry():
    data = request.json
    user_id = data.get('user_id')
    date_str = data.get('date')
    raw_status = data.get('status')
    note = data.get('note')
    if not user_id or not date_str:
        return jsonify({'success': False, 'message': 'Missing data'}), 400
    target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    att = Attendance.query.filter_by(user_id=user_id, date=target_date).first()
    if not att:
        att = Attendance(user_id=user_id, date=target_date)
        db.session.add(att)
    
    if raw_status == 'Leave_Morning':
        att.status = 'Leave'
        att.shift_type = 'Morning_Half'
    elif raw_status == 'Leave_Afternoon':
        att.status = 'Leave'
        att.shift_type = 'Afternoon_Half'
    elif raw_status == 'Leave':
        att.status = 'Leave'
        att.shift_type = 'Full'
    else:
        att.status = raw_status
        att.shift_type = 'Full'
    att.note = note
    if att.status in ['Present', 'Late', 'Training'] and not att.check_in:
        att.check_in = datetime.combine(target_date, datetime.min.time())
    db.session.commit()
    return jsonify({'success': True, 'message': f'Updated User {user_id}'})

@bp.route('/api/attendance/leave-summary', methods=['GET'])
@login_required
def leave_summary():
    year = request.args.get('year', datetime.now().year, type=int)
    users = User.query.all()
    result = []
    for u in users:
        stats = u.get_leave_stats(year) 
        result.append({'id': u.id, 'username': u.username, 'quota': stats['quota'], 'used': stats['used'], 'remaining': stats['remaining']})
    result.sort(key=lambda x: x['used'], reverse=True)
    return jsonify({'users': result})

@bp.route('/api/user/<int:user_id>/update-leave-stats', methods=['POST'])
@login_required
def update_user_leave_stats(user_id):
    user = User.query.get_or_404(user_id)
    data = request.json
    if 'quota' in data: user.annual_leave_quota = float(data['quota'])
    if 'total_used' in data:
        desired_used = float(data['total_used'])
        current_stats = user.get_leave_stats(datetime.now().year)
        system_calculated = current_stats['system_used']
        user.leave_used_correction = desired_used - system_calculated
    db.session.commit()
    return jsonify({'success': True})

@bp.route('/api/attendance/report', methods=['GET'])
@login_required
def attendance_report():
    month = request.args.get('month', datetime.now().month, type=int)
    year = request.args.get('year', datetime.now().year, type=int) # Lấy năm từ request
    range_val = request.args.get('range', 1, type=int) 
    
    if range_val == 12:
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
    else:
        _, last_day = monthrange(year, month)
        end_date = date(year, month, last_day)
        start_date = end_date.replace(day=1) 
        curr = start_date
        for _ in range(range_val - 1):
             curr = (curr - timedelta(days=1)).replace(day=1)
        start_date = curr
    
    users = User.query.all()
    report = []
    atts = Attendance.query.filter(Attendance.date >= start_date, Attendance.date <= end_date).all()
    user_att_map = defaultdict(dict)
    for a in atts: user_att_map[a.user_id][a.date] = a.status
    delta_days = (end_date - start_date).days + 1

    for u in users:
        stats = {'Present': 0, 'Late': 0, 'Leave': 0, 'Absent': 0, 'Training': 0, 'Weekend': 0, 'Holiday': 0}
        for i in range(delta_days):
            current_date = start_date + timedelta(days=i)
            is_weekend = current_date.weekday() >= 5
            status = user_att_map[u.id].get(current_date, 'Weekend' if is_weekend else 'Present')
            if status in stats: stats[status] += 1
        
        # Đảm bảo get_leave_stats nhận đúng năm
        leave_info = u.get_leave_stats(year)
        report.append({'username': u.username, 'user_id': u.id, 'stats': stats, 'leave_info': leave_info})
        
    return jsonify({'success': True, 'report': report, 'period_text': f"Từ {start_date.strftime('%d/%m/%Y')} đến {end_date.strftime('%d/%m/%Y')}"})

@bp.route('/x3')
@login_required
def x3_dashboard():
    # 1. NHẬN THAM SỐ
    view_mode = request.args.get('view_mode', 'day')
    date_str = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    user_filter = request.args.get('user_filter', 'me')
    
    try:
        current_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        current_date = datetime.now().date()

    # 2. XỬ LÝ ĐIỀU HƯỚNG THỜI GIAN (PREV/NEXT/DISPLAY)
    prev_date = next_date = None
    date_display = ""
    
    if view_mode == 'day':
        prev_date = (current_date - timedelta(days=1)).strftime('%Y-%m-%d')
        next_date = (current_date + timedelta(days=1)).strftime('%Y-%m-%d')
        date_display = current_date.strftime('Thứ %w, %d/%m/%Y').replace('Thứ 0', 'Chủ Nhật').replace('Thứ 1', 'Thứ 2').replace('Thứ 2', 'Thứ 3').replace('Thứ 3', 'Thứ 4').replace('Thứ 4', 'Thứ 5').replace('Thứ 5', 'Thứ 6').replace('Thứ 6', 'Thứ 7')
    
    elif view_mode == 'week':
        start_of_week = current_date - timedelta(days=current_date.weekday())
        prev_date = (start_of_week - timedelta(weeks=1)).strftime('%Y-%m-%d')
        next_date = (start_of_week + timedelta(weeks=1)).strftime('%Y-%m-%d')
        end_of_week = start_of_week + timedelta(days=6)
        year, week_num, _ = current_date.isocalendar()
        date_display = f"Tuần {week_num} ({start_of_week.strftime('%d/%m')} - {end_of_week.strftime('%d/%m')})"

    elif view_mode == 'month':
        # Logic lùi/tiến tháng
        # Prev Month
        last_month = current_date.replace(day=1) - timedelta(days=1)
        prev_date = last_month.replace(day=1).strftime('%Y-%m-%d')
        # Next Month
        _, days_in_month = calendar.monthrange(current_date.year, current_date.month)
        next_month = current_date.replace(day=1) + timedelta(days=days_in_month)
        next_date = next_month.replace(day=1).strftime('%Y-%m-%d')
        
        date_display = f"Tháng {current_date.month} / {current_date.year}"

    # 3. XÁC ĐỊNH USER
    target_user_id = current_user.id
    if user_filter.isdigit():
        target_user_id = int(user_filter)
    all_users = User.query.order_by(User.username).all()

    # 4. DATA CHO PICKER TASK
    searchable_tasks = Task.query.filter(
        Task.who_id == target_user_id,
        Task.status.in_(['Pending', 'In Progress'])
    ).options(subqueryload(Task.sub_tasks)).order_by(Task.task_date.desc()).limit(50).all()
    
    searchable_tasks_json = [{
        'id': t.id, 'what': t.what,
        'date': t.task_date.strftime('%d/%m') if t.task_date else '',
        'subtasks': [st.content for st in t.sub_tasks] 
    } for t in searchable_tasks]

    # Context chung
    context = {
        'page_name': 'x3',
        'view_mode': view_mode,
        'date_str': date_str,
        'current_date': current_date,
        'user_filter': user_filter,
        'all_users': all_users,
        'searchable_tasks_json': searchable_tasks_json,
        'plan': None, 'col1_data': [], 'col3_data': [], 'habit_data': [],
        'prev_date': prev_date, 'next_date': next_date, 'date_display': date_display
    }

    # === LOGIC VIEW ===
    if view_mode == 'day':
        context['plan'] = DailyPlan.query.filter_by(user_id=target_user_id, date=current_date).first()
        
        tasks_query = Task.query.filter(Task.task_date == current_date)
        if user_filter == 'me': tasks_query = tasks_query.filter(Task.who_id == current_user.id)
        elif user_filter.isdigit(): tasks_query = tasks_query.filter(Task.who_id == int(user_filter))
        
        all_tasks = tasks_query.options(joinedload(Task.assignee)).order_by(Task.hour).all()
        context['col1_data'] = [t for t in all_tasks if t.hour is not None]
        context['col3_data'] = [t for t in all_tasks if t.hour is None]

        habits = Habit.query.filter_by(user_id=target_user_id, is_active=True).all()
        for h in habits:
            log = HabitLog.query.filter_by(habit_id=h.id, date_logged=current_date).first()
            context['habit_data'].append({'id': h.id, 'name': h.name, 'done': log.is_done if log else False})

    elif view_mode == 'week':
        year, week_num, _ = current_date.isocalendar()
        context['plan'] = WeeklyPlan.query.filter_by(user_id=target_user_id, year=year, week_number=week_num).first()
        
        start_of_week = current_date - timedelta(days=current_date.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        
        week_tasks = Task.query.filter(Task.task_date.between(start_of_week, end_of_week))
        if user_filter == 'me': week_tasks = week_tasks.filter(Task.who_id == current_user.id)
        elif user_filter.isdigit(): week_tasks = week_tasks.filter(Task.who_id == int(user_filter))
        
        ts = week_tasks.options(joinedload(Task.assignee)).order_by(Task.task_date, Task.hour).all()
        days_map = defaultdict(list)
        for t in ts: days_map[t.task_date.strftime('%Y-%m-%d')].append(t)
        
        col1_data = []
        day_names = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'CN']
        for i in range(7):
            d = start_of_week + timedelta(days=i)
            d_str = d.strftime('%Y-%m-%d')
            col1_data.append({'date': d, 'day_name': day_names[i], 'tasks': days_map.get(d_str, [])})
        context['col1_data'] = col1_data

    elif view_mode == 'month':
        context['plan'] = MonthlyPlan.query.filter_by(user_id=target_user_id, year=current_date.year, month=current_date.month).first()
        
        # LOGIC MỚI: LẤY DANH SÁCH CÁC TUẦN TRONG THÁNG (Cho Cột 1)
        # 1. Tìm ngày đầu và cuối tháng
        _, num_days = calendar.monthrange(current_date.year, current_date.month)
        start_month = current_date.replace(day=1)
        end_month = current_date.replace(day=num_days)
        
        # 2. Duyệt qua các tuần
        # Bắt đầu từ thứ 2 của tuần chứa ngày mùng 1
        curr_week_start = start_month - timedelta(days=start_month.weekday())
        weeks_list = []
        
        while curr_week_start <= end_month:
            year, week_num, _ = curr_week_start.isocalendar()
            
            # Lấy WeeklyPlan của tuần đó để hiển thị Mục tiêu (Preview)
            w_plan = WeeklyPlan.query.filter_by(user_id=target_user_id, year=year, week_number=week_num).first()
            w_objective = w_plan.weekly_objective if w_plan else ""
            
            weeks_list.append({
                'week_num': week_num,
                'start_date': curr_week_start,
                'end_date': curr_week_start + timedelta(days=6),
                'objective': w_objective,
                'link_date': curr_week_start.strftime('%Y-%m-%d') # Để link sang view week
            })
            curr_week_start += timedelta(weeks=1)
            
        context['col1_data'] = weeks_list # Gán vào cột 1 của Month View

    return render_template('x3_dashboard.html', **context)


@bp.route('/api/subtask/<int:subtask_id>/toggle', methods=['POST'])
@login_required
def toggle_subtask(subtask_id):
    # 1. Lưu trạng thái tick ngay lập tức
    subtask = SubTask.query.get_or_404(subtask_id)
    parent_task_id = subtask.task_id
    
    subtask.is_done = not subtask.is_done
    db.session.commit() # Commit luôn để DB cập nhật
    
    # 2. Lấy số liệu thống kê mới nhất từ DB
    parent_task = Task.query.get(parent_task_id)
    total_items = SubTask.query.filter_by(task_id=parent_task_id).count()
    incomplete_items = SubTask.query.filter_by(task_id=parent_task_id, is_done=False).count()
    done_items = total_items - incomplete_items
    
    old_status = parent_task.status
    new_status = old_status # Mặc định giữ nguyên
    
    # 3. Logic Đơn giản hóa: Dựa trên % hoàn thành
    if total_items > 0:
        if incomplete_items == 0: new_status = 'Done'
        elif done_items > 0: new_status = 'In Progress'
        else: new_status = 'Pending'

    # 4. Cập nhật nếu trạng thái thay đổi
    if new_status != old_status:
        parent_task.status = new_status
        if new_status == 'Done':
            parent_task.task_date = date.today() 
            if parent_task.start_date and parent_task.start_date > parent_task.task_date:
                parent_task.start_date = parent_task.task_date
            if parent_task.daily_report_item_id:
                issue = DailyReportData.query.get(parent_task.daily_report_item_id)
                if issue:
                    issue.is_resolved = 1
                    issue.report_date = date.today()
        else:
            if old_status == 'Done' and parent_task.daily_report_item_id:
                issue = DailyReportData.query.get(parent_task.daily_report_item_id)
                if issue: issue.is_resolved = 0

        if parent_task.key_result_id:
            recalculate_kr_progress(parent_task.key_result_id)
        db.session.commit()

    # Tính toán % tiến độ hiện tại của Task con
    progress_pct = int((done_items / total_items) * 100) if total_items > 0 else 0

    # --- [MỚI] 5. TÍNH TOÁN % GLOBAL CHO NGÀY HIỆN TẠI ---
# --- [MỚI] 5. TÍNH TOÁN % GLOBAL CHO NGÀY HIỆN TẠI ---
# --- [MỚI] 5. TÍNH TOÁN % GLOBAL CHO NGÀY HIỆN TẠI (ĐỒNG BỘ LOGIC 1 TASK = 1 ĐIỂM) ---
    data = request.get_json(silent=True) or {}
    report_date_str = data.get('report_date')
    if report_date_str:
        report_date = datetime.strptime(report_date_str, '%Y-%m-%d').date()
    else:
        report_date = parent_task.task_date
        
    all_tasks_for_day = Task.query.filter(
        or_(
            and_(Task.start_date.isnot(None), Task.start_date <= report_date, Task.task_date >= report_date),
            and_(Task.start_date.is_(None), Task.task_date == report_date),
            and_(Task.task_date < report_date, Task.status.notin_(['Done', 'Drop']))
        )
    ).options(subqueryload(Task.sub_tasks)).all()
    
    active_projects = Project.query.filter(Project.status != 'Done').all()
    project_ids = [p.id for p in active_projects]
    
    total_day_tasks = 0.0
    done_day_score = 0.0
    
    for t in all_tasks_for_day:
        if t.status == 'Drop':
            continue
            
        p_id = None
        if t.key_result_id:
            kr = KeyResult.query.get(t.key_result_id)
            if kr and kr.objective: p_id = kr.objective.project_id
        elif t.daily_report_item_id:
            issue = DailyReportData.query.get(t.daily_report_item_id)
            if issue: p_id = issue.project_id
            
        if not p_id:
            for p in active_projects:
                if f"[{p.name}]" in t.what:
                    p_id = p.id
                    break

        if p_id and p_id in project_ids:
            sts = t.sub_tasks
            if sts:
                total_st = len(sts)
                done_st = sum(1 for st in sts if st.is_done)
                task_score = done_st / total_st if total_st > 0 else 0
            else:
                task_score = 1.0 if t.status == 'Done' else 0.0
                
            total_day_tasks += 1.0
            done_day_score += task_score
            
    global_progress = int((done_day_score / total_day_tasks * 100)) if total_day_tasks > 0 else 0

    return jsonify({
        'success': True, 
        'is_done': subtask.is_done,
        'task_status': parent_task.status,
        'progress_pct': progress_pct,
        'global_progress': global_progress, # Đã chuẩn xác
        'message': f'Updated: {old_status} -> {new_status}'
    })

def sync_kr_to_task(user_id, date_obj, kr_content, action_content, existing_task_id=None, task_type='Daily'):
    # Nếu KR rỗng thì không làm gì
    if not kr_content or not kr_content.strip():
        return None

    # --- SỬA LỖI 1: TÍNH TOÁN NỘI DUNG TASK TRƯỚC KHI TẠO ---
    # Prefix cho Task name
    prefix = ""
    if task_type == 'Weekly': prefix = "[Tuần] "
    elif task_type == 'Monthly': prefix = "[Tháng] "
    
    final_content = kr_content
    if prefix and not kr_content.startswith("["):
         final_content = f"{prefix}{kr_content}"

    task = None
    if existing_task_id:
        task = Task.query.get(existing_task_id)
    
    if not task:
        # Tạo Task mới: Gán 'what' ngay lập tức để tránh lỗi NOT NULL khi flush
        task = Task(
            what=final_content,
            who_id=user_id, 
            task_date=date_obj, 
            status='Pending', 
            priority='High'
        ) 
        db.session.add(task)
        db.session.flush() # Lúc này 'what' đã có dữ liệu, flush sẽ thành công
    else:
        # Nếu task đã tồn tại, cập nhật lại nội dung và ngày
        task.what = final_content 
        task.task_date = date_obj
    
    # --- LOGIC XỬ LÝ SUBTASK (Checklist) ---
    if action_content:
        # --- SỬA LỖI 2: HỖ TRỢ TÁCH DÒNG 1. 2. 3. VÀ CÁC KÝ TỰ ĐẶC BIỆT ---
        # Sử dụng Regex để làm sạch đầu dòng:
        # ^(\d+[\.\)]|[-•*]) : Bắt đầu bằng số kèm chấm/ngoặc HOẶC các dấu gạch đầu dòng
        import re
        new_lines = []
        for line in action_content.split('\n'):
            # Loại bỏ số thứ tự (1., 2...) hoặc gạch đầu dòng (-, *, •)
            clean_line = re.sub(r'^(\d+[\.\)]|[-•*])\s*', '', line.strip()).strip()
            if clean_line:
                new_lines.append(clean_line)
        
        # Lấy checklist hiện tại từ DB
        existing_subtasks = SubTask.query.filter_by(task_id=task.id).all()
        existing_map = {st.content: st for st in existing_subtasks}
        
        used_ids = set()
        
        # Duyệt qua các dòng mới nhập
        for line in new_lines:
            if line in existing_map:
                # Nếu đã có -> Giữ nguyên (để giữ trạng thái is_done)
                st = existing_map[line]
                used_ids.add(st.id)
            else:
                # Nếu chưa có -> Tạo mới
                st = SubTask(content=line, is_done=False, task_id=task.id)
                db.session.add(st)
        
        # Xóa những mục không còn trong text nữa
        for st in existing_subtasks:
            if st.id not in used_ids:
                db.session.delete(st)
            
    return task.id

# --- CẬP NHẬT CÁC API SAVE ---

@bp.route('/api/x3/save', methods=['POST'])
@login_required
def save_x3_plan():
    """Lưu kế hoạch NGÀY"""
    data = request.json
    try:
        date_str = data.get('date')
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()

        plan = DailyPlan.query.filter_by(user_id=current_user.id, date=target_date).first()
        if not plan:
            plan = DailyPlan(user_id=current_user.id, date=target_date)
            db.session.add(plan)

        # Update text fields
        plan.pain_point = data.get('pain_point')
        plan.root_cause = data.get('root_cause')
        plan.daily_objective = data.get('daily_objective')
        
        plan.kr1 = data.get('kr1'); plan.kr1_action = data.get('kr1_action')
        plan.kr2 = data.get('kr2'); plan.kr2_action = data.get('kr2_action')
        plan.kr3 = data.get('kr3'); plan.kr3_action = data.get('kr3_action')
        
        plan.kaizen_result = data.get('kaizen_result')
        plan.kaizen_cause = data.get('kaizen_cause')
        plan.kaizen_action = data.get('kaizen_action')
        plan.kaizen_lesson = data.get('kaizen_lesson')

        # SYNC TO TASKS
        # Helper lấy ID từ input hoặc DB
        def get_tid(input_key, db_val):
            val = data.get(input_key)
            if val and str(val).isdigit(): return int(val)
            return db_val

        tid1 = sync_kr_to_task(current_user.id, target_date, plan.kr1, plan.kr1_action, get_tid('kr1_task_id', plan.kr1_task_id), 'Daily')
        if tid1: plan.kr1_task_id = tid1
        
        tid2 = sync_kr_to_task(current_user.id, target_date, plan.kr2, plan.kr2_action, get_tid('kr2_task_id', plan.kr2_task_id), 'Daily')
        if tid2: plan.kr2_task_id = tid2
        
        tid3 = sync_kr_to_task(current_user.id, target_date, plan.kr3, plan.kr3_action, get_tid('kr3_task_id', plan.kr3_task_id), 'Daily')
        if tid3: plan.kr3_task_id = tid3

        db.session.commit()
        return jsonify({'success': True, 'message': 'Đã lưu & Đồng bộ Task!'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@bp.route('/api/x3/save-week', methods=['POST'])
@login_required
def save_x3_week():
    """Lưu kế hoạch TUẦN"""
    data = request.json
    try:
        d = datetime.strptime(data.get('date'), '%Y-%m-%d').date()
        year, week_num, _ = d.isocalendar()
        
        # Tính ngày đầu tuần để gán cho Task tuần (thường là Thứ 2)
        start_of_week = d - timedelta(days=d.weekday())

        plan = WeeklyPlan.query.filter_by(user_id=current_user.id, year=year, week_number=week_num).first()
        if not plan:
            plan = WeeklyPlan(user_id=current_user.id, year=year, week_number=week_num)
            db.session.add(plan)
            
        plan.pain_point = data.get('pain_point')
        plan.root_cause = data.get('root_cause')
        plan.weekly_objective = data.get('daily_objective') 
        
        plan.kr1 = data.get('kr1'); plan.kr1_action = data.get('kr1_action')
        plan.kr2 = data.get('kr2'); plan.kr2_action = data.get('kr2_action')
        plan.kr3 = data.get('kr3'); plan.kr3_action = data.get('kr3_action')
        
        plan.kaizen_result = data.get('kaizen_result')
        plan.kaizen_cause = data.get('kaizen_cause')
        plan.kaizen_action = data.get('kaizen_action')
        plan.kaizen_lesson = data.get('kaizen_lesson')
        
        # SYNC TASKS (Weekly)
        def get_tid(input_key, db_val):
            val = data.get(input_key)
            if val and str(val).isdigit(): return int(val)
            return db_val

        tid1 = sync_kr_to_task(current_user.id, start_of_week, plan.kr1, plan.kr1_action, get_tid('kr1_task_id', plan.kr1_task_id), 'Weekly')
        if tid1: plan.kr1_task_id = tid1
        
        tid2 = sync_kr_to_task(current_user.id, start_of_week, plan.kr2, plan.kr2_action, get_tid('kr2_task_id', plan.kr2_task_id), 'Weekly')
        if tid2: plan.kr2_task_id = tid2
        
        tid3 = sync_kr_to_task(current_user.id, start_of_week, plan.kr3, plan.kr3_action, get_tid('kr3_task_id', plan.kr3_task_id), 'Weekly')
        if tid3: plan.kr3_task_id = tid3
            
        db.session.commit()
        return jsonify({'success': True, 'message': 'Đã lưu tiêu điểm tuần!'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@bp.route('/api/x3/save-month', methods=['POST'])
@login_required
def save_x3_month():
    """Lưu kế hoạch THÁNG"""
    data = request.json
    try:
        d = datetime.strptime(data.get('date'), '%Y-%m-%d').date()
        # Ngày đầu tháng
        start_of_month = d.replace(day=1)
        
        plan = MonthlyPlan.query.filter_by(user_id=current_user.id, year=d.year, month=d.month).first()
        if not plan:
            plan = MonthlyPlan(user_id=current_user.id, year=d.year, month=d.month)
            db.session.add(plan)
            
        plan.pain_point = data.get('pain_point')
        plan.root_cause = data.get('root_cause')
        plan.monthly_objective = data.get('daily_objective') 
        
        plan.kr1 = data.get('kr1'); plan.kr1_action = data.get('kr1_action')
        plan.kr2 = data.get('kr2'); plan.kr2_action = data.get('kr2_action')
        plan.kr3 = data.get('kr3'); plan.kr3_action = data.get('kr3_action')
        
        plan.kaizen_result = data.get('kaizen_result')
        plan.kaizen_cause = data.get('kaizen_cause')
        plan.kaizen_action = data.get('kaizen_action')
        plan.kaizen_lesson = data.get('kaizen_lesson')

        # SYNC TASKS (Monthly)
        def get_tid(input_key, db_val):
            val = data.get(input_key)
            if val and str(val).isdigit(): return int(val)
            return db_val

        tid1 = sync_kr_to_task(current_user.id, start_of_month, plan.kr1, plan.kr1_action, get_tid('kr1_task_id', plan.kr1_task_id), 'Monthly')
        if tid1: plan.kr1_task_id = tid1
        
        tid2 = sync_kr_to_task(current_user.id, start_of_month, plan.kr2, plan.kr2_action, get_tid('kr2_task_id', plan.kr2_task_id), 'Monthly')
        if tid2: plan.kr2_task_id = tid2
        
        tid3 = sync_kr_to_task(current_user.id, start_of_month, plan.kr3, plan.kr3_action, get_tid('kr3_task_id', plan.kr3_task_id), 'Monthly')
        if tid3: plan.kr3_task_id = tid3

        db.session.commit()
        return jsonify({'success': True, 'message': 'Đã lưu tiêu điểm tháng!'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500



# ==============================================================================
# PERFORMANCE MANAGEMENT (TRANG MỚI)
# ==============================================================================

@bp.route('/performance')
@login_required
def performance_dashboard():
    today = datetime.now()
    return render_template(
        'performance_dashboard.html',
        today_string=today.strftime('%A, %d %B %Y'),
        today_date_str=today.strftime('%Y-%m-%d'),
        page_name='performance'
    )


def _calculate_auto_scores(user_id, target_date):
    """Tính toán điểm gợi ý cho Số lượng và Kỷ luật"""
    # 1. Số lượng
    tasks = Task.query.filter_by(who_id=user_id, task_date=target_date).all()
    total_points = 0
    done_count = 0
    for t in tasks:
        if t.status == 'Done':
            done_count += 1
            if t.priority == 'Urgent': total_points += 3
            elif t.priority == 'High': total_points += 2
            elif t.priority == 'Medium': total_points += 1
            else: total_points += 0.5
    
    suggested_qty = 5
    if total_points >= 5: suggested_qty = 10
    elif total_points >= 3: suggested_qty = 8
    elif total_points >= 1: suggested_qty = 6
    elif done_count == 0 and len(tasks) > 0: suggested_qty = 4

    # 2. Kỷ luật
    att = Attendance.query.filter_by(user_id=user_id, date=target_date).first()
    suggested_disc = 10
    att_status = "N/A"
    if att:
        att_status = att.status
        if att.status == 'Late': suggested_disc = 8
        elif att.status == 'Absent': suggested_disc = 0
        elif att.status in ['Leave', 'Weekend']: suggested_disc = None # Không chấm
        
    return suggested_qty, suggested_disc, att_status, done_count, len(tasks)

@bp.route('/api/performance/daily-sheet', methods=['GET'])
@login_required
def get_performance_sheet():
    date_str = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    target_date = datetime.strptime(date_str, '%Y-%m-%d').date()

    users = User.query.order_by(User.username).all()
    perfs = DailyPerformance.query.filter_by(date=target_date).all()
    perf_map = {p.user_id: p for p in perfs}

    result = []
    for u in users:
        p = perf_map.get(u.id)
        
        # Tính toán gợi ý live
        s_qty, s_disc, att_status, done, total = _calculate_auto_scores(u.id, target_date)

        # Logic hiển thị: Nếu DB có thì lấy DB, không thì lấy Gợi ý
        d_qty = p.quantity_score if (p and p.quantity_score is not None) else s_qty
        d_disc = p.discipline_score if (p and p.discipline_score is not None) else s_disc
        
        # Điểm thủ công (nếu chưa có thì là None để UI hiển thị "-")
        d_qual = p.quality_score if p else None
        d_att = p.attitude_score if p else None
        
        # Tính final score để hiển thị (Preview) nếu DB chưa có
        if p and p.final_score > 0:
            final_disp = p.final_score
        else:
            # Tính tạm để hiện lên UI cho đẹp
            # Coi None là 0 khi tính tạm, hoặc lấy giá trị mặc định 5
            v_qty = d_qty or 0
            v_qual = d_qual or 0
            v_att = d_att or 0
            v_disc = d_disc or 0
            # Chia 4
            final_disp = round((v_qty + v_qual + v_att + v_disc)/4, 2) if (d_qual or d_att) else '-'

        result.append({
            'user_id': u.id, 'username': u.username,
            'meta': {'done_tasks': done, 'total_tasks': total, 'att_status': att_status},
            'scores': {
                'quantity': d_qty, 'quality': d_qual, 'attitude': d_att, 'discipline': d_disc
            },
            'comments': {
                'quantity': p.quantity_comment if p else '',
                'quality': p.quality_comment if p else '',
                'attitude': p.attitude_comment if p else '',
                'discipline': p.discipline_comment if p else '',
                'general': p.comment if p else ''
            },
            'final_score': final_disp
        })
    return jsonify({'success': True, 'data': result})

@bp.route('/api/performance/update', methods=['POST'])
@login_required
def update_performance():
    data = request.json
    user_id = data.get('user_id')
    date_str = data.get('date')
    field = data.get('field')
    value = data.get('value')

    target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    perf = DailyPerformance.query.filter_by(user_id=user_id, date=target_date).first()
    
    # Nếu chưa có record, tạo mới
    if not perf:
        perf = DailyPerformance(user_id=user_id, date=target_date)
        db.session.add(perf)
    
    # [FIX] Tự động điền các điểm Gợi ý vào DB nếu chúng đang trống (để tính trung bình cho đúng)
    s_qty, s_disc, _, _, _ = _calculate_auto_scores(user_id, target_date)
    if perf.quantity_score is None: perf.quantity_score = s_qty
    if perf.discipline_score is None: perf.discipline_score = s_disc
    
    # Cập nhật trường đang sửa
    if hasattr(perf, field):
        if 'score' in field:
            if value == '' or value is None: setattr(perf, field, None)
            else: setattr(perf, field, float(value))
        else:
            setattr(perf, field, str(value).strip())
            
    # Tính toán lại Final Score và lưu
    perf.calculate_final()
    db.session.commit()
    return jsonify({'success': True, 'final_score': perf.final_score})

@bp.route('/api/performance/analytics', methods=['GET'])
@login_required
def get_performance_analytics():
    period = request.args.get('period', 'month')
    ref_date_str = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    ref_date = datetime.strptime(ref_date_str, '%Y-%m-%d').date()
    
    start_date, end_date = get_date_range_for_analytics(period, ref_date) # Helper function (defined below or inline)
    
    # --- 1. Query Ranking Data ---
    perfs = DailyPerformance.query.filter(DailyPerformance.date >= start_date, DailyPerformance.date <= end_date).all()
    user_stats = defaultdict(lambda: {'count': 0, 'qty': 0, 'qual': 0, 'att': 0, 'disc': 0, 'final': 0, 'username': ''})
    all_users = User.query.all()
    user_map = {u.id: u.username for u in all_users}
    
    issues_list = [] # Danh sách vấn đề

    for p in perfs:
        s = user_stats[p.user_id]
        s['username'] = user_map.get(p.user_id, 'Unknown')
        s['count'] += 1
        s['qty'] += (p.quantity_score or 0)
        s['qual'] += (p.quality_score or 0)
        s['att'] += (p.attitude_score or 0)
        s['disc'] += (p.discipline_score or 0)
        s['final'] += (p.final_score or 0)
        
        # --- 2. Lọc Vấn đề (Issues Log) ---
        # Điều kiện: Điểm thành phần < 6 hoặc Điểm tổng < 5 hoặc Có comment tiêu cực (tùy chỉnh)
        is_issue = False
        issue_details = []
        
        if (p.quantity_score or 10) < 5: issue_details.append(f"SL Thấp ({p.quantity_score})")
        if (p.quality_score or 10) < 5: issue_details.append(f"CL Kém ({p.quality_score})")
        if (p.attitude_score or 10) < 5: issue_details.append(f"Thái độ ({p.attitude_score})")
        if (p.discipline_score or 10) < 8: issue_details.append(f"Kỷ luật ({p.discipline_score})")
        
        # Check comment nếu có
        comments = []
        if p.quantity_comment: comments.append(p.quantity_comment)
        if p.quality_comment: comments.append(p.quality_comment)
        if p.attitude_comment: comments.append(p.attitude_comment)
        if p.discipline_comment: comments.append(p.discipline_comment)
        if p.comment: comments.append(p.comment)
        
        if issue_details: # Nếu có điểm kém
            issues_list.append({
                'date': p.date.strftime('%d/%m'),
                'username': user_map.get(p.user_id, 'Unknown'),
                'issues': ", ".join(issue_details),
                'note': "; ".join(comments) if comments else "Không có ghi chú"
            })

    ranking_result = []
    for uid, s in user_stats.items():
        if s['count'] > 0:
            ranking_result.append({
                'username': s['username'], 'days_count': s['count'],
                'avg_qty': round(s['qty']/s['count'], 1), 'avg_qual': round(s['qual']/s['count'], 1),
                'avg_att': round(s['att']/s['count'], 1), 'avg_disc': round(s['disc']/s['count'], 1),
                'avg_final': round(s['final']/s['count'], 2)
            })
    ranking_result.sort(key=lambda x: x['avg_final'], reverse=True)
    
    # Sort issues theo ngày mới nhất
    issues_list.sort(key=lambda x: x['date'], reverse=True)

    return jsonify({
        'success': True, 
        'ranking': ranking_result, 
        'issues': issues_list,
        'period_text': f"{start_date.strftime('%d/%m')} - {end_date.strftime('%d/%m/%Y')}"
    })

def get_date_range_for_analytics(period, ref_date):
    if period == 'month': return ref_date.replace(day=1), ref_date.replace(day=monthrange(ref_date.year, ref_date.month)[1])
    elif period == 'quarter':
        q = (ref_date.month - 1) // 3 + 1
        s_m = (q - 1) * 3 + 1
        return ref_date.replace(month=s_m, day=1), ref_date.replace(month=s_m+2, day=monthrange(ref_date.year, s_m+2)[1])
    elif period == 'year': return ref_date.replace(month=1, day=1), ref_date.replace(month=12, day=31)
    else: return ref_date.replace(day=1), ref_date 


# =======================================================
# API TẠO TASK HÀNG LOẠT (BULK CREATE)
# =======================================================
@bp.route('/api/tasks/bulk-create', methods=['POST'])
@login_required
def bulk_create_tasks():
    data = request.json
    tasks_data = data.get('tasks', []) # Danh sách các object {what, who_id, date}
    origin_note_id = data.get('note_id') # [MỚI] Nhận ID của Note gốc
    
    if not tasks_data:
        return jsonify({'success': False, 'message': 'Không có dữ liệu.'}), 400
        
    created_count = 0
    try:
        # Kiểm tra Note có tồn tại không (optional, để an toàn)
        if origin_note_id:
            note_exists = Note.query.get(origin_note_id)
            if not note_exists:
                origin_note_id = None # Nếu ID rác thì bỏ qua

        for item in tasks_data:
            what = item.get('what', '').strip()
            if not what: continue
            
            # Xử lý ngày tháng
            date_str = item.get('date')
            try:
                task_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.today().date()
            except ValueError:
                task_date = datetime.today().date()
            
            # Xử lý người làm
            who_id = item.get('who_id')
            if who_id == 'none' or not who_id: 
                who_id = None
            else:
                try:
                    who_id = int(who_id)
                except ValueError:
                    who_id = None

            new_task = Task(
                what=what,
                task_date=task_date,
                who_id=who_id,
                status='Pending',
                priority='Medium',
                hour=None,
                origin_note_id=origin_note_id # [MỚI] Gắn ID Note vào Task
            )
            db.session.add(new_task)
            created_count += 1
            
        db.session.commit()
        
        msg = f'Đã tạo thành công {created_count} công việc!'
        if origin_note_id:
            msg += ' (Đã liên kết với Note)'
            
        return jsonify({'success': True, 'message': msg})
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Bulk Create Error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@bp.route('/api/notes/bulk-create', methods=['POST'])
@login_required
def bulk_create_notes():
    data = request.json
    column_id = data.get('column_id')
    titles = data.get('titles', []) # Danh sách các tiêu đề note

    if not column_id or not titles:
        return jsonify({'success': False, 'message': 'Thiếu dữ liệu (Cột hoặc Danh sách note).'}), 400

    try:
        # Kiểm tra column có tồn tại không
        column = Column.query.get(column_id)
        if not column:
            return jsonify({'success': False, 'message': 'Cột không tồn tại.'}), 404

        count = 0
        for title in titles:
            clean_title = title.strip()
            if clean_title:
                new_note = Note(
                    title=clean_title,
                    content="", # Nội dung mặc định rỗng
                    column_id=int(column_id),
                    creator_id=current_user.id,
                    label=None
                )
                db.session.add(new_note)
                count += 1
        
        db.session.commit()
        return jsonify({'success': True, 'message': f'Đã tạo thành công {count} ghi chú vào cột "{column.name}"!'})
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Bulk Create Notes Error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
# [THÊM VÀO routes.py]

# [TÌM VÀ THAY THẾ HÀM parse_note_to_tasks TRONG routes.py]

# [TÌM VÀ THAY THẾ HÀM parse_note_to_tasks TRONG routes.py]

@bp.route('/api/notes/parse-to-tasks', methods=['POST'])
@login_required
def parse_note_to_tasks():
    data = request.json
    note_content = data.get('content', '')
    
    if not note_content:
        return jsonify({'success': False, 'message': 'Nội dung note trống.'}), 400

    parsed_tasks = []
    today_str = date.today().strftime('%Y-%m-%d')
    
    # 1. Lấy danh sách User để mapping PIC
    all_users = User.query.all()
    user_map = {u.username.lower(): u.id for u in all_users}

    lines = note_content.split('\n')
    
    for line in lines:
        clean_line = line.strip()
        if not clean_line: continue

        task_content = None
        who_id = None # Mặc định là None để Frontend xử lý (hoặc để user chọn)
        
        # --- CASE A: BẢNG MARKDOWN ---
        if '|' in clean_line:
            parts = [p.strip() for p in clean_line.split('|') if p.strip()]
            if not parts: continue
            
            first_col = parts[0].lower()
            # Bỏ qua header
            if 'job' in first_col or 'task' in first_col or 'nội dung' in first_col or '---' in first_col:
                continue
            
            # Lấy nội dung
            raw_content = parts[0]
            task_content = re.sub(r'^[\d]+[-\.]\s*', '', raw_content).strip()
            
            # Lấy PIC (nếu có)
            if len(parts) >= 2:
                pic_name = parts[1].lower()
                for u_name, u_id in user_map.items():
                    if u_name in pic_name:
                        who_id = u_id
                        break

        # --- CASE B: LIST/CHECKLIST ---
        elif clean_line.startswith(('-', '*', '[ ]', '- [ ]')):
            task_content = clean_line.replace('- [ ]', '').replace('[ ]', '').lstrip('-').lstrip('*').strip()

        # --- TỔNG HỢP KẾT QUẢ ---
        if task_content:
            parsed_tasks.append({
                'what': task_content,
                'who_id': who_id if who_id else current_user.id, # Mặc định gán cho mình nếu ko tìm thấy
                'date': today_str
            })

    # TRẢ VỀ JSON CHỨ KHÔNG LƯU VÀO DB
    return jsonify({
        'success': True, 
        'count': len(parsed_tasks),
        'tasks': parsed_tasks # Danh sách task để frontend hiện lên bảng review
    })
 
@bp.route('/daily-report')
@login_required
def daily_report():
    date_str = request.args.get('date')
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()
    except (ValueError, TypeError):
        target_date = date.today()

    # [TÍCH HỢP X3] Lấy dữ liệu X3 Plan cho ngày hiện tại
    x3_plan = DailyPlan.query.filter_by(user_id=current_user.id, date=target_date).first()

    # 1. LOAD PROJECTS
    active_projects = Project.query.options(subqueryload(Project.builds)).filter(Project.status != 'Done').order_by(Project.position, Project.name).all()
    project_ids = [p.id for p in active_projects]

    # 2. LOAD ISSUES (Group I)
    relevant_reports = DailyReportData.query.options(
        joinedload(DailyReportData.tasks).subqueryload(Task.sub_tasks)
    ).filter(
        DailyReportData.project_id.in_(project_ids),
        DailyReportData.created_at <= target_date,
        or_(
            DailyReportData.report_date == target_date,
            and_(DailyReportData.report_date < target_date, DailyReportData.is_resolved.in_([0, False, '0']))
        )
    ).all()

    report_map = defaultdict(list)
    for r in relevant_reports:
        report_map[r.project_id].append(r)

    # 3. LOAD TASKS (Group II) & CALCULATE PROGRESS (NEW LOGIC)
    all_tasks_raw = Task.query.filter(
        or_(
            and_(
                Task.start_date.isnot(None),
                Task.start_date <= target_date,
                Task.task_date >= target_date
            ),
            and_(
                Task.start_date.is_(None),
                Task.task_date == target_date
            ),
            and_(
                Task.task_date < target_date, 
                Task.status.notin_(['Done', 'Drop'])
            )
        )
    ).options(
        joinedload(Task.assignee), 
        subqueryload(Task.sub_tasks),
        joinedload(Task.key_result).joinedload(KeyResult.objective)
    ).all()

    task_map = defaultdict(list)
    unassigned_tasks = []
    
    total_day_tasks = 0.0 # Tính theo số lượng Task (1 Task = 1 Điểm)
    done_day_score = 0.0  # Điểm hoàn thành thực tế

    for t in all_tasks_raw:
        if t.status == 'Drop':
            continue

        p_id = None
        if t.key_result and t.key_result.objective:
            p_id = t.key_result.objective.project_id
        elif t.daily_report_item_id:
            issue_link = DailyReportData.query.get(t.daily_report_item_id)
            if issue_link: p_id = issue_link.project_id
        
        if not p_id:
            for p in active_projects:
                if f"[{p.name}]" in t.what:
                    p_id = p.id
                    break

        # [BỔ SUNG CHO X3] Ánh xạ project info
        t.mapped_project_id = p_id
        t.mapped_project_name = next((p.name for p in active_projects if p.id == p_id), None) if p_id else None

        # --- LOGIC TÍNH ĐIỂM MỚI (1 TASK = 1 ĐIỂM) ---
        sub_tasks = t.sub_tasks
        task_score = 0.0

        if sub_tasks:
            done_st = sum(1 for st in sub_tasks if st.is_done)
            total_st = len(sub_tasks)
            task_score = done_st / total_st if total_st > 0 else 0
            t.progress_pct = int(task_score * 100)
        else:
            task_score = 1.0 if t.status == 'Done' else 0.0
            t.progress_pct = 100 if t.status == 'Done' else 0

        if p_id and p_id in project_ids:
            task_map[p_id].append(t)
            total_day_tasks += 1.0
            done_day_score += task_score
        else:
            unassigned_tasks.append(t)

    # % Hoàn thành tổng (Làm tròn)
    day_progress = int((done_day_score / total_day_tasks * 100)) if total_day_tasks > 0 else 0

    # 4. TỔNG HỢP DỮ LIỆU
    final_data = []
    for p in active_projects:
        current_build_name = "N/A"
        active_build_id = None
        if p.builds:
            active_build = next((b for b in p.builds if b.start_date and b.start_date <= target_date and (not b.end_date or b.end_date >= target_date)), None)
            current_build_name = active_build.name if active_build else "Running"
            active_build_id = active_build.id if active_build else (p.builds[0].id if len(p.builds) > 0 else None)
        
        final_data.append({
            'project': p, 
            'active_build_name': current_build_name,
            'active_build_id': active_build_id,
            'entries': report_map.get(p.id, []),
            'tasks': task_map.get(p.id, [])
        })

    # --- [BỔ SUNG CHO X3] XỬ LÝ 3 CỘT X3 TỪ TẤT CẢ TASKS (Gom cả project) ---
    # SỬA LỖI: Bỏ màng lọc assignee để lấy TRỌN VẸN toàn bộ task trong ngày (không bị mất task quick add)
    my_tasks = [t for t in all_tasks_raw if t.status != 'Drop']
    
    col1_data = [t for t in my_tasks if t.hour is not None]
    col1_data.sort(key=lambda x: str(x.hour)) # Sắp xếp lịch cố định theo giờ
    col3_data = [t for t in my_tasks if t.hour is None]

    # Lấy dữ liệu Thói quen y như code cũ của X3
    habits = Habit.query.filter_by(user_id=current_user.id, is_active=True).all()
    for h in habits:
        log = HabitLog.query.filter_by(habit_id=h.id, date_logged=target_date).first()
        h.log_done = log.is_done if log else False
    # --- END BỔ SUNG ---

    users = User.query.all()
    user_options_html = "".join([f'<option value="{u.id}">{u.username}</option>' for u in users])
    all_projects_json = [{'id': p.id, 'name': p.name} for p in active_projects]

    return render_template('daily_report.html', 
                           report_data=final_data, 
                           col1_data=col1_data,    
                           col3_data=col3_data,    
                           habits=habits,          
                           date_str=target_date.strftime('%Y-%m-%d'),
                           prev_date=(target_date - timedelta(days=1)).strftime('%Y-%m-%d'),
                           next_date=(target_date + timedelta(days=1)).strftime('%Y-%m-%d'),
                           today_date_str=date.today().strftime('%Y-%m-%d'),
                           target_date=target_date,
                           day_progress=day_progress,
                           done_day_score=round(done_day_score, 1), # Gửi điểm thực tế ra UI
                           total_day_tasks=int(total_day_tasks),    # Gửi tổng task ra UI
                           user_options_html=user_options_html,
                           all_projects=all_projects_json,
                           x3_plan=x3_plan)

@bp.route('/api/x3/summarize-kaizen', methods=['GET'])
@login_required
def summarize_kaizen():
    """API trợ lý tự động tổng hợp Kaizen dựa trên công việc trong ngày của User"""
    date_str = request.args.get('date', datetime.today().strftime('%Y-%m-%d'))
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        target_date = datetime.today().date()
        
    # Lấy các task Đã Xong trong ngày
    done_tasks = Task.query.filter(
        Task.who_id == current_user.id,
        Task.task_date == target_date,
        Task.status == 'Done'
    ).all()
    
    # Lấy Tiêu điểm ngày
    plan = DailyPlan.query.filter_by(user_id=current_user.id, date=target_date).first()
    
    # Xử lý Logic tự động điền
    result_text = ""
    if done_tasks:
        task_names = [t.what for t in done_tasks[:3]] # Lấy 3 việc chính
        result_text = "Hoàn thành: " + ", ".join(task_names)
        if len(done_tasks) > 3:
            result_text += f" và {len(done_tasks) - 3} việc khác."
    else:
        result_text = "Chưa hoàn thành các hạng mục đã đề ra."
        
    lesson_text = "Lập kế hoạch sát thực tế hơn để đảm bảo tiến độ."
    action_text = "Tập trung giải quyết dứt điểm các task tồn đọng ngay đầu giờ sáng mai."
    
    # Nếu user đã nhập Pain Point, AI (hoặc rule base) sẽ đưa ra action tương ứng
    if plan and plan.pain_point:
        lesson_text = f"Nhận diện được rủi ro từ '{plan.pain_point}' là kinh nghiệm quan trọng."
        action_text = f"Đưa ra đối sách phòng ngừa cụ thể cho rủi ro này vào ngày mai."

    return jsonify({
        'success': True,
        'summary': {
            'result': result_text,
            'lesson': lesson_text,
            'action': action_text
        }
    })                           
@bp.route('/api/task/<int:task_id>/update-link', methods=['POST'])
@login_required
def update_task_link(task_id):
    """API lưu report_link ĐỘC LẬP cho từng Task"""
    data = request.json
    new_link = data.get('report_link', '').strip()
    
    task = Task.query.get(task_id)
    if not task:
        return jsonify({'success': False, 'message': 'Task not found'}), 404
        
    try:
        # Lưu link trực tiếp vào bảng Task
        task.report_link = new_link
        db.session.commit()
        return jsonify({'success': True, 'message': 'Link saved to Task!'})
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saving report link: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@bp.route('/api/daily-report/update-cell', methods=['POST'])
@login_required
def api_update_report_cell():
    data = request.json
    item_id = str(data.get('id'))
    field = data.get('field')
    val = data.get('value')
    date_str = data.get('date')
    
    try:
        curr_report_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        if item_id.startswith('temp-'):
            project_id = int(data.get('project_id'))
            item = DailyReportData(
                project_id=project_id, 
                report_date=curr_report_date,
                is_resolved=0, # Dùng số 0
                has_data=1
            )
            db.session.add(item)
            db.session.flush()
        else:
            item = DailyReportData.query.get_or_404(int(item_id))

        if field == 'is_resolved':
            # ÉP KIỂU SỐ NGUYÊN 1/0 KHI LƯU (SQLite sẽ không bị nhầm lẫn)
            is_done_int = 1 if (val is True or str(val).lower() in ['true', '1']) else 0
            item.is_resolved = is_done_int
            
            # Nếu XONG (tick), ghi nhận ngày hoàn thành là ngày hôm nay
            if is_done_int == 1:
                item.report_date = curr_report_date
            # Nếu BỎ TICK, issue này sẽ vẫn giữ report_date cũ và tự động carry over nếu cần
        
        elif hasattr(item, field):
            setattr(item, field, str(val).strip() if (val and str(val).lower() != 'none') else "")
            item.has_data = 1

        db.session.commit()
        
        # Trả về kết quả thực tế sau khi đã ép kiểu lại một lần nữa
        final_status = True if item.is_resolved in [1, '1', True] else False
        return jsonify({
            'success': True, 
            'id': item.id, 
            'is_resolved': final_status
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Lỗi cập nhật Daily Report: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@bp.route('/api/daily-report/delete-item/<int:item_id>', methods=['POST'])
@login_required
def api_delete_report_item(item_id):
    item = DailyReportData.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    return jsonify({'success': True})


# Tìm và thay thế đoạn code xử lý Task Status và thêm Create Task API

@bp.route('/api/daily-report/create-task', methods=['POST'])
@login_required
def create_task_from_issue():
    """API để tạo Task từ một Issue trong Daily Report"""
    data = request.json
    issue_id = data.get('issue_id')
    issue_text = data.get('issue_text')
    project_id = data.get('project_id')
    
    if not issue_id or not issue_text:
        return jsonify({'success': False, 'message': 'Missing Issue ID or Description.'}), 400
        
    try:
        # Tạo Task mới liên kết với Issue
        new_task = Task(
            what=f"{issue_text}",
            task_date=date.today(),
            who_id=current_user.id,
            status='Pending',
            priority='High',
            daily_report_item_id=issue_id # Mỏ neo liên kết
        )
        db.session.add(new_task)
        db.session.commit()
        
        # Ghi log
        db.session.add(Log(action=f"Created Task ID {new_task.id} from Issue #{issue_id}", user_id=current_user.id))
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Task created and linked successfully!',
            'task': new_task.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

# THAY THẾ HÀM update_task_status CỦA BẠN BẰNG ĐOẠN SAU:
@bp.route('/update-task-status', methods=['POST'])
@login_required
def update_task_status():
    """Cập nhật trạng thái Task và tự động đồng bộ % Global"""
    data = request.json
    try:
        task_id = data.get('taskId')
        new_status = data.get('newStatus')
        
        if not task_id or not new_status:
            return jsonify({'success': False, 'message': 'Missing taskId or newStatus'}), 400

        task = Task.query.get(task_id)
        if not task:
            return jsonify({'success': False, 'message': 'Task not found'}), 404
        
        old_status = task.status
        task.status = new_status
        
        if new_status == 'Done':
            task.task_date = date.today()
            if task.start_date and task.start_date > task.task_date:
                task.start_date = task.task_date
        
        if new_status == 'Done' and task.daily_report_item_id:
            issue = DailyReportData.query.get(task.daily_report_item_id)
            if issue:
                issue.is_resolved = 1
                issue.report_date = date.today()

        db.session.add(Log(action=f"Changed status '{task.what}' from {old_status} to {new_status}", user_id=current_user.id))
        db.session.commit() # Commit để lát query lấy data mới nhất
        
        # --- TÍNH LẠI % GLOBAL PROGRESS ---
        report_date = date.today()
        all_tasks_for_day = Task.query.filter(
            or_(
                and_(Task.start_date.isnot(None), Task.start_date <= report_date, Task.task_date >= report_date),
                and_(Task.start_date.is_(None), Task.task_date == report_date),
                and_(Task.task_date < report_date, Task.status.notin_(['Done', 'Drop']))
            )
        ).options(subqueryload(Task.sub_tasks)).all()
        
        active_projects = Project.query.filter(Project.status != 'Done').all()
        project_ids = [p.id for p in active_projects]
        
        total_day_tasks = 0.0
        done_day_score = 0.0
        
        for t in all_tasks_for_day:
            if t.status == 'Drop': continue
            p_id = None
            if t.key_result_id:
                kr = KeyResult.query.get(t.key_result_id)
                if kr and kr.objective: p_id = kr.objective.project_id
            elif t.daily_report_item_id:
                issue = DailyReportData.query.get(t.daily_report_item_id)
                if issue: p_id = issue.project_id
                
            if not p_id:
                for p in active_projects:
                    if f"[{p.name}]" in t.what:
                        p_id = p.id; break

            if p_id and p_id in project_ids:
                sts = t.sub_tasks
                if sts:
                    total_st = len(sts)
                    task_score = sum(1 for st in sts if st.is_done) / total_st if total_st > 0 else 0
                else:
                    task_score = 1.0 if t.status == 'Done' else 0.0
                    
                total_day_tasks += 1.0
                done_day_score += task_score
                
        global_progress = int((done_day_score / total_day_tasks * 100)) if total_day_tasks > 0 else 0

        return jsonify({
            'success': True, 
            'message': 'Status updated!',
            'task': task.to_dict(),
            'global_progress': global_progress # Trả data mới về Frontend
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in update_task_status: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
        
# UPDATE cho checklist
@bp.route('/api/subtask/reorder', methods=['POST'])
@login_required
def reorder_subtasks():
    data = request.json
    ids = data.get('ids', []) # Danh sách ID theo thứ tự mới: [12, 10, 15...]
    
    try:
        # Cập nhật vị trí cho từng subtask dựa trên index trong mảng gửi lên
        for index, s_id in enumerate(ids):
            st = SubTask.query.get(s_id)
            if st:
                st.position = index
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
@bp.route('/critical-thinking')
@login_required
def critical_thinking():
    """
    Endpoint hiển thị công cụ Master Critical Thinking Template.
    Yêu cầu user phải đăng nhập (login_required).
    """
    # Nếu cần truyền thêm dữ liệu (như ngày tháng, project), anh có thể query DB ở đây
    return render_template('critical_thinking.html')

# --- TÌM VÀ THAY THẾ TOÀN BỘ CỤM HÀM LIÊN QUAN ĐẾN LINE STATUS TRONG routes.py BẰNG ĐOẠN NÀY ---

def process_line_status_file(project_id):
    """
    Hàm lõi: Đọc file line_status.xlsx, lọc theo Tên Project và lưu vào DB.
    File Excel BẮT BUỘC có các cột: Project, Build, Process, Inline, Takt Time, Efficiency...
    """
    project = Project.query.get(project_id)
    if not project:
        return False, "Không tìm thấy Project"

    try:
        # File phải nằm trong app/uploads hoặc cấu hình UPLOAD_FOLDER của bạn
        file_name = 'line_master.xlsx' 
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], file_name)
        
        if not os.path.exists(file_path):
            return False, "Vui lòng Upload file Line Status (File chưa tồn tại trên máy chủ)."
            
        df = pd.read_excel(file_path, engine='openpyxl')
        df.columns = df.columns.str.strip().str.lower()
        
        # Ánh xạ cột (Mapping)
        col_map = {
            'project': 'project_name', 'build': 'build_name', 'process': 'process', 
            'inline': 'inline', 'gib': 'gib', 'takt time': 'takt_time', 
            'efficiency': 'efficiency', 'ch': 'ch', 'ch avail': 'ch_available', 'ch available': 'ch_available', 
            'capa': 'capa', 'issue': 'issue', 'reason': 'reason', 
            'action': 'action', 'status': 'status', 'link': 'link'
        }
        df.rename(columns=col_map, inplace=True)
        
        # BẮT BUỘC: File phải có cột Project và Build
        if 'project_name' not in df.columns or 'build_name' not in df.columns:
            return False, "File Excel thiếu cột 'Project' hoặc 'Build'."
            
        # Tự động lọc dữ liệu của Project hiện tại
        project_df = df[df['project_name'] == project.name].copy()
        
        today = date.today()
        # Xóa data cũ trong ngày của Project này
        LineStatus.query.filter_by(project_id=project_id, report_date=today).delete()

        if project_df.empty:
            db.session.commit()
            return True, f"File không có dữ liệu nào khớp với Project '{project.name}'."

        new_records = []
        for _, row in project_df.iterrows():
            if pd.isna(row.get('build_name')): continue
            
            # Lấy data và loại bỏ NaN
            record_data = row.where(pd.notnull(row), None).to_dict()
            
            valid_keys = ['build_name', 'process', 'inline', 'gib', 'takt_time', 
                          'efficiency', 'ch', 'ch_available', 'capa', 
                          'issue', 'reason', 'action', 'status', 'link']
            filtered_data = {k: v for k, v in record_data.items() if k in valid_keys}

            new_records.append(LineStatus(project_id=project_id, report_date=today, **filtered_data))

        if new_records:
            db.session.bulk_save_objects(new_records)
            db.session.commit()
            
        return True, "Đồng bộ dữ liệu thành công!"
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Lỗi sync Line Status: {e}")
        return False, f"Lỗi đọc file Excel: {str(e)}"


@bp.route('/api/project/<int:project_id>/line-status', methods=['GET'])
@login_required
def get_line_status(project_id):
    """
    CHỈ XEM: Load dữ liệu rất nhanh từ Database. Tuyệt đối không đọc lại file Excel.
    """
    target_date_str = request.args.get('date', date.today().strftime('%Y-%m-%d'))
    try:
        target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
    except ValueError:
        target_date = date.today()
    
    records = LineStatus.query.filter_by(project_id=project_id, report_date=target_date).all()
    
    # Gom nhóm theo Build (Compare by Build)
    data_by_build = defaultdict(list)
    for r in records:
        data_by_build[r.build_name].append(r.to_dict())

    return jsonify({
        'success': True, 
        'data': dict(data_by_build)
    })


@bp.route('/api/project/<int:project_id>/line-status/sync', methods=['POST'])
@login_required
def sync_line_status_data(project_id):
    """
    SYNC: Nút 'Tải lại' sẽ gọi API này để ép hệ thống đọc lại file Excel.
    """
    success, msg = process_line_status_file(project_id)
    return jsonify({'success': success, 'message': msg})


@bp.route('/api/project/<int:project_id>/line-status/upload', methods=['POST'])
@login_required
def upload_line_status_file(project_id):
    """
    UPLOAD: Nhận file, lưu lại và tự động Sync.
    """
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Không có file.'}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'Chưa chọn file.'}), 400
        
    try:
        # Lưu file
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'line_status.xlsx')
        file.save(file_path)
        
        # Sync luôn
        success, msg = process_line_status_file(project_id)
        if success:
            return jsonify({'success': True, 'message': 'Upload file và đồng bộ thành công!'})
        else:
            return jsonify({'success': False, 'message': f'Đã lưu file nhưng lỗi đọc dữ liệu: {msg}'})
            
    except Exception as e:
        current_app.logger.error(f"Lỗi upload Line Status: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# THÊM API MỚI NÀY VÀO DƯỚI CÙNG CỦA CỤM LINE STATUS
@bp.route('/api/line-status/update-cell', methods=['POST'])
@login_required
def update_line_status_cell():
    """API lưu dữ liệu Database và ĐỒNG BỘ NGƯỢC vào file Excel (2-Way Sync)"""
    data = request.json
    item_id = data.get('id')
    field = data.get('field')
    val = data.get('value')
    
    try:
        import openpyxl
        item = LineStatus.query.get_or_404(item_id)
        project = Project.query.get(item.project_id)
        
        # 1. Ép kiểu và lưu vào Database
        if field in ['inline', 'gib']: 
            val = int(val) if val and str(val).strip() != '' else 0
        elif field in ['takt_time', 'efficiency', 'ch', 'ch_available', 'capa']: 
            val = float(val) if val and str(val).strip() != '' else 0.0
        else:
            val = str(val).strip() if val else ""
            
        setattr(item, field, val)
        db.session.commit()

        # 2. Ghi ngược lại vào file Excel gốc để đảm bảo không bị mất khi Sync lại
        try:
            file_name = 'line_master.xlsx'
            file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], file_name)
            if os.path.exists(file_path):
                wb = openpyxl.load_workbook(file_path)
                sheet = wb.active
                
                # Tìm Header để biết cột nào
                headers = {}
                for col_idx, cell in enumerate(sheet[1], start=1):
                    if cell.value:
                        headers[str(cell.value).strip().lower()] = col_idx
                
                # Mapping tên field (từ DB) ra tên cột (trong Excel)
                col_map_reverse = {
                    'inline': 'inline', 'gib': 'gib', 'takt_time': 'takt time',
                    'efficiency': 'efficiency', 'ch_available': 'ch avail',
                    'capa': 'capa', 'status': 'status', 'issue': 'issue',
                    'action': 'action', 'link': 'link', 'ch': 'ch'
                }
                
                excel_header_name = col_map_reverse.get(field, field)
                target_col_idx = None
                
                # Tìm khớp tương đối cột trong Excel
                for h_name, idx in headers.items():
                    if excel_header_name in h_name or h_name in excel_header_name:
                        target_col_idx = idx
                        break
                        
                if target_col_idx:
                    proj_col = headers.get('project')
                    build_col = headers.get('build')
                    proc_col = headers.get('process')
                    
                    if proj_col and build_col and proc_col:
                        # Quét các dòng để tìm đúng Process
                        for row in range(2, sheet.max_row + 1):
                            p_val = sheet.cell(row=row, column=proj_col).value
                            b_val = sheet.cell(row=row, column=build_col).value
                            pr_val = sheet.cell(row=row, column=proc_col).value
                            
                            # Khớp Project Name, Build Name, Process Name
                            if str(p_val).strip() == project.name and str(b_val).strip() == item.build_name and str(pr_val).strip() == item.process:
                                # Trả Efficiency về dạng thập phân nếu Excel format là %
                                excel_val = val
                                if field == 'efficiency' and float(val) > 1:
                                    excel_val = float(val) / 100.0
                                    
                                sheet.cell(row=row, column=target_col_idx).value = excel_val
                                wb.save(file_path)
                                break
        except Exception as ex:
            current_app.logger.error(f"Lỗi ghi ngược Excel: {ex}")
            # Bỏ qua lỗi Excel để UI vẫn chạy tiếp bình thường nếu file đang bị ai đó mở

        return jsonify({'success': True, 'message': 'Đã lưu DB và ghi đè Excel!'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Lỗi cập nhật ô Line Status: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500