from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
import click
from jinja2 import TemplateNotFound  # <-- thêm để bắt lỗi template
from app import db, bcrypt, login_manager
from app.models import User, Task, ActionItem, Objective, UploadedFile, Log

bp = Blueprint('auth', __name__, url_prefix='/auth')

# GHI CHÚ: @login_manager.user_loader đã chuyển sang app/__init__.py

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.index'))
        else:
            flash('Đăng nhập thất bại. Vui lòng kiểm tra lại tên đăng nhập hoặc mật khẩu.', 'danger')

    # Thử render theo 2 vị trí: 'auth/login.html' rồi fallback 'login.html'
    try:
        return render_template('auth/login.html')
    except TemplateNotFound:
        return render_template('login.html')

@bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

# ==============================================================================
# LỆNH COMMAND LINE (CLI)
# ==============================================================================

@bp.cli.command('create-user')
@click.argument('username')
@click.argument('password')
def create_user_command(username, password):
    """Tạo một người dùng mới."""
    if User.query.filter_by(username=username).first():
        print(f"Lỗi: Người dùng '{username}' đã tồn tại.")
        return
    new_user = User(username=username, email=f"{username}@example.com")
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()
    print(f"Đã tạo người dùng '{username}' thành công.")

@bp.cli.command('change-password')
@click.argument('username')
@click.argument('new_password')
def change_password_command(username, new_password):
    """Thay đổi mật khẩu cho một người dùng đã tồn tại."""
    user = User.query.filter_by(username=username).first()
    if not user:
        print(f"Lỗi: Người dùng '{username}' không tồn tại.")
        return
    user.set_password(new_password)
    db.session.commit()
    print(f"Đã cập nhật mật khẩu cho người dùng '{username}' thành công.")

@bp.cli.command('delete-user')
@click.argument('username')
def delete_user_command(username):
    """Xóa một người dùng và gỡ họ khỏi các nhiệm vụ được giao."""
    user = User.query.filter_by(username=username).first()
    if not user:
        print(f"Lỗi: Người dùng '{username}' không tồn tại.")
        return

    if not click.confirm(f"Bạn có chắc chắn muốn xóa người dùng '{username}' không? Hành động này không thể hoàn tác."):
        print("Hành động đã được hủy.")
        return

    try:
        Task.query.filter_by(who_id=user.id).update({'who_id': None})
        ActionItem.query.filter_by(assignee_id=user.id).update({'assignee_id': None})
        Objective.query.filter_by(owner_id=user.id).update({'owner_id': None})
        UploadedFile.query.filter_by(uploader_id=user.id).update({'uploader_id': None})
        Log.query.filter_by(user_id=user.id).update({'user_id': None})
        db.session.delete(user)
        db.session.commit()
        print(f"Đã xóa người dùng '{username}' và cập nhật các nhiệm vụ liên quan thành công.")
    except Exception as e:
        db.session.rollback()
        print(f"Đã xảy ra lỗi khi xóa người dùng: {e}")
