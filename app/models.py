import re # <--- THÊM IMPORT NÀY
from datetime import datetime, date, timedelta
from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from flask import url_for
import json
from sqlalchemy import UniqueConstraint

# ==============================================================================
# USER AUTHENTICATION
# ==============================================================================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    annual_leave_quota = db.Column(db.Float, default=12.0)
    leave_used_correction = db.Column(db.Float, default=0.0)

    is_admin = db.Column(db.Boolean, default=False)
    
    tasks = db.relationship('Task', backref='assignee')
    objectives = db.relationship('Objective', backref='owner')
    uploaded_files = db.relationship('UploadedFile', backref='uploader')
    logs = db.relationship('Log', back_populates='user')
    notes = db.relationship('Note', back_populates='creator', lazy='dynamic', cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username
        }

    def get_leave_stats(self, year=None):
        # Import local để tránh lỗi nếu class Attendance định nghĩa sau User
        from app.models import Attendance
        
        # Nếu không truyền năm, lấy năm hiện tại
        try:
            target_year = int(year) if year else datetime.now().year
        except (ValueError, TypeError):
            target_year = datetime.now().year
        
        # Đếm từ dữ liệu chấm công thật trong năm được chọn
        leaves = Attendance.query.filter(
            Attendance.user_id == self.id,
            Attendance.status == 'Leave',
            db.extract('year', Attendance.date) == target_year
        ).all()
        
        system_used = 0
        for l in leaves:
            # Kiểm tra cột shift_type để tính 0.5 hoặc 1.0
            if hasattr(l, 'shift_type') and l.shift_type in ['Morning_Half', 'Afternoon_Half']:
                system_used += 0.5
            else:
                system_used += 1.0
        
        # Cộng thêm phần Admin sửa tay (correction)
        correction = self.leave_used_correction if hasattr(self, 'leave_used_correction') and self.leave_used_correction else 0.0
        final_used = system_used + correction
        
        return {
            'quota': self.annual_leave_quota,
            'system_used': system_used,
            'correction': correction,
            'used': final_used,
            'remaining': self.annual_leave_quota - final_used,
            'year': target_year
        }

# Tìm và thay thế class DailyReportData trong models.py bằng bản này:

class DailyReportData(db.Model):
    """Bảng dữ liệu báo cáo hàng ngày - Bổ sung Evidence & Links"""
    __tablename__ = 'daily_report_data'
    
    id = db.Column(db.Integer, primary_key=True)
    report_date = db.Column(db.Date, nullable=False, index=True)
    created_at = db.Column(db.Date, nullable=False, default=date.today)
    
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    process = db.Column(db.String(100), nullable=False, default="N/A")    
    build_name = db.Column(db.String(100), nullable=True)  
    
    yield_info = db.Column(db.Text, nullable=True, default="")
    issue = db.Column(db.Text, nullable=True, default="")
    fa = db.Column(db.Text, nullable=True, default="")
    action = db.Column(db.Text, nullable=True, default="")
    result = db.Column(db.Text, nullable=True, default="")
    pic = db.Column(db.String(100), nullable=True, default="") # Nếu bạn có cột PIC
    report_link = db.Column(db.String(500), nullable=True, default="")
    
    
    is_resolved = db.Column(db.Boolean, default=False, server_default='0')
    has_data = db.Column(db.Boolean, default=False, server_default='0')
    tasks = db.relationship('Task', backref='related_issue', lazy=True)
    project = db.relationship('Project', backref=db.backref('daily_reports', cascade="all, delete-orphan"))
    # [MỚI] Relationship để lấy nhanh file đính kèm
    attachments = db.relationship('UploadedFile', backref='daily_report', lazy=True, cascade="all, delete-orphan")
    tasks = db.relationship(
        'Task', 
        backref='related_issue', 
        lazy=True, 
        cascade="all, delete-orphan",
        overlaps="related_issue,related_tasks,issue_source"
    )
    def to_dict(self):
        # Tính toán tiến độ từ các task liên quan
        total_tasks = len(self.tasks)
        done_tasks = sum(1 for t in self.tasks if t.status == 'Done')
        progress = int((done_tasks / total_tasks * 100)) if total_tasks > 0 else 0

        return {
            'id': self.id,
            'project_id': self.project_id,
            'is_resolved': self.is_resolved,
            'build_name': self.build_name or '',
            'issue': self.issue or '',
            'fa': self.fa or '',
            'action': self.action or '',
            'result': self.result or '',
            'report_link': self.report_link or '',
            'report_date': self.report_date.strftime('%Y-%m-%d'),
            'is_carry_over': self.created_at < self.report_date,
            'attachments': [att.to_dict() for att in self.attachments],
            # [MỚI] Thông tin Task để hiển thị ở Bảng 1
            'task_info': {
                'has_task': total_tasks > 0,
                'progress': progress,
                'status_text': f"{done_tasks}/{total_tasks} Tasks",
                'linked_task_ids': [t.id for t in self.tasks]
            }
        }
