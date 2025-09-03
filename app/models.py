from datetime import datetime, date, timedelta
from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from flask import url_for
import json


# ==============================================================================
# USER AUTHENTICATION
# ==============================================================================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)

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

# ==============================================================================
# CALENDAR MODELS (Task, Log)
# ==============================================================================

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task_date = db.Column(db.Date, nullable=True, index=True)
    hour = db.Column(db.Integer, nullable=True)
    what = db.Column(db.String(255), nullable=False)
    who_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    status = db.Column(db.String(50), default='Pending')
    note = db.Column(db.Text)
    report = db.Column(db.Text)
    recurrence = db.Column(db.String(20), default='none')
    recurrence_end_date = db.Column(db.Date)
    priority = db.Column(db.String(20), default='Medium') # Thêm cột priority
    
    attachments = db.relationship('UploadedFile', backref='task', cascade="all, delete-orphan")
    key_result_id = db.Column(db.Integer, db.ForeignKey('key_result.id'), nullable=True)

    def to_dict(self):
        data = {
            'id': self.id,
            'date': self.task_date.strftime('%Y-%m-%d') if self.task_date else None,
            'hour': self.hour,
            'what': self.what,
            'who': self.assignee.username if self.assignee else '',
            'who_id': self.who_id,
            'status': self.status,
            'note': self.note,
            'report': self.report,
            'recurrence': self.recurrence,
            'recurrence_end_date': self.recurrence_end_date.strftime('%Y-%m-%d') if self.recurrence_end_date else None,
            'attachments': [att.to_dict() for att in self.attachments],
            'key_result_id': self.key_result_id,
            'priority': self.priority
        }
        return json.loads(json.dumps(data, ensure_ascii=False))

class Log(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(500), nullable=False)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User', back_populates='logs')

    def __repr__(self):
        return f'<Log {self.action}>'

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
    objectives = db.relationship('Objective', backref='project', cascade="all, delete-orphan")
    builds = db.relationship('Build', backref='project', lazy=True, cascade="all, delete-orphan")
    

class Build(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    schedule_link = db.Column(db.String(500), nullable=True) 
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    
    # SỬA LỖI: Bỏ lazy='dynamic' để cho phép tính toán tiến độ hiệu quả
    objectives = db.relationship('Objective', backref='build', cascade="all, delete-orphan")

    @property
    def progress(self):
        """Calculate the average progress of all objectives in this build."""
        # Bây giờ self.objectives là một list (nếu được tải trước)
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
    # SỬA LỖI: Bỏ lazy='dynamic' để cho phép tải trước dữ liệu
    key_results = db.relationship('KeyResult', backref='objective', cascade="all, delete-orphan", order_by='KeyResult.id')


    @property
    def progress(self):
        krs = self.key_results
        # Vì đã bỏ lazy='dynamic', krs giờ là một list
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
    tasks = db.relationship('Task', backref='key_result', cascade="all, delete-orphan")

    @property
    def progress(self):
        if self.target == 0: return 0
        return min(100, (self.current / self.target) * 100)

# ==============================================================================
# UPLOADS MANAGER
# ==============================================================================
# (Giữ nguyên không thay đổi)
class UploadedFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    original_filename = db.Column(db.String(255), nullable=False)
    saved_filename = db.Column(db.String(255), nullable=False, unique=True)
    file_type = db.Column(db.String(20))
    file_size = db.Column(db.Integer)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    uploader_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=True)
    note_id = db.Column(db.Integer, db.ForeignKey('note.id'), nullable=True)
    upload_source = db.Column(db.String(50), default='attachment')
    
    
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
            return {'text': 'Tải lên trực tiếp', 'url': None}
        
        if self.task_id and self.task:
            task_date = self.task.task_date.strftime('%Y-%m-%d')
            return {
                'text': 'Công việc',
                'url': url_for('main.index', view_mode='day', date_str=task_date)
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

# ==============================================================================
# NOTE & COLUMN MODELS
# ==============================================================================
# (Giữ nguyên không thay đổi)
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

    def __repr__(self):
        return f'<Note {self.title}>'

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'column_title': self.column.name if self.column else '',
            'column_id': self.column_id,
            'timestamp': self.timestamp.strftime('%H:%M %d/%m/%Y'),
            'attachments': [att.to_dict() for att in self.attachments]
        }

# ==============================================================================
# PRACTICE LOG MODELS
# ==============================================================================
# (Giữ nguyên không thay đổi)
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

class HabitLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    habit_name = db.Column(db.String(100), nullable=False)
    log_ts = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
