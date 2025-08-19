from app import create_app

app = create_app()

# Import routes sau khi app đã được tạo
from app import routes

if __name__ == '__main__':
    # Tạm thời dùng app.run() để debug dễ hơn
    app.run(debug=True, host='0.0.0.0', port=8000)