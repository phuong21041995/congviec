# migrate.py
from flask_migrate import upgrade
from app import create_app, db

# Tạo app context để script có thể kết nối database
app = create_app()
with app.app_context():
    print("--- Running database migrations programmatically ---")
    
    # Đây là lệnh tương đương với `flask db upgrade`
    upgrade()
    
    print("--- Migrations finished ---")