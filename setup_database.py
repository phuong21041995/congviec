# setup_database.py
import os
from app import create_app, db
from app.models import User
from werkzeug.security import generate_password_hash
from sqlalchemy import select

print("--- [START] Running Final Database Setup ---")

# Tạo một instance của ứng dụng để có context
app = create_app()

# Sử dụng app context để thao tác với database
with app.app_context():
    print("[STEP 1/2] Forcing creation of all tables from models...")
    
    # Lệnh này sẽ đọc thẳng models.py và tạo bảng, không cần thư mục migrations
    try:
        db.create_all()
        print("==> SUCCESS: All tables created.")
    except Exception as e:
        print(f"==> ERROR: Could not create tables. Reason: {e}")
        # Thoát nếu không tạo được bảng
        exit(1)

    print("[STEP 2/2] Seeding initial admin user...")
    
    # Kiểm tra xem user 'admin' đã tồn tại chưa
    user_in_db = db.session.execute(select(User).where(User.username == "admin")).first()
    
    if not user_in_db:
        try:
            hashed_password = generate_password_hash("adidaphat")
            admin_user = User(username="admin", email="admin@example.com", password_hash=hashed_password)
            db.session.add(admin_user)
            db.session.commit()
            print("==> SUCCESS: Admin user 'admin' created.")
        except Exception as e:
            print(f"==> ERROR: Could not create admin user. Reason: {e}")
            db.session.rollback()
    else:
        print("==> INFO: Admin user already exists. Skipping creation.")

print("--- [END] Database setup finished. ---")