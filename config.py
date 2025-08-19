import os
import sys

# ==============================================================================
# THAY THẾ BẰNG ĐOẠN CODE NÀY
# ==============================================================================
# Xác định thư mục gốc của ứng dụng, hoạt động cho cả script và file .exe
if getattr(sys, 'frozen', False):
    # Nếu đang chạy từ file .exe đã đóng gói
    basedir = os.path.dirname(sys.executable)
else:
    # Nếu đang chạy như một script .py bình thường
    basedir = os.path.abspath(os.path.dirname(__file__))
# ==============================================================================


class Config:
    """Set Flask configuration variables."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'ban-nen-thay-doi-chuoi-nay-de-bao-mat-hon'

    # Database configuration
    # Dòng này giờ sẽ luôn trỏ tới file database.db nằm cạnh file .exe hoặc script
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'database.db')
        
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Uploads configuration
    # Sửa lại đường dẫn UPLOAD_FOLDER để dùng basedir mới
    UPLOAD_FOLDER = os.path.join(basedir, 'app', 'static', 'uploads')
    
    # Giới hạn dung lượng file upload
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024 * 1024  # 2GB