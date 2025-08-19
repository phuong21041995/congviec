from datetime import datetime, date, timedelta
from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from flask import url_for


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
    action_items = db.relationship('ActionItem', backref='assignee')
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
    task_date = db.Column(db.Date, nullable=False, index=True)
    hour = db.Column(db.Integer, nullable=True)
    what = db.Column(db.String(255), nullable=False)
    who_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    status = db.Column(db.String(50), default='Pending')
    note = db.Column(db.Text)
    recurrence = db.Column(db.String(20), default='none')
    recurrence_end_date = db.Column(db.Date)
    
    attachments = db.relationship('UploadedFile', backref='task', cascade="all, delete-orphan")

    def to_dict(self):
        return {
            'id': self.id,
            'date': self.task_date.strftime('%Y-%m-%d'),
            'hour': self.hour,
            'what': self.what,
            'who': self.assignee.username if self.assignee else '',
            'who_id': self.who_id,
            'status': self.status,
            'note': self.note,
            'recurrence': self.recurrence,
            'recurrence_end_date': self.recurrence_end_date.strftime('%Y-%m-%d') if self.recurrence_end_date else None,
            'attachments': [att.to_dict() for att in self.attachments]
        }

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
    
    status = db.Column(db.String(20), nullable=False, default='Active', server_default='Active')
    objectives = db.relationship('Objective', backref='project', cascade="all, delete-orphan")

class Objective(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(500), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    color = db.Column(db.String(20))
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'))
    key_results = db.relationship('KeyResult', backref='objective', cascade="all, delete-orphan")

    @property
    def progress(self):
        krs = self.key_results
        if not krs: return 0
        return sum(kr.progress for kr in krs) / len(krs)

class KeyResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(500), nullable=False)
    current = db.Column(db.Float, default=0)
    target = db.Column(db.Float, default=1)
    objective_id = db.Column(db.Integer, db.ForeignKey('objective.id'), nullable=False)
    action_items = db.relationship('ActionItem', backref='key_result', cascade="all, delete-orphan")

    @property
    def progress(self):
        if self.target == 0: return 0
        return min(100, (self.current / self.target) * 100)

class ActionItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(50), default='To Do')
    due_date = db.Column(db.Date)
    report = db.Column(db.Text)
    key_result_id = db.Column(db.Integer, db.ForeignKey('key_result.id'), nullable=False)
    assignee_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    attachments = db.relationship('UploadedFile', backref='action_item', cascade="all, delete-orphan")
    def to_dict(self):
        return {
            'id': self.id,
            'content': self.content,
            'status': self.status,
            'due_date': self.due_date.strftime('%Y-%m-%d') if self.due_date else None,
            'assignee_name': self.assignee.username if self.assignee else None,
            'assignee_id': self.assignee_id,
            'kr_id': self.key_result_id,
            'detail_url': url_for('main.action_detail', action_id=self.id)
        }

class Kaizen(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    week_start_date = db.Column(db.Date, nullable=False)
    problem = db.Column(db.Text, nullable=False)
    solution = db.Column(db.Text)

# ==============================================================================
# UPLOADS MANAGER
# ==============================================================================

class UploadedFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    original_filename = db.Column(db.String(255), nullable=False)
    saved_filename = db.Column(db.String(255), nullable=False, unique=True)
    file_type = db.Column(db.String(20))
    file_size = db.Column(db.Integer)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    uploader_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=True)
    action_item_id = db.Column(db.Integer, db.ForeignKey('action_item.id'), nullable=True)
    note_id = db.Column(db.Integer, db.ForeignKey('note.id'), nullable=True)
    upload_source = db.Column(db.String(50), default='attachment') # attachment | direct
    
    
    def to_dict(self):
        return {
            'id': self.id,
            'original_filename': self.original_filename,
            'url': url_for('main.uploaded_file', filename=self.saved_filename),
            'delete_url': url_for('main.delete_uploaded_file', file_id=self.id)
        }

# Trong file app/models.py, thay thế property context của class UploadedFile

    @property
    def upload_date_local(self):
        if not self.upload_date:
            return None
        return self.upload_date + timedelta(hours=7)  # GMT+7
    def context(self):
        # Ưu tiên nguồn upload được đánh dấu tường minh
        if self.upload_source == 'direct':
            return {'text': 'Tải lên trực tiếp', 'url': None}
        
        # Nếu không, xác định bối cảnh qua liên kết
        if self.task_id and self.task:
            task_date = self.task.task_date.strftime('%Y-%m-%d')
            return {
                'text': 'Công việc',
                'url': url_for('main.index', view_mode='day', date_str=task_date)
            }
        if self.action_item_id and self.action_item:
            return {
                'text': 'Hành động OKR',
                'url': url_for('main.action_detail', action_id=self.action_item_id)
            }
        if self.note_id and self.note:
            return {
                'text': 'Ghi chú',
                'url': url_for('main.notes')
            }
        
        # Mặc định là đính kèm nếu không có nguồn rõ ràng
        return {
            'text': 'Đính kèm',
            'url': None
        }

# ==============================================================================
# NOTE & COLUMN MODELS
# ==============================================================================
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
# Dán vào cuối file app/models.py
# Dán vào cuối file app/models.py

# Trong file app/models.py
class PracticeLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    log_ts = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # --- Dữ liệu từ Ghi nhận nhanh ---
    tag = db.Column(db.String(50), nullable=False, index=True)
    note = db.Column(db.Text)
    
    # --- Dữ liệu từ Quán chiếu sâu ---
    situation = db.Column(db.Text, nullable=True) 
    sense_door = db.Column(db.String(50), nullable=True) # Căn: Mắt, Tai...
    sense_object = db.Column(db.Text, nullable=True)  # **NEW**: Trần: Hình ảnh A, Âm thanh B...
    feeling = db.Column(db.String(200), nullable=True)      # Thọ
    craving = db.Column(db.String(200), nullable=True)     # Ái
    contemplation = db.Column(db.Text, nullable=True)
    outcome = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    intensity = db.Column(db.Integer, nullable=True)     # 1..5
    duration_min = db.Column(db.Integer, nullable=True)  # phút
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