# ==============================================================================
# CALENDAR MODELS (Task, Log)
# ==============================================================================
# Trong models.py

class TaskComment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    # Ai nói?
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    # Nói ở việc nào?
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False)
    
    # Quan hệ để truy xuất ngược
    user = db.relationship('User', backref='task_comments')
    task = db.relationship('Task', backref=db.backref('comments', cascade='all, delete-orphan'))

    def to_dict(self):
        return {
            'id': self.id,
            'content': self.content,
            'user_name': self.user.username if self.user else 'Unknown',
            'user_id': self.user_id,
            'timestamp': self.timestamp.isoformat(),
            # Thêm cái này để frontend biết là ngày giờ nào cho dễ đọc
            'time_display': (self.timestamp + timedelta(hours=7)).strftime('%d/%m %H:%M') 
        }
        
# Trong models.py

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    
    # [MỚI] Ngày bắt đầu (để vẽ Timeline)
    start_date = db.Column(db.Date, nullable=True) 
    
    # [GIỮ NGUYÊN] Đây đóng vai trò là End Date (Hạn chót/Deadline)
    task_date = db.Column(db.Date, nullable=True, index=True) 
    
    
    hour = db.Column(db.String(10), nullable=True)
    what = db.Column(db.String(255), nullable=False)
    who_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    status = db.Column(db.String(50), default='Pending')
    note = db.Column(db.Text)
    report = db.Column(db.Text)
    recurrence = db.Column(db.String(20), default='none')
    recurrence_end_date = db.Column(db.Date)
    priority = db.Column(db.String(20), default='Medium')
    report_link = db.Column(db.String(500), nullable=True)
    # Quan hệ
    sub_tasks = db.relationship('SubTask', backref='task', lazy=True, cascade="all, delete-orphan", order_by='SubTask.position')
    daily_report_item_id = db.Column(db.Integer, db.ForeignKey('daily_report_data.id'), nullable=True)
    origin_note_id = db.Column(db.Integer, db.ForeignKey('note.id'), nullable=True)
    
    attachments = db.relationship('UploadedFile', backref='task', cascade="all, delete-orphan")
    key_result_id = db.Column(db.Integer, db.ForeignKey('key_result.id'), nullable=True)
    
    issue_source = db.relationship(
        'DailyReportData', 
        backref=db.backref('related_tasks', lazy='dynamic', overlaps="related_issue,related_tasks,tasks"),
        overlaps="related_issue,related_tasks,tasks"
    )

    def to_dict(self):
        return {
            'id': self.id,
            # [THÊM MỚI] Gửi ngày bắt đầu về cho Frontend
            'start_date': self.start_date.strftime('%Y-%m-%d') if self.start_date else None,
            
            'task_date': self.task_date.strftime('%Y-%m-%d') if self.task_date else None,
            'hour': self.hour,
            'what': self.what,
            'who': self.assignee.username if self.assignee else '',
            'who_id': self.who_id,
            'status': self.status,
            'note': self.note,
            'report': self.report,
            'recurrence': self.recurrence,
            'recurrence_end_date': self.recurrence_end_date.strftime('%Y-%m-%d') if self.recurrence_end_date else None,
            'daily_report_item_id': self.daily_report_item_id,
            'attachments': [att.to_dict() for att in self.attachments],
            'key_result_id': self.key_result_id,
            'priority': self.priority,
            'comments': [c.to_dict() for c in sorted(self.comments, key=lambda x: x.timestamp)] if hasattr(self, 'comments') else [],
            'sub_tasks': [st.to_dict() for st in self.sub_tasks] 
        }

