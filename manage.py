from flask_migrate import MigrateCommand
from flask_script import Manager
from app import create_app, db

app = create_app()
manager = Manager(app)

# ✅ Đăng ký lệnh 'db'
manager.add_command('db', MigrateCommand)

if __name__ == '__main__':
    manager.run()
