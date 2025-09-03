import os
import random
from datetime import datetime, timedelta, date, timezone
from sqlalchemy import func, or_
import io
from collections import defaultdict
from calendar import monthrange
import bleach
import json
from bleach.css_sanitizer import CSSSanitizer
from flask import (Blueprint, current_app, flash, jsonify, redirect,
                   render_template, request, send_from_directory, url_for, send_file)
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload, subqueryload
from werkzeug.utils import secure_filename
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import (KeyResult, Log,
                        Objective, Project, Task, UploadedFile, User, Column, Note, PracticeLog, Build)
from app.constants import STATUS_META, TASK_STATUSES
from app.utils import get_date_range, get_time_range_from_filter, _vn_day_bounds_to_utc, to_vn_time, to_utc_time


bp = Blueprint('main', __name__)

def recalculate_kr_progress(kr_id):
    kr = KeyResult.query.get(kr_id)
    if kr:
        action_items_list = list(kr.tasks)
        if action_items_list:
            total_actions = len(action_items_list)
            done_actions = sum(1 for action in action_items_list if action.status == 'Done')
            kr.current = float(done_actions)
            kr.target = float(total_actions) if total_actions > 0 else 1.0
        else:
            kr.current = 0
            kr.target = 0
        db.session.commit()
    return kr

# ==============================================================================
# ROUTE API TẬP TRUNG CHO UPLOAD FILE
# ==============================================================================

@bp.route('/api/upload-attachment', methods=['POST'])
@login_required
def upload_attachment():
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file.'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'Not yet choose file'}), 400

    task_id = request.form.get('task_id')
    note_id = request.form.get('note_id')
    source = request.form.get('source', 'attachment')

    if file:
        original_filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        saved_filename = f"{timestamp}_{original_filename}"
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], saved_filename)
        
        try:
            file.save(file_path)
            file_size = os.path.getsize(file_path)
            _, file_ext = os.path.splitext(original_filename)

            new_file = UploadedFile(
                original_filename=original_filename,
                saved_filename=saved_filename,
                file_type=file_ext.lower(),
                file_size=file_size,
                uploader_id=current_user.id,
                upload_source=source
            )
            
            if task_id: 
                new_file.task_id = int(task_id)
            if note_id: 
                new_file.note_id = int(note_id)
            
            db.session.add(new_file)
            db.session.commit()
            
            return jsonify({ 'success': True, 'file': new_file.to_dict() })
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Error happend: {str(e)}'}), 500
            
    return jsonify({'success': False, 'message': 'Error dont define'}), 500

@bp.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)

