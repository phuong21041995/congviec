import os
import sys
from flask import Flask, jsonify
from flask_migrate import Migrate  # thêm vào đầu file
migrate = Migrate()  # thêm dòng này

from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from jinja2 import ChoiceLoader, FileSystemLoader
from config import Config
from zoneinfo import ZoneInfo
from datetime import datetime

db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Vui lòng đăng nhập để tiếp tục.'
login_manager.login_message_category = 'warning'

# --- Jinja2 filter: UTC -> giờ VN (hoặc tz tuỳ chọn) ---
def to_local_time(value, tz_name='Asia/Ho_Chi_Minh', fmt='%Y-%m-%d %H:%M'):
    if not value:
        return ''
    try:
        if getattr(value, 'tzinfo', None) is None:
            value = value.replace(tzinfo=ZoneInfo('UTC'))
        return value.astimezone(ZoneInfo(tz_name)).strftime(fmt)
    except Exception:
        return str(value)

def exe_dir():
    return os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

def candidate_dirs(name):
    root = exe_dir()
    pkg_dir = os.path.dirname(__file__)
    cands = []
    if hasattr(sys, '_MEIPASS'):
        cands.append(os.path.join(sys._MEIPASS, 'app', name))  # type: ignore[attr-defined]
    cands.append(os.path.join(root, '_internal', 'app', name))
    cands.append(os.path.join(root, 'app', name))
    cands.append(os.path.join(pkg_dir, name))
    cands.append(os.path.join(root, name))
    return cands

def pick_first_existing(paths):
    for p in paths:
        if os.path.isdir(p):
            return p
    return paths[0]

def create_app(config_class=Config):
    cand_templates = candidate_dirs('templates')
    cand_static    = candidate_dirs('static')
    templates_dir  = pick_first_existing(cand_templates)
    static_dir     = pick_first_existing(cand_static)

    app = Flask(__name__, template_folder=templates_dir, static_folder=static_dir)
    app.config.from_object(config_class)

    try:
        upload_folder = app.config['UPLOAD_FOLDER']
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)
            print(f"Đã tạo thư mục uploads tại: {upload_folder}")
    except Exception as e:
        print(f"Lỗi khi tạo thư mục uploads: {e}")

    if not app.config.get('SECRET_KEY'):
        app.config['SECRET_KEY'] = 'change-me-please'

    uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if uri.startswith('sqlite:///'):
        rel = uri.replace('sqlite:///', '')
        if not os.path.isabs(rel):
            abs_db = os.path.join(exe_dir(), rel)
            os.makedirs(os.path.dirname(abs_db), exist_ok=True)
            app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{abs_db}'

    db.init_app(app)
    migrate.init_app(app, db) 
    bcrypt.init_app(app)
    login_manager.init_app(app)

    app.jinja_env.filters['to_local_time'] = to_local_time
    app.jinja_loader = ChoiceLoader([FileSystemLoader(p) for p in cand_templates])

    from . import models  # noqa: F401
    with app.app_context():
        db.create_all()

    # --- ĐĂNG KÝ CÁC BLUEPRINT ---
    from .auth import bp as auth_bp
    app.register_blueprint(auth_bp)

    from .routes import bp as main_bp
    app.register_blueprint(main_bp)

    # === DÒNG CODE SỬA LỖI ĐƯỢC THÊM VÀO ĐÂY ===
    from .uploads_api import bp as uploads_api_bp
    app.register_blueprint(uploads_api_bp)
    # ============================================

    @app.route('/__diag__/templates')
    def _diag_templates():
        targets = ['auth/login.html', 'login.html', 'index.html', 'base.html']
        search = cand_templates
        found = {t: [os.path.join(p, t) for p in search if os.path.isfile(os.path.join(p, t))] for t in targets}
        return jsonify({
            "template_folder": app.template_folder,
            "static_folder": app.static_folder,
            "search_paths": search,
            "exists": {p: os.path.isdir(p) for p in search},
            "found": found,
        })

    app.logger.info('TEMPLATE picked: %s', app.template_folder)
    app.logger.info('STATIC   picked: %s', app.static_folder)
    app.logger.info('SEARCH PATHS   : %s', cand_templates)

    from .models import User
    @login_manager.user_loader
    def load_user(user_id):
        try:
            return User.query.get(int(user_id))
        except Exception:
            return None

    # ✅ Tạo user mặc định nếu chưa có
    from sqlalchemy import select
    with app.app_context():
        has_user = db.session.execute(select(User.id)).first()
        if not has_user:
            app.logger.info("Không có user nào. Đang tạo user mặc định...")
            user = User(username="admin", email="admin@example.com")
            user.set_password("adidaphat")
            db.session.add(user)
            db.session.commit()
            app.logger.info("✅ Đã tạo user mặc định: admin / adidaphat")
        else:
            app.logger.info("✅ Đã có user trong database. Bỏ qua tạo mặc định.")
            
    def format_date_short(date_string):
        """Format a date string 'YYYY-MM-DD' to 'DD/MM'."""
        if isinstance(date_string, str):
            try:
                # Chuyển đổi chuỗi thành đối tượng datetime trước khi format
                dt_obj = datetime.strptime(date_string, '%Y-%m-%d')
                return dt_obj.strftime('%d/%m')
            except ValueError:
                return date_string # Trả về nguyên bản nếu format sai
        return date_string
        
    def to_date_obj(date_string):
        """Convert a 'YYYY-MM-DD' string to a date object."""
        if isinstance(date_string, str):
            try:
                return datetime.strptime(date_string, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                return None
        return None

    app.jinja_env.filters['format_date_short'] = format_date_short
    app.jinja_env.filters['to_date'] = to_date_obj # ĐĂNG KÝ FILTER MỚI
    # Trong hàm create_app, trước dòng 'return app'

    return app