class Log(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(500), nullable=False)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User', back_populates='logs')

    def __repr__(self):
        return f'<Log {self.action}>'

    # --- THÊM PROPERTY NÀY ĐỂ TRÍCH XUẤT ID TASK ---
    @property
    def related_task_id(self):
        """Trích xuất ID task từ chuỗi action nếu có (VD: 'Updated task ID 123...')"""
        match = re.search(r'ID\s+(\d+)', self.action)
        if match:
            return int(match.group(1))
        return None

# === MODEL MỚI CHO SUBTASK (CHECKLIST ITEM) ===
class SubTask(db.Model):
    __tablename__ = 'sub_task' # Thêm dòng này để chắc chắn tên bảng là 'sub_task'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(300), nullable=False)
    is_done = db.Column(db.Boolean, default=False, nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id', ondelete='CASCADE'), nullable=False)
    position = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {
            'id': self.id,
            'content': self.content,
            'is_done': self.is_done
        }

# ==============================================================================
# OKR & KAIZEN MODELS
# ==============================================================================
class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, unique=True)
    description = db.Column(db.Text)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='Active', server_default='Active')
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    note = db.Column(db.Text, nullable=True)
    owner = db.relationship('User', backref='projects_owned')
    objectives = db.relationship('Objective', backref='project', cascade="all, delete-orphan")
    builds = db.relationship('Build', backref='project', lazy=True, cascade="all, delete-orphan", order_by="Build.position")
    position = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    plan_link = db.Column(db.String(500), nullable=True)

    @property
    def progress(self):
        all_builds = self.builds
        if not all_builds:
            unassigned_objectives = [o for o in self.objectives if not o.build_id]
            if not unassigned_objectives:
                return 0
            progress_values = [obj.progress for obj in unassigned_objectives if obj.progress is not None]
        else:
            progress_values = [b.progress for b in all_builds if b.progress is not None]

        if not progress_values:
            return 0
        
        return sum(progress_values) / len(progress_values)

class ProductionData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    process = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Integer, nullable=True)
    quantity_yield = db.Column(db.Integer, nullable=True, default=0)
    result = db.Column(db.String(100), nullable=False)
    yrt = db.Column(db.Float, nullable=True)
    yield_rate = db.Column(db.Float, nullable=True)
    reason = db.Column(db.Text, nullable=True)
    action = db.Column(db.Text, nullable=True)
    status = db.Column(db.Text, nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False, index=True)
    build_name = db.Column(db.String(100), nullable=False, index=True)
    project = db.relationship('Project', backref=db.backref('production_data', cascade="all, delete-orphan"))

    def __repr__(self):
        return f'<ProductionData Build:{self.build_name} - Result:{self.result}>' 

class Build(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id',use_alter=True), nullable=True)
    schedule_link = db.Column(db.String(500), nullable=True) 
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    note = db.Column(db.Text, nullable=True)
    owner = db.relationship('User', backref='builds_owned')
    report_link = db.Column(db.String(500), nullable=True)
    objectives = db.relationship('Objective', backref='build', cascade="all, delete-orphan")
    position = db.Column(db.Integer, default=0, nullable=False, server_default='0')
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'project_id': self.project_id,
            'owner_id': self.owner_id,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'note': self.note,
            'schedule_link': self.schedule_link,
            'report_link': self.report_link,
            'progress': self.progress,
            'owner_username': self.owner.username if self.owner else ''
        }
    @property
    def progress(self):
        objectives_list = self.objectives
        if not objectives_list:
            return 0
        
        progress_values = [obj.progress for obj in objectives_list if obj.progress is not None]
        if not progress_values:
            return 0
            
        total_progress = sum(progress_values)
        return round(total_progress / len(progress_values))

    def __repr__(self):
        return f'<Build {self.name}>'