@bp.route('/delete-uploaded-file/<int:file_id>', methods=['POST'])
@login_required
def delete_uploaded_file(file_id):
    uploaded_file = UploadedFile.query.get_or_404(file_id)
    try:
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], uploaded_file.saved_filename)
        if os.path.exists(file_path):
            os.remove(file_path)
        
        db.session.delete(uploaded_file)
        db.session.commit()
        return jsonify({'success': True, 'message': 'File deleted!'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error when delete file: {str(e)}'}), 500

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

@bp.route('/')
@bp.route('/calendar/<string:view_mode>/<string:date_str>')
@login_required
def index(view_mode='week', date_str=None):
    # Lấy user_id từ URL, mặc định là 'all' để hiển thị tất cả
    selected_user_id = request.args.get('user_id', 'all')

    if date_str is None:
        date_str = datetime.today().strftime('%Y-%m-%d')

    # Tính toán các khoảng thời gian dựa trên view_mode
    start_date, end_date, date_display = get_date_range(view_mode, date_str)
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
        context.update({'hours': range(8, 20)})
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

# TÌM HÀM save_task VÀ THAY THẾ TOÀN BỘ BẰNG CODE NÀY

@bp.route('/save-task', methods=['POST'])
@login_required
def save_task():
    data = request.form
    # SỬA LỖI 1: Lấy đúng key 'taskId' từ form, không phải 'id'
    task_id = data.get('taskId') 
    
    what = bleach.clean(data.get('taskWhat', ''))
    task_date_str = data.get('taskDate')
    
    if not what or not task_date_str:
        return jsonify({'success': False, 'message': 'Task title and date are required.'}), 400

    try:
        hour_str = data.get('taskHour')
        who_id_str = data.get('taskWho')
        key_result_id_str = data.get('taskKeyResult')
        end_date_str = data.get('taskRecurrenceEndDate')
        recurrence = data.get('taskRecurrence', 'none')

        task_date = datetime.strptime(task_date_str, '%Y-%m-%d').date()
        hour = int(hour_str) if hour_str else None
        who_id = int(who_id_str) if who_id_str else None
        key_result_id = int(key_result_id_str) if key_result_id_str else None
        recurrence_end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str and recurrence != 'none' else None
    except (ValueError, TypeError) as e:
        current_app.logger.error(f"Error parsing form data for task save: {e}")
        return jsonify({'success': False, 'message': 'Invalid data format submitted.'}), 400

    if task_id:
        task = Task.query.get_or_404(task_id)
        log_content = f"Updated task ID {task.id}"
    else:
        task = Task()
        db.session.add(task)
        log_content = "Created new task"

    task.what = what
    task.task_date = task_date
    task.hour = hour
    task.who_id = who_id
    task.status = data.get('taskStatus', 'Pending')
    task.note = bleach.clean(data.get('taskNote', ''))
    task.priority = data.get('taskPriority', 'Medium')
    task.key_result_id = key_result_id
    task.recurrence = recurrence
    task.recurrence_end_date = recurrence_end_date
    
    # Commit để lưu thông tin chính và lấy task.id nếu là task mới
    db.session.commit()
    
    # SỬA LỖI 2: Thêm logic xử lý file upload
    try:
        files = request.files.getlist('attachments[]')
        for file in files:
            if file and file.filename != '':
                original_filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                saved_filename = f"{timestamp}_{original_filename}"
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
                    task_id=task.id  # Gắn file vào task vừa lưu
                )
                db.session.add(new_file)
    except Exception as e:
        current_app.logger.error(f"Error handling file upload for task {task.id}: {e}")
        # Không cần rollback vì thông tin task chính đã lưu thành công
        pass # Bỏ qua nếu có lỗi upload file
    
    # Xử lý các logic phụ và log
    db.session.add(Log(action=f"{log_content}: '{what}'", user_id=current_user.id))
    
    if not task_id and recurrence != 'none' and recurrence_end_date:
        # (Giữ nguyên logic tạo task lặp lại của bạn)
        current_date, original_day = task.task_date, task.task_date.day
        while True:
            if recurrence == 'daily': current_date += timedelta(days=1)
            elif recurrence == 'weekly': current_date += timedelta(days=7)
            elif recurrence == 'monthly':
                next_month, next_year = (current_date.month + 1, current_date.year)
                if next_month > 12: next_month, next_year = 1, next_year + 1
                last_day = monthrange(next_year, next_month)[1]
                current_date = date(next_year, next_month, min(original_day, last_day))

            if current_date > recurrence_end_date: break
            if not Task.query.filter_by(task_date=current_date, hour=task.hour, what=task.what).first():
                db.session.add(Task(task_date=current_date, hour=task.hour, what=task.what, who_id=task.who_id, status=task.status, note=task.note, recurrence='none', key_result_id=key_result_id or None))

    db.session.commit()
    db.session.refresh(task)
    return jsonify({'success': True, 'task': task.to_dict(), 'message': 'Task saved successfully!'})
# HÀM 2: TẠO API MỚI api_get_task
@bp.route('/api/task/<int:task_id>')
@login_required
def api_get_task(task_id):
    """API để lấy chi tiết một task, dùng cho modal trên Gantt."""
    task = Task.query.options(
        joinedload(Task.attachments), 
        joinedload(Task.assignee)
    ).get_or_404(task_id)
    return jsonify({'success': True, 'task': task.to_dict()})

# HÀM 3: CẬP NHẬT HÀM api_dhtmlx_data
@bp.route('/api/dhtmlx-data')
@login_required
def api_dhtmlx_data():
    project_id = request.args.get('project_id', type=int)
    if not project_id:
        return jsonify({'data': []})

    query = Project.query.options(
        subqueryload(Project.builds)
            .subqueryload(Build.objectives)
            .subqueryload(Objective.key_results)
            .subqueryload(KeyResult.tasks)
            .joinedload(Task.assignee)
    )
    project = query.get(project_id)
    
    if not project:
        return jsonify({'data': []})

    gantt_data = []

    def calculate_progress(tasks):
        if not tasks: return 0.0
        done_count = sum(1 for t in tasks if t.status == 'Done')
        return round(done_count / len(tasks), 4) if tasks else 0.0

    proj_id = f'proj-{project.id}'
    if project.start_date and project.end_date:
        gantt_data.append({
            'id': proj_id, 'text': project.name,
            'start_date': project.start_date.isoformat(),
            'end_date': (project.end_date + timedelta(days=1)).isoformat(), # dhtmlx end date is exclusive
            'type': 'project', 'open': True
        })

    for build in project.builds:
        build_id = f'build-{build.id}'
        if build.start_date and build.end_date:
            build_tasks = [task for obj in build.objectives for kr in obj.key_results for task in kr.tasks]
            gantt_data.append({
                'id': build_id, 'text': build.name,
                'start_date': build.start_date.isoformat(),
                'end_date': (build.end_date + timedelta(days=1)).isoformat(),
                'type': 'build', 'parent': proj_id,
                'progress': calculate_progress(build_tasks), 'open': True
            })

        for obj in build.objectives:
            obj_id = f'obj-{obj.id}'
            obj_tasks = [task for kr in obj.key_results for task in kr.tasks]
            
            if obj.start_date:
                obj_end = max([t.task_date for t in obj_tasks if t.task_date] or [None], default=None)
                # === SỬA LỖI: Thay timedelta(days=2) thành timedelta(days=1) ===
                end_date_iso = (obj_end + timedelta(days=1)).isoformat() if obj_end else (obj.start_date + timedelta(days=1)).isoformat()
                gantt_data.append({
                    'id': obj_id, 'text': obj.content,
                    'start_date': obj.start_date.isoformat(),
                    'end_date': end_date_iso,
                    'type': 'objective', 'parent': build_id,
                    'progress': calculate_progress(obj_tasks), 'open': True
                })

                for kr in obj.key_results:
                    kr_id = f'kr-{kr.id}'
                    kr_tasks = kr.tasks
                    kr_start = min([t.task_date for t in kr_tasks if t.task_date] or [None], default=None)
                    kr_end = max([t.task_date for t in kr_tasks if t.task_date] or [None], default=None)

                    if kr_start and kr_end:
                        gantt_data.append({
                            'id': kr_id, 'text': kr.content,
                            'start_date': kr_start.isoformat(),
                            'end_date': (kr_end + timedelta(days=1)).isoformat(),
                            'type': 'key_result', 'parent': obj_id,
                            'progress': calculate_progress(kr_tasks), 'open': True
                        })

                    for task in kr_tasks:
                        if task.task_date:
                            gantt_data.append({
                                'id': f'task-{task.id}', 'text': task.what,
                                'start_date': task.task_date.isoformat(),
                                'end_date': (task.task_date + timedelta(days=1)).isoformat(),
                                'type': 'task', 'parent': kr_id,
                                'owner': task.assignee.username if task.assignee else '',
                                'progress': 1.0 if task.status == 'Done' else 0.0,
                                'priority': task.priority or 'Medium'
                            })

    return jsonify({'data': gantt_data})

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
    task = Task.query.get_or_404(task_id)
    db.session.add(Log(action=f"Deleted event ID {task.id}: '{task.what}'", user_id=current_user.id))
    db.session.delete(task)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Deleted event'})

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
        return redirect(url_for('main.project_workspace'))

    # Check for duplicate name
    existing_project = Project.query.filter_by(name=name).first()
    if existing_project:
        flash(f'Tên dự án "{name}" đã tồn tại. Vui lòng chọn tên khác.', 'warning')
        return redirect(url_for('main.project_workspace'))

    # If not a duplicate, continue
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None
    
    new_project = Project(
        name=name,
        description=request.form.get('description'),
        status=request.form.get('status', 'Active'),
        start_date=start_date,
        end_date=end_date
    )
    db.session.add(new_project)
    db.session.commit()
    flash('Created new project!', 'success')
    
    return redirect(url_for('main.project_workspace'))
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
            return redirect(url_for('main.project_workspace', project_id=project_id, tab='okr'))
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
        build_id=data.get('build_id') or None
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
    
    # === SỬA ĐỔI Ở ĐÂY ===
    # Thêm .strip() để loại bỏ khoảng trắng thừa, và xử lý cả trường hợp giá trị là None
    start_date_str = (data.get('start_date') or '').strip()
    end_date_str = (data.get('end_date') or '').strip()
    # =====================

    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None
    except ValueError:
        # Trả về lỗi rõ ràng nếu định dạng ngày tháng vẫn sai
        return jsonify({'success': False, 'message': 'Invalid date format. Please use YYYY-MM-DD.'}), 400

    new_kr = KeyResult(
        objective_id=data['objective_id'], 
        content=data['content'], 
        start_date=start_date,
        end_date=end_date,
        target=0, 
        current=0
    )
    db.session.add(new_kr)
    db.session.commit()
    db.session.add(Log(action=f"Added KR to Objective ID {data['objective_id']}: '{data['content']}'", user_id=current_user.id))
    db.session.commit()
    
    return jsonify({ 'success': True, 'kr': { 'id': new_kr.id, 'content': new_kr.content, 'progress': 0, 'current': 0, 'target': 0, 'objective_id': new_kr.objective_id } })
    
@bp.route('/update-task-status/<int:task_id>', methods=['POST'])
@login_required
def update_task_from_okr(task_id):
    task = Task.query.get_or_404(task_id)
    task.status = 'Done' if request.json.get('checked') else 'Pending'
    db.session.commit()
    
    status_text = "Hoàn thành" if task.status == 'Done' else "Chuyển về Pending"
    db.session.add(Log(action=f"{status_text} Task ID {task.id}: '{task.what}'", user_id=current_user.id))
    db.session.commit()
    
    kr = recalculate_kr_progress(task.key_result_id)
    
    return jsonify({
        'success': True, 'message': 'Task status and KR progress updated', 
        'kr_id': kr.id, 'objective_id': kr.objective_id,
        'kr_progress': kr.progress, 'obj_progress': kr.objective.progress,
        'kr_current': kr.current, 'kr_target': kr.target
    })
    
@bp.route('/update/<item_type>/<int:item_id>', methods=['POST'])
@login_required
def update_okr_item(item_type, item_id):
    model_map = {'objective': Objective, 'key_result': KeyResult, 'task': Task}
    Model = model_map.get(item_type)
    if not Model: return jsonify({'success': False, 'message': 'Type not suitable'}), 400
    
    item = Model.query.get_or_404(item_id)
    data = request.json
    
    # Cập nhật ngày tháng (nếu có)
    if 'start_date' in data and 'end_date' in data:
        # === SỬA ĐỔI Ở ĐÂY ===
        start_date_str = (data.get('start_date') or '').strip()
        end_date_str = (data.get('end_date') or '').strip()
        try:
            item.start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
            item.end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None
        except (ValueError, TypeError):
            # Bỏ qua nếu định dạng ngày không hợp lệ
            pass
            
    db.session.commit()
    db.session.add(Log(action=f"Cập nhật {item_type} ID {item.id}", user_id=current_user.id))
    db.session.commit()
    return jsonify({'success': True, 'message': 'Item updated successfully'})



@bp.route('/delete/<item_type>/<int:item_id>', methods=['POST'])
@login_required
def delete_item(item_type, item_id):
    model_map = {'objective': Objective, 'key_result': KeyResult, 'task': Task}
    Model = model_map.get(item_type)
    if not Model: return jsonify({'success': False, 'message': 'Type not suitable'}), 400
    
    item = Model.query.get_or_404(item_id)
    response_data = {'success': True}
    
    db.session.add(Log(action=f"Xóa {item_type} ID {item.id}: '{item.what if hasattr(item, 'what') else item.content}'", user_id=current_user.id))

    if item_type == 'task':
        kr_id = item.key_result_id
        db.session.delete(item)
        db.session.commit()
        if kr_id:
            kr = recalculate_kr_progress(kr_id)
            if kr:
                response_data.update({
                    'kr_id': kr.id, 'objective_id': kr.objective_id,
                    'kr_progress': kr.progress, 'obj_progress': kr.objective.progress,
                    'kr_current': kr.current, 'kr_target': kr.target
                })
    elif item_type == 'key_result':
        obj = item.objective
        db.session.delete(item)
        db.session.commit()
        response_data.update({'objective_id': obj.id, 'obj_progress': obj.progress})
    else:
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
    query = request.args.get('q', '').strip()
    if not query:
        return render_template('search_results.html', query=query, tasks=[], objectives=[], key_results=[])

    search_term = f"%{query}%"
    tasks = Task.query.filter(or_(Task.what.ilike(search_term), Task.note.ilike(search_term))).all()
    objectives = Objective.query.filter(Objective.content.ilike(search_term)).options(joinedload(Objective.project)).all()
    key_results = KeyResult.query.filter(KeyResult.content.ilike(search_term)).options(joinedload(KeyResult.objective)).all()

    return render_template('search_results.html', page_name='search', query=query, tasks=tasks, objectives=objectives, key_results=key_results)
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


@bp.route('/projects')
@login_required
def project_workspace():
    selected_project_id = request.args.get('project_id', type=int)
    active_tab = request.args.get('tab', 'info')

    # Dữ liệu Cột Trái
    status_filter = request.args.get('status', 'all')
    status_choices = ['Planned', 'Active', 'On Hold', 'Done']
    base_query = Project.query
    if status_filter != 'all' and status_filter in status_choices:
        base_query = base_query.filter(Project.status == status_filter)
    all_projects_list = base_query.order_by(Project.name).all()

    # Dữ liệu Cột Phải
    selected_project_data = None
    objectives_for_display = []
    if selected_project_id:
        selected_project = Project.query.options(
            subqueryload(Project.builds).subqueryload(Build.objectives).subqueryload(Objective.key_results).subqueryload(KeyResult.tasks).joinedload(Task.assignee),
            subqueryload(Project.objectives).subqueryload(Objective.key_results).subqueryload(KeyResult.tasks).joinedload(Task.assignee)
        ).get(selected_project_id)

        if selected_project:
            objectives_list = sorted(selected_project.objectives, key=lambda o: o.position if o.position is not None else float('inf'))

            all_tasks = [task for o in objectives_list for kr in o.key_results for task in kr.tasks]
            task_count = len(all_tasks)
            open_tasks_count = sum(1 for task in all_tasks if task.status != 'Done')
            
            progress_list = [o.progress for o in objectives_list if o.progress is not None]
            avg_progress = sum(progress_list) / len(progress_list) if progress_list else 0
            
            days_remaining = (selected_project.end_date - date.today()).days if selected_project.end_date else None

            # --- LẤY NHẬT KÝ HOẠT ĐỘNG LIÊN QUAN ĐẾN DỰ ÁN ---
            project_logs = []
            try:
                objective_ids = {o.id for o in objectives_list}
                key_result_ids = {kr.id for o in objectives_list for kr in o.key_results}
                task_ids = {t.id for t in all_tasks}

                search_terms = []
                if objective_ids:
                    search_terms.extend([f"Objective ID {id}" for id in objective_ids])
                if key_result_ids:
                    search_terms.extend([f"Added KR to Objective ID {id}" for id in objective_ids])
                    search_terms.extend([f"key_result ID {id}" for id in key_result_ids])
                if task_ids:
                    search_terms.extend([f"task ID {id}" for id in task_ids])
                    search_terms.extend([f"CV ID {id}" for id in task_ids])

                if search_terms:
                    conditions = [Log.action.ilike(f"%{term}%") for term in search_terms]
                    project_logs = Log.query.filter(or_(*conditions)).order_by(Log.timestamp.desc()).limit(10).all()
            except Exception as e:
                current_app.logger.error(f"Error fetching project logs for project {selected_project_id}: {e}")
                project_logs = []
            
            # Đóng gói dữ liệu để gửi sang template
            selected_project_data = {
                'project': selected_project,
                'stats': {
                    'o': len(objectives_list), 
                    'kr': sum(len(o.key_results) for o in objectives_list), 
                    'task': task_count, 
                    'progress': avg_progress,
                    'open_tasks': open_tasks_count 
                },
                'days_remaining': days_remaining,
                # === SỬA LỖI: Truyền dữ liệu log thực sự sang template ===
                'logs': project_logs 
            }
            objectives_for_display = objectives_list

    all_users = User.query.all()
    all_builds_for_modal = Build.query.all()
    
    return render_template('project_workspace.html',
                           page_name='projects',
                           all_projects=all_projects_list,
                           selected_project_data=selected_project_data,
                           selected_project_id=selected_project_id,
                           objectives=objectives_for_display,
                           active_tab=active_tab,
                           status_choices=status_choices, 
                           current_status=status_filter,
                           users=all_users,
                           projects=Project.query.order_by(Project.name).all(),
                           builds=all_builds_for_modal,
                           today_date_str=date.today().strftime('%Y-%m-%d')
                           )


@bp.route('/update-project/<int:project_id>', methods=['POST'])
@login_required
def update_project_details(project_id):
    project = Project.query.get_or_404(project_id)
    
    project.name = request.form.get('name')
    project.description = request.form.get('description')
    project.status = request.form.get('status')
    start_date_str = request.form.get('start_date')
    end_date_str = request.form.get('end_date')
    project.start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
    project.end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None
    db.session.commit()
    
    flash(f'Project "{project.name}" updated successfully!', 'success')
    # SỬA LỖI: Điều hướng về workspace và chọn đúng project vừa sửa
    return redirect(url_for('main.project_workspace', project_id=project_id))

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
    # SỬA LỖI: Điều hướng về trang workspace chính
    return redirect(url_for('main.project_workspace'))

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
        return redirect(request.referrer or url_for('main.project_workspace'))

    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None
    
    new_build = Build(
        name=name, 
        project_id=project_id,
        start_date=start_date,
        end_date=end_date,
        schedule_link=schedule_link
    )
    db.session.add(new_build)
    db.session.commit()
    flash('New build created!', 'success')
    return redirect(url_for('main.project_workspace', project_id=project_id, tab='info'))

@bp.route('/update-build/<int:build_id>', methods=['POST'])
@login_required
def update_build_details(build_id):
    build = Build.query.get_or_404(build_id)
    build.name = request.form.get('name')
    start_date_str = request.form.get('start_date')
    end_date_str = request.form.get('end_date')
    build.start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
    build.end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None
    build.project_id = request.form.get('project_id')

    # === ADD THIS LINE ===
    build.schedule_link = request.form.get('schedule_link') # Thêm dòng này để lưu link
    # =====================

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

# app/routes.py

@bp.route('/update-task-status', methods=['POST'])
@login_required
def update_task_status():
    data = request.json
    try:
        task_id = data.get('taskId')
        new_status = data.get('newStatus')
        
        if not task_id or not new_status:
            return jsonify({'success': False, 'message': 'Miss infor taskId or newStatus'}), 400

        task = Task.query.get(task_id)
        if not task:
            return jsonify({'success': False, 'message': 'Cannot find job'}), 404
        
        old_status = task.status
        task.status = new_status
        
        log_action = f"changed status '{task.what}' từ {old_status} sang {new_status}."
        db.session.add(Log(action=log_action, user_id=current_user.id))
        
        db.session.commit()
        
        # CHANGE: Trả về đối tượng task đã được cập nhật
        # Điều này rất quan trọng để frontend có thể cập nhật "live"
        return jsonify({
            'success': True, 
            'message': 'Status update success!',
            'task': task.to_dict() 
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
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


@bp.route('/notes')
@login_required
def notes():
    all_columns = Column.query.order_by(Column.position).all()
    if not all_columns:
        default_titles = ['Idea', 'IP', 'Document','Seminar']
        for i, title in enumerate(default_titles):
            db.session.add(Column(name=title, position=i))
        db.session.commit()
        all_columns = Column.query.order_by(Column.position).all()

    notes_by_column_id = defaultdict(list)
    for note in Note.query.all():
        notes_by_column_id[note.column_id].append(note)

    return render_template('notes.html', all_columns=all_columns, notes_by_column_id=notes_by_column_id, page_name='notes')

@bp.route('/api/notes', methods=['POST'])
@login_required
def create_note():
    data = request.form
    title = data.get('title')
    column_id = data.get('column_id')

    if not title or not column_id:
        return jsonify({'success': False, 'message': 'Title and column must be fill'}), 400

    allowed_tags = list(bleach.ALLOWED_TAGS) + ['div', 'p', 'br', 'strong', 'em', 'u', 'ol', 'ul', 'li', 'img', 'a', 'span']
    allowed_attrs = {**bleach.ALLOWED_ATTRIBUTES, 'img': ['src', 'alt', 'style'], 'a': ['href', 'title'], 'span': ['style']}
    css_sanitizer = CSSSanitizer(allowed_css_properties=['color', 'background-color', 'text-align'])

    content = bleach.clean(
        data.get('content', ''), 
        tags=allowed_tags, 
        attributes=allowed_attrs,
        css_sanitizer=css_sanitizer
    )
    
    try:
        note = Note(title=title, content=content, column_id=int(column_id))
        note.creator_id = current_user.id
        
        db.session.add(note)
        db.session.flush()

        files = request.files.getlist('attachments[]')
        for file in files:
            if file and file.filename != '':
                original_filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                saved_filename = f"{timestamp}_{original_filename}"
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
                    note_id=note.id
                )
                db.session.add(new_file)

        db.session.commit()
        db.session.refresh(note)
        return jsonify({'success': True, 'message': 'Create note sucess!'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating note: {e}")
        return jsonify({'success': False, 'message': f'Error happend: {str(e)}'}), 500

@bp.route('/api/notes/<int:note_id>', methods=['PUT', 'POST'])
@login_required
def update_note(note_id):
    note = Note.query.get_or_404(note_id)

    try:
        if request.is_json:
            data = request.get_json()
            if 'column_id' in data:
                note.column_id = data['column_id']
        else:
            data = request.form
            
            allowed_tags = list(bleach.ALLOWED_TAGS) + ['div', 'p', 'br', 'strong', 'em', 'u', 'ol', 'ul', 'li', 'img', 'a', 'span']
            allowed_attrs = {**bleach.ALLOWED_ATTRIBUTES, 'img': ['src', 'alt', 'style'], 'a': ['href', 'title']}
            
            if 'title' in data:
                note.title = data['title']
            if 'content' in data:
                note.content = bleach.clean(data['content'], tags=allowed_tags, attributes=allowed_attrs)
            if 'column_id' in data:
                 note.column_id = data['column_id']

            files = request.files.getlist('attachments[]')
            for file in files:
                if file and file.filename != '':
                    original_filename = secure_filename(file.filename)
                    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                    saved_filename = f"{timestamp}_{original_filename}"
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
                        note_id=note.id
                    )
                    db.session.add(new_file)

        db.session.commit()
        db.session.refresh(note)
        return jsonify({'success': True, 'message': 'Updated note!'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating note {note_id}: {e}")
        return jsonify({'success': False, 'message': f'Error happend: {str(e)}'}), 500

@bp.route('/api/notes/<int:note_id>', methods=['GET'])
@login_required
def get_note(note_id):
    note = Note.query.options(joinedload(Note.attachments)).get_or_404(note_id)
    return jsonify({'success': True, 'note': note.to_dict()})

@bp.route('/api/notes/<int:note_id>', methods=['DELETE'])
@login_required
def delete_note(note_id):
    note = Note.query.get_or_404(note_id)
    db.session.delete(note)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Deleted note'})

@bp.route('/api/columns', methods=['POST'])
@login_required
def create_column():
    data = request.json
    if not data or not data.get('name'):
        return jsonify({'success': False, 'message': 'Column name must be not empty'}), 400
    max_pos = db.session.query(db.func.max(Column.position)).scalar() or -1
    new_column = Column(name=data['name'], position=max_pos + 1)
    db.session.add(new_column)
    db.session.commit()
    return jsonify({'success': True, 'column': {'id': new_column.id, 'name': new_column.name, 'position': new_column.position}})

@bp.route('/api/columns/<int:column_id>', methods=['DELETE'])
@login_required
def delete_column(column_id):
    column = Column.query.get_or_404(column_id)
    db.session.delete(column)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Column deleted'})

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
        column = Column.query.get(col_id)
        if column:
            column.position = index
    db.session.commit()
    return jsonify({'success': True, 'message': 'Arranged column'})

@bp.route('/api/upload-image', methods=['POST'])
@login_required
def upload_image_api():
    if 'file' in request.files:
        file = request.files['file']
        if file.filename != '':
            original_filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            saved_filename = f"{timestamp}_{original_filename}"
            file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], saved_filename))
            return jsonify({'location': url_for('main.uploaded_file', filename=saved_filename)})
    return jsonify({'error': 'Upload failed'}), 400

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
@bp.route('/api/practice-log/calendar-view')
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

        rows = (PracticeLog.query
                .filter(PracticeLog.user_id == current_user.id,
                        PracticeLog.log_ts >= start_utc,
                        PracticeLog.log_ts <  end_utc)
                .with_entities(PracticeLog.log_ts)
                .all())

        counts = {}
        for (ts,) in rows:
            d_key = to_vn_time(ts).date().strftime('%Y-%m-%d')
            counts[d_key] = counts.get(d_key, 0) + 1

        logged_dates = sorted(counts.keys())
        return jsonify({'success': True, 'logged_dates': logged_dates, 'counts_by_date': counts})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@bp.route('/api/practice-log/recent-logs')
@login_required
def get_recent_logs():
    """API để lấy 15 ghi nhận mới nhất dưới dạng JSON."""
    recent_logs = PracticeLog.query.filter_by(user_id=current_user.id)        .order_by(PracticeLog.log_ts.desc()).limit(15).all()

    logs_list = []
    for log in recent_logs:
        log_dict = log.to_dict()
        vn_time = to_vn_time(log.log_ts)
        log_dict['log_ts_vn'] = vn_time.isoformat()
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
# routes.py

# TÌM HÀM NÀY VÀ THAY THẾ BẰNG CODE BÊN DƯỚI
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
        'status': project.status
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
        'schedule_link': build.schedule_link or ''
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
# Route cũ để điều hướng
@bp.route('/gantt')
def gantt_redirect():
    project_id = request.args.get('project_id')
    if project_id:
        return redirect(url_for('main.timeline_page', project_id=project_id))
    return redirect(url_for('main.timeline_page'))
@bp.route('/api/objective/<int:obj_id>')
@login_required
def api_get_objective(obj_id):
    obj = Objective.query.get_or_404(obj_id)
    return jsonify({
        'success': True,
        'objective': {
            'id': obj.id,
            'content': obj.content,
            'owner_id': obj.owner_id,
            'project_id': obj.project_id,
            'build_id': obj.build_id,
            'start_date': obj.start_date.isoformat() if obj.start_date else '',
            'end_date': obj.end_date.isoformat() if obj.end_date else ''
        }
    })
# THÊM MỚI: API để lấy chi tiết một Key Result
@bp.route('/api/key-result/<int:kr_id>')
@login_required
def api_get_key_result(kr_id):
    kr = KeyResult.query.get_or_404(kr_id)
    return jsonify({
        'success': True,
        'key_result': {
            'id': kr.id,
            'content': kr.content,
            'start_date': kr.start_date.isoformat() if kr.start_date else '',
            'end_date': kr.end_date.isoformat() if kr.end_date else ''
        }
    })
# THÊM HÀM MỚI NÀY VÀO CUỐI FILE app/routes.py

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
# Thêm vào cuối file app/routes.py

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