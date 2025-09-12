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

    print("[STEP 2/2] Seeding initial users...")

    # SỬA: Định nghĩa một danh sách các user bạn muốn tạo ở đây
    users_to_create = [
        {'username': 'admin', 'email': 'admin@example.com', 'password': 'your_admin_password'},
        {'username': 'phuong.vien', 'email': 'phuong.vien@example.com', 'password': 'adidaphat'},
        {'username': 'van.anh', 'email': 'test1@example.com', 'password': 'adidaphat'},
        {'username': 'user_test2', 'email': 'test2@example.com', 'password': 'password456'},
        # Thêm các user khác vào đây...
    ]

    try:
        # SỬA: Dùng vòng lặp for để xử lý từng user trong danh sách
        for user_data in users_to_create:
            # Kiểm tra xem user đã tồn tại chưa
            user_in_db = db.session.execute(select(User).where(User.username == user_data['username'])).first()
            
            if not user_in_db:
                # Nếu chưa tồn tại, tạo user mới
                hashed_password = generate_password_hash(user_data['password'])
                new_user = User(
                    username=user_data['username'], 
                    email=user_data['email'], 
                    password_hash=hashed_password
                )
                db.session.add(new_user)
                print(f"==> SUCCESS: User '{user_data['username']}' will be created.")
            else:
                # Nếu đã tồn tại, bỏ qua
                print(f"==> INFO: User '{user_data['username']}' already exists. Skipping creation.")
        
        # SỬA: Commit tất cả các thay đổi (thêm user) một lần duy nhất sau vòng lặp
        db.session.commit()
        print("\n==> SUCCESS: All new users have been committed to the database.")

    except Exception as e:
        print(f"==> ERROR: An error occurred while creating users. Reason: {e}")
        db.session.rollback()


print("--- [END] Database setup finished. ---")
