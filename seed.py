# seed.py
from sqlalchemy import select
from werkzeug.security import generate_password_hash
from sqlalchemy.exc import DataError, StatementError

# Import các thành phần cần thiết từ ứng dụng của bạn
from app import create_app, db
from app.models import User

print("--- Running Database Seeder ---")

# Tạo một instance của ứng dụng Flask để có context
flask_app = create_app()

# Đẩy context của ứng dụng vào để có thể thao tác với database
with flask_app.app_context():
    
    # Kiểm tra xem đã có user nào trong bảng 'user' chưa
    # Dùng try-except để bắt lỗi nếu bảng chưa tồn tại (mặc dù db upgrade đã chạy trước)
    try:
        has_user = db.session.execute(select(User.id)).first()
    except Exception as e:
        print(f"Could not check for existing users, assuming none exist. Error: {e}")
        has_user = None

    if not has_user:
        print("Database is empty. Creating default admin user...")
        
        # Tạo đối tượng user
        user = User(username="admin", email="admin@example.com")
        
        try:
            # Sử dụng method set_password từ model User
            user.set_password("adidaphat")
            db.session.add(user)
            db.session.commit()
            print("==> Successfully created user: admin / adidaphat")
        except (DataError, StatementError) as e:
            # Xử lý fallback nếu có lỗi về độ dài hash password
            db.session.rollback()
            print(f"Caught DB error: {e}. Falling back to pbkdf2.")
            user.password_hash = generate_password_hash("adidaphat", method="pbkdf2:sha256")
            db.session.add(user)
            db.session.commit()
            print("==> Successfully created user with fallback hash: admin / adidaphat")
        except Exception as e:
            db.session.rollback()
            print(f"An unexpected error occurred during user creation: {e}")
    else:
        print("Database already contains users. Skipping seed process.")

print("--- Seeder finished ---")