class Objective(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(500), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True)
    color = db.Column(db.String(20))
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'))
    build_id = db.Column(db.Integer, db.ForeignKey('build.id'))
    position = db.Column(db.Integer, default=0, nullable=False)
    note = db.Column(db.Text, nullable=True)
    key_results = db.relationship('KeyResult', backref='objective', cascade="all, delete-orphan", order_by='KeyResult.id')

    # <<< THÊM PHƯƠNG THỨC NÀY VÀO ĐÂY >>>
    def to_dict(self):
        return {
            'id': self.id,
            'content': self.content,
            'project_id': self.project_id,
            'build_id': self.build_id,
            'owner_id': self.owner_id,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'progress': self.progress,
            'note': self.note
        }

    @property
    def progress(self):
        krs = self.key_results
        if not krs: return 0
        return sum(kr.progress for kr in krs) / len(krs)

class KeyResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(500), nullable=False)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    current = db.Column(db.Float, default=0)
    target = db.Column(db.Float, default=1)
    objective_id = db.Column(db.Integer, db.ForeignKey('objective.id'), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    note = db.Column(db.Text, nullable=True)
    owner = db.relationship('User', backref='key_results')
    tasks = db.relationship('Task', backref='key_result', cascade="all, delete-orphan")
    def to_dict_for_obj_detail(self):
        """Returns a dictionary representation for the Objective Detail Modal."""
        return {
            'id': self.id,
            'content': self.content,
            'progress': self.progress,
            'current': self.current,
            'target': self.target,
            'tasks': [
                {
                    'id': task.id,
                    'what': task.what,
                    'status': task.status,
                    'assignee': task.assignee.to_dict() if task.assignee else None
                } for task in sorted(self.tasks, key=lambda t: t.id)
            ]
        }
    @property
    def progress(self):
        if self.target == 0: return 0
        return min(100, (self.current / self.target) * 100)

class UploadedFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    original_filename = db.Column(db.String(255), nullable=False)
    saved_filename = db.Column(db.String(255), nullable=False, unique=True)
    file_type = db.Column(db.String(20))
    file_size = db.Column(db.Integer)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    uploader_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=True)
    note_id = db.Column(db.Integer, db.ForeignKey('note.id'), nullable=True)
    upload_source = db.Column(db.String(50), default='attachment')
    project = db.relationship('Project', backref=db.backref('attachments', lazy='dynamic'))
    daily_report_id = db.Column(db.Integer, db.ForeignKey('daily_report_data.id'), nullable=True)
    def to_dict(self):
        return {
            'id': self.id,
            'original_filename': self.original_filename,
            'url': url_for('main.uploaded_file', filename=self.saved_filename),
            'delete_url': url_for('main.delete_uploaded_file', file_id=self.id)
        }

    @property
    def upload_date_local(self):
        if not self.upload_date:
            return None
        return self.upload_date + timedelta(hours=7)
    def context(self):
        if self.upload_source == 'direct':
            if self.project_id and self.project:
                return {
                    'text': 'Project File',
                    'url': url_for('main.project_workspace', project_id=self.project_id)
                }
            return {'text': 'Tải lên trực tiếp', 'url': None}
        
        if self.task_id and self.task:
            task_date_str = self.task.task_date.strftime('%Y-%m-%d') if self.task.task_date else date.today().strftime('%Y-%m-%d')
            return {
                'text': 'Công việc',
                'url': url_for('main.index', view_mode='day', date_str=task_date_str)
            }
        if self.note_id and self.note:
            return {
                'text': 'Ghi chú',
                'url': url_for('main.notes')
            }
        
        return {
            'text': 'Đính kèm',
            'url': None
        }

class Column(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    position = db.Column(db.Integer) 
    notes = db.relationship('Note', backref='column', lazy=True, cascade="all, delete-orphan")
    def __repr__(self):
        return f'<Column {self.name}>'

class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    column_id = db.Column(db.Integer, db.ForeignKey('column.id'), nullable=False)
    attachments = db.relationship('UploadedFile', backref='note', cascade="all, delete-orphan")
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    creator = db.relationship('User', back_populates='notes')
    label = db.Column(db.String(20), nullable=True)

    # [MỚI] Relationship để lấy danh sách task con được tạo từ Note này
    generated_tasks = db.relationship('Task', backref='origin_note', lazy='dynamic')

    def __repr__(self):
        return f'<Note {self.title}>'

# Trong models.py -> class Note
    def to_dict(self):
        # TÍNH TOÁN TIẾN ĐỘ TASK
        total_tasks = self.generated_tasks.count()
        done_tasks = self.generated_tasks.filter(Task.status == 'Done').count()
        
        progress_percent = 0
        if total_tasks > 0:
            progress_percent = int((done_tasks / total_tasks) * 100)

        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'column_id': self.column_id,
            'creator': self.creator.to_dict() if self.creator else None,
            'timestamp': self.timestamp.isoformat(),
            'label': self.label,
            'attachments': [att.to_dict() for att in self.attachments],
            
            # [GIỮ NGUYÊN] Dữ liệu thống kê
            'task_progress': {
                'total': total_tasks,
                'done': done_tasks,
                'percent': progress_percent,
                'has_tasks': total_tasks > 0
            },
            # [THÊM MỚI] Danh sách chi tiết task để hiển thị trong Modal
            'linked_tasks': [
                {
                    'id': t.id,
                    'what': t.what,
                    'status': t.status,
                    'who': t.assignee.username if t.assignee else 'N/A'
                } for t in self.generated_tasks.all()
            ]
        }

class PracticeLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    log_ts = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    tag = db.Column(db.String(50), nullable=False, index=True)
    note = db.Column(db.Text)
    situation = db.Column(db.Text, nullable=True) 
    sense_door = db.Column(db.String(50), nullable=True)
    sense_object = db.Column(db.Text, nullable=True)
    feeling = db.Column(db.String(200), nullable=True)
    craving = db.Column(db.String(200), nullable=True)
    contemplation = db.Column(db.Text, nullable=True)
    outcome = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    intensity = db.Column(db.Integer, nullable=True)
    duration_min = db.Column(db.Integer, nullable=True)
    def to_dict(self):
        return {
            'id': self.id,
            'log_ts': self.log_ts.isoformat(),
            'tag': self.tag,
            'note': self.note or '',
            'situation': self.situation or '',
            'sense_door': self.sense_door or '',
            'sense_object': self.sense_object or '',
            'feeling': self.feeling or '',
            'craving': self.craving or '',
            'contemplation': self.contemplation or '',
            'outcome': self.outcome or '',
            'intensity': self.intensity,
            'duration_min': self.duration_min,
        }

# Trong models.py

class Habit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True) # Để ẩn thói quen cũ không muốn track nữa
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Quan hệ với logs
    logs = db.relationship('HabitLog', backref='habit', lazy='dynamic', cascade="all, delete-orphan")

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'is_active': self.is_active
        }

class HabitLog(db.Model): # Cập nhật lại bảng này (hoặc xóa bảng cũ tạo lại)
    id = db.Column(db.Integer, primary_key=True)
    date_logged = db.Column(db.Date, nullable=False) # Chỉ cần ngày, không cần giờ phút
    habit_id = db.Column(db.Integer, db.ForeignKey('habit.id'), nullable=False)
    is_done = db.Column(db.Boolean, default=True)
    
    __table_args__ = (db.UniqueConstraint('habit_id', 'date_logged', name='_habit_date_uc'),)


class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, index=True) # Ngày chấm công
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Thời gian thực tế
    check_in = db.Column(db.DateTime, nullable=True)  
    check_out = db.Column(db.DateTime, nullable=True) 

    # Trạng thái logic
    # Các giá trị: 'Present', 'Late', 'Absent' (Nghỉ ko phép), 'Leave' (Nghỉ có phép)
    status = db.Column(db.String(20), default='Absent') 
    
    # Loại hình (để xử lý nửa ngày/cả ngày)
    # Các giá trị: 'Full', 'Morning_Half', 'Afternoon_Half'
    shift_type = db.Column(db.String(20), default='Full')

    note = db.Column(db.String(255), nullable=True) # Lý do đi muộn/nghỉ

    # Mỗi user chỉ có 1 record cho 1 ngày
    __table_args__ = (UniqueConstraint('user_id', 'date', name='_user_attendance_uc'),)

    @property
    def work_duration(self):
        if self.check_in and self.check_out:
            return (self.check_out - self.check_in).total_seconds() / 3600 # Giờ
        return 0
# --- Mở file models.py và thêm class này vào cuối file ---


