# WFH_Launcher.spec (Phiên bản cuối cùng, đơn giản và đáng tin cậy)

a = Analysis(
    ['launcher.py'], # Tên file launcher của bạn
    pathex=[],
    binaries=[],
    datas=[
        # Sao chép toàn bộ các thư mục và file cần thiết vào gói
        ('app/templates', 'app/templates'),
        ('app/static', 'app/static'),
        ('migrations', 'migrations'), # <-- Đảm bảo thư mục migrations được đưa vào
        ('config.py', '.'),
        ('run.py', '.'),
        ('my_icon.ico', '.') # Tên file icon của bạn
    ],
    hiddenimports=[
        'waitress', 
        'sqlalchemy.sql.default_comparator',
        'flask_migrate', # <-- Thêm flask_migrate để chắc chắn
        'app.models', 
        'app.routes',
        'app.auth'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='WorkManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon='my_icon.ico', # Tên file icon của bạn
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='WorkManager',
)