class DailyPerformance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, index=True)
    
    # Điểm số
    quantity_score = db.Column(db.Float, default=None)
    quality_score = db.Column(db.Float, default=None)
    attitude_score = db.Column(db.Float, default=None)
    discipline_score = db.Column(db.Float, default=None)
    
    # Comment chi tiết (Mới thêm lại)
    quantity_comment = db.Column(db.String(255))
    quality_comment = db.Column(db.String(255))
    attitude_comment = db.Column(db.String(255))
    discipline_comment = db.Column(db.String(255))
    
    # Cột cũ (để backup, không dùng nữa)
    comment = db.Column(db.Text)
    
    final_score = db.Column(db.Float, default=0.0)

    __table_args__ = (UniqueConstraint('user_id', 'date', name='_user_perf_uc_v2'),)

    def calculate_final(self):
        # Tính trung bình cộng (Chỉ chia cho các cột đã chấm hoặc chia 4 nếu muốn ép buộc)
        # Logic: Coi None là 0 để tính toán
        s1 = self.quantity_score or 0
        s2 = self.quality_score or 0
        s3 = self.attitude_score or 0
        s4 = self.discipline_score or 0
        
        # Nếu muốn công bằng: Chưa chấm thì không tính vào trung bình? 
        # Hay chưa chấm = 0? Excel của bro chia 5, ở đây chia 4 cột.
        # Để tránh "sai sai", ta sẽ chia 4 cứng.
        self.final_score = round((s1 + s2 + s3 + s4) / 4, 2)

# ==============================================================================
# X3 PLAN MODELS (Daily, Weekly, Monthly) - ĐÃ CẬP NHẬT LIÊN KẾT TASK
# ==============================================================================

class DailyPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, index=True)

    # Tiêu điểm
    pain_point = db.Column(db.Text)
    root_cause = db.Column(db.Text)
    daily_objective = db.Column(db.String(500))
    
    # KR (Nội dung hiển thị nhanh)
    kr1 = db.Column(db.String(255))
    kr2 = db.Column(db.String(255))
    kr3 = db.Column(db.String(255))
    
    # Action (Text thuần để hiển thị nhanh nếu cần)
    kr1_action = db.Column(db.Text)
    kr2_action = db.Column(db.Text)
    kr3_action = db.Column(db.Text)
    
    # [MỚI] LIÊN KẾT VỚI TASK THỰC TẾ
    kr1_task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=True)
    kr2_task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=True)
    kr3_task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=True)
    
    # Relationship để truy xuất object Task dễ dàng (nếu cần)
    kr1_task = db.relationship('Task', foreign_keys=[kr1_task_id])
    kr2_task = db.relationship('Task', foreign_keys=[kr2_task_id])
    kr3_task = db.relationship('Task', foreign_keys=[kr3_task_id])
    
    # Kaizen
    kaizen_result = db.Column(db.Text)
    kaizen_cause = db.Column(db.Text)
    kaizen_action = db.Column(db.Text)
    kaizen_lesson = db.Column(db.Text)

    __table_args__ = (db.UniqueConstraint('user_id', 'date', name='_user_daily_plan_uc'),)

class WeeklyPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    week_number = db.Column(db.Integer, nullable=False)
    
    # Tiêu điểm Tuần
    pain_point = db.Column(db.Text)
    root_cause = db.Column(db.Text)
    weekly_objective = db.Column(db.String(500))
    
    # KR & Action (Tuần)
    kr1 = db.Column(db.String(255))
    kr1_action = db.Column(db.Text)
    
    kr2 = db.Column(db.String(255))
    kr2_action = db.Column(db.Text)
    
    kr3 = db.Column(db.String(255))
    kr3_action = db.Column(db.Text)

    # [MỚI] LIÊN KẾT VỚI TASK THỰC TẾ (TUẦN)
    kr1_task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=True)
    kr2_task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=True)
    kr3_task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=True)
    
    # Kaizen Tuần
    kaizen_result = db.Column(db.Text)
    kaizen_cause = db.Column(db.Text)
    kaizen_action = db.Column(db.Text)
    kaizen_lesson = db.Column(db.Text)

    __table_args__ = (db.UniqueConstraint('user_id', 'year', 'week_number', name='_user_weekly_plan_uc'),)

class MonthlyPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)
    
    # Tiêu điểm Tháng
    pain_point = db.Column(db.Text)
    root_cause = db.Column(db.Text)
    monthly_objective = db.Column(db.String(500))
    
    # KR & Action (Tháng)
    kr1 = db.Column(db.String(255))
    kr1_action = db.Column(db.Text)
    
    kr2 = db.Column(db.String(255))
    kr2_action = db.Column(db.Text)
    
    kr3 = db.Column(db.String(255))
    kr3_action = db.Column(db.Text)

    # [MỚI] LIÊN KẾT VỚI TASK THỰC TẾ (THÁNG)
    kr1_task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=True)
    kr2_task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=True)
    kr3_task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=True)
    
    # Kaizen Tháng
    kaizen_result = db.Column(db.Text)
    kaizen_cause = db.Column(db.Text)
    kaizen_action = db.Column(db.Text)
    kaizen_lesson = db.Column(db.Text)

    __table_args__ = (db.UniqueConstraint('user_id', 'year', 'month', name='_user_monthly_plan_uc'),)
# ==============================================================================
# SALARY & TAX MANAGEMENT (MỚI)
# ==============================================================================

class SalaryConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Cấu hình cố định
    base_salary_gross = db.Column(db.Float, default=0.0) # Lương Gross hợp đồng
    insurance_salary = db.Column(db.Float, default=0.0)  # Lương đóng bảo hiểm
    dependents_count = db.Column(db.Integer, default=0)  # Số người phụ thuộc
    region = db.Column(db.Integer, default=1)            # Vùng (1, 2, 3, 4) để tính trần BHTN

    __table_args__ = (db.UniqueConstraint('user_id', name='_user_salary_config_uc'),)
    user = db.relationship('User', backref=db.backref('salary_config', uselist=False))

class MonthlySalary(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)
    
    # Số liệu thực tế
    gross_income = db.Column(db.Float, default=0.0)      # Tổng thu nhập chịu thuế
    insurance_deducted = db.Column(db.Float, default=0.0)# Bảo hiểm đã trừ
    tax_deducted = db.Column(db.Float, default=0.0)      # Thuế TNCN đã trừ tại nguồn
    net_income = db.Column(db.Float, default=0.0)        # Thực lĩnh (Gross - BH - Thuế)
    
    other_deductions = db.Column(db.Float, default=0.0)  # Giảm trừ khác (từ thiện...)
    note = db.Column(db.Text)

    __table_args__ = (db.UniqueConstraint('user_id', 'year', 'month', name='_user_monthly_salary_uc'),)

# Tìm class LineStatus ở cuối file models.py và thay thế bằng code này:

class LineStatus(db.Model):
    __tablename__ = 'line_status'
    id = db.Column(db.Integer, primary_key=True)
    report_date = db.Column(db.Date, nullable=False, default=date.today, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False, index=True)
    
    # Định danh (Đã thay line_name thành build_name)
    build_name = db.Column(db.String(100), nullable=False)
    process = db.Column(db.String(100), nullable=False)
    
    # Thông số đo lường (Drivers)
    inline = db.Column(db.Integer, default=1)
    gib = db.Column(db.Integer, default=0)
    takt_time = db.Column(db.Float, default=0.0)
    efficiency = db.Column(db.Float, default=100.0)
    
    # Năng lực (Capacity)
    ch = db.Column(db.Float, default=0.0)
    ch_available = db.Column(db.Float, default=0.0)
    capa = db.Column(db.Float, default=0.0)
    
    # Quản lý rủi ro & Lịch sử
    issue = db.Column(db.Text, nullable=True)
    reason = db.Column(db.Text, nullable=True)
    action = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(50), default='Running') # Running, Warning, Down
    link = db.Column(db.String(500), nullable=True)

    project = db.relationship('Project', backref=db.backref('line_statuses', lazy='dynamic', cascade="all, delete-orphan"))

    def to_dict(self):
        return {
            'id': self.id,
            'report_date': self.report_date.strftime('%Y-%m-%d'),
            'build_name': self.build_name,
            'process': self.process,
            'inline': self.inline,
            'gib': self.gib,
            'takt_time': self.takt_time,
            'efficiency': self.efficiency,
            'ch': self.ch,
            'ch_available': self.ch_available,
            'capa': self.capa,
            'issue': self.issue or '',
            'reason': self.reason or '',
            'action': self.action or '',
            'status': self.status or 'Running',
            'link': self.link or ''
        }