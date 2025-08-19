# launcher_tkinter.py — Premium Tkinter Launcher cho Flask + Waitress
# - Giao diện xịn: header gradient, 2 cột, nút lớn, đèn trạng thái
# - Dừng server mềm (không thoát app) với waitress.create_server()
# - Dark mode toggle, Always-on-top, phím tắt, copy/open URL, refresh IP, clear log
# - ★ Thêm User Manager (nút riêng + Ctrl+U, không mở trùng)

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, font as tkFont
import socket
import threading
import os
import sys
import webbrowser
import time
from datetime import datetime

# ============= CẤU HÌNH (có thể override bằng ENV) =============
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "5000"))
ICON_FILE = "my_icon.ico"

# ============= IMPORT FLASK APP + WAITRESS =============
try:
    from run import app  # Flask WSGI app object
    from app import db
    from app.models import User
    try:
        # create_server cho phép đóng server mềm
        from waitress import create_server
        HAVE_CREATE_SERVER = True
    except Exception:
        from waitress import serve  # fallback (không stop mềm được)
        HAVE_CREATE_SERVER = False
    FLASK_APP_IMPORTED = True
except Exception as e:
    FLASK_APP_IMPORTED = False
    IMPORT_ERROR_MSG = (
        f"Lỗi import ứng dụng Flask: {e}\n\n"
        "Chức năng Server và Quản lý User sẽ bị vô hiệu hóa."
    )

# ============= HỖ TRỢ MẠNG/CHUNG =============
def resource_path(relative_path: str) -> str:
    try:
        base_path = sys._MEIPASS  # PyInstaller
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def get_lan_ip() -> str:
    """IP LAN (best effort)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # không gửi data
        ip = s.getsockname()[0]
    except Exception:
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip = "127.0.0.1"
    finally:
        try:
            s.close()
        except Exception:
            pass
    return ip

def get_hostname() -> str:
    return socket.gethostname()

def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host if host != "0.0.0.0" else "127.0.0.1", port)) == 0


# ============= LAUNCHER APP =============
class AppLauncher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Con người đi trước - Công việc theo sau")
        self.geometry("900x850")
        self.minsize(900, 580)
        try:
            self.iconbitmap(resource_path(ICON_FILE))
        except Exception:
            pass

        # Trạng thái server
        self.server_thread = None
        self.server_obj = None
        self._server_running = False
        self._dark_mode = False
        self._always_on_top = False

        # ★ giữ ref tới cửa sổ User Manager để tránh mở trùng
        self._user_win = None

        self._init_fonts()
        self._init_styles()
        self._build_ui()
        self._bind_shortcuts()
        self.protocol("WM_DELETE_WINDOW", self.on_exit)

        # Init UI state
        if not FLASK_APP_IMPORTED:
            self._log(IMPORT_ERROR_MSG, level="ERROR")
        else:
            self._log("Sẵn sàng. Nhấn “Bắt đầu Server” để chạy Waitress.")
        self.update_urls()
        self._update_status_ui()

    # ---------- Fonts ----------
    def _init_fonts(self):
        try:
            self.header_font = tkFont.Font(family="Quicksand", size=12, weight="bold")
            self.body_font   = tkFont.Font(family="Quicksand", size=10)
            self.small_font  = tkFont.Font(family="Quicksand", size=10, weight="bold")
            self.status_font = tkFont.Font(family="Quicksand", size=10, weight="bold")
        except tk.TclError:
            self.header_font = tkFont.Font(family="Segoe UI Light", size=12, weight="bold")
            self.body_font   = tkFont.Font(family="Segoe UI Light", size=10)
            self.small_font  = tkFont.Font(family="Segoe UI Light", size=10, weight="bold")
            self.status_font = tkFont.Font(family="Segoe UI Light", size=10, weight="bold")

    # ---------- Styles & palette ----------
# ---------- Styles & palette ----------
    def _palette(self):
        """
        Bảng màu được thiết kế lại để hài hòa và hiện đại hơn.
        - Lấy cảm hứng từ bảng màu Tailwind CSS.
        - Tăng cường độ tương phản và chiều sâu cho cả 2 chế độ.
        - Khu vực Log được đồng bộ với theme chung.
        """
        if self._dark_mode:
            return dict(
                # Nền và Chữ
                BG="#0F172A",         # Xanh đen rất đậm (Slate 900)
                FG="#E2E8F0",         # Xám nhạt (Slate 200)
                SUB="#94A3B8",        # Xám vừa (Slate 400)
                # Thẻ và Viền
                CARD="#1E293B",       # Xanh đen vừa (Slate 800)
                BORDER="#334155",     # Xanh đen nhạt (Slate 700)
                # Màu nhấn (Accent)
                ACCENT="#818CF8",     # Tím Indigo nhạt (Indigo 400)
                ACCENT_H="#6366F1",   # Tím Indigo đậm (Indigo 500)
                # Màu cảnh báo (Danger)
                DANGER="#F43F5E",     # Đỏ hồng (Rose 500)
                DANGER_H="#E11D48",   # Đỏ hồng đậm (Rose 600)
                # Màu tối cho nút
                DARK="#4B5563",       # Xám đậm (Gray 600)
                DARK_H="#374151",     # Xám đậm hơn (Gray 700)
                # Khung nhập liệu (Entry)
                ENTRY_BG="#0F172A",   # Giống nền chính
                ENTRY_FG="#E2E8F0",   # Giống chữ chính
                # Khu vực Log
                LOG_BG="#020617",     # Đen tuyền ánh xanh (Slate 950)
                LOG_FG="#D1D5DB",     # Xám rất nhạt (Gray 300)
            )
        else: # Light Mode
            return dict(
                # Nền và Chữ
                BG="#F8FAFC",         # Xám siêu nhạt (Slate 50)
                FG="#1E293B",         # Xanh đen (Slate 800)
                SUB="#64748B",        # Xám vừa (Slate 500)
                # Thẻ và Viền
                CARD="#FFFFFF",       # Trắng
                BORDER="#E2E8F0",     # Xám nhạt (Slate 200)
                # Màu nhấn (Accent)
                ACCENT="#3B82F6",     # Xanh dương (Blue 500)
                ACCENT_H="#2563EB",   # Xanh dương đậm (Blue 600)
                # Màu cảnh báo (Danger)
                DANGER="#EF4444",     # Đỏ (Red 500)
                DANGER_H="#DC2626",   # Đỏ đậm (Red 600)
                # Màu tối cho nút
                DARK="#475569",       # Xanh xám (Slate 600)
                DARK_H="#334155",     # Xanh xám đậm (Slate 700)
                # Khung nhập liệu (Entry)
                ENTRY_BG="#FFFFFF",   # Trắng
                ENTRY_FG="#1E293B",   # Giống chữ chính
                # Khu vực Log (Nền tối chữ sáng để dễ đọc log)
                LOG_BG="#1E293B",     # Xanh đen (Slate 800)
                LOG_FG="#D1D5DB",     # Xám nhạt (Gray 300)
            )

    def _init_styles(self):
        self.style = ttk.Style(self)
        try:
            self.style.theme_use("clam")
        except Exception:
            pass
        self._apply_style()

    def _apply_style(self):
        P = self._palette()
        self.configure(bg=P["BG"])
        s = self.style
        # Base
        s.configure("TFrame", background=P["BG"])
        s.configure("TLabel", background=P["BG"], foreground=P["FG"], font=self.body_font)
        s.configure("TCheckbutton", background=P["BG"], foreground=P["FG"], font=self.body_font)
        s.configure("TEntry", fieldbackground=P["ENTRY_BG"], foreground=P["ENTRY_FG"])

        # Cards
        s.configure("Card.TLabelframe", background=P["CARD"], bordercolor=P["BORDER"])
        s.configure("Card.TLabelframe.Label", font=self.header_font, foreground=P["FG"])
        s.configure("CardInner.TFrame", background=P["CARD"])

        # Buttons
        s.configure("Primary.TButton", background=P["ACCENT"], foreground="white",
                    padding=10, font=self.small_font, bordercolor=P["ACCENT"])
        s.map("Primary.TButton", background=[("active", P["ACCENT_H"])])

        s.configure("Dark.TButton", background=P["DARK"], foreground="white",
                    padding=10, font=self.small_font, bordercolor=P["DARK"])
        s.map("Dark.TButton", background=[("active", "#000000")])

        s.configure("Danger.TButton", background=P["DANGER"], foreground="black",
                    padding=10, font=self.small_font, bordercolor=P["DANGER"])
        s.map("Danger.TButton", background=[("active", "#e60b0b")])

        s.configure("Ghost.TButton", padding=8)

    # ---------- Header gradient ----------
    def _draw_header_gradient(self, event=None):
        P = self._palette()
        c = self.header_canvas
        w = c.winfo_width() or 1
        h = c.winfo_height() or 1
        c.delete("all")
        # simple horizontal gradient
        steps = 64
        for i in range(steps):
            r = i / steps
            # blend from accent to card/bg
            color = self._blend(P["ACCENT"], P["CARD"] if not self._dark_mode else "#111827", r)
            c.create_rectangle(int(i*w/steps), 0, int((i+1)*w/steps), h, outline="", fill=color)

        # Title & status (drawn as text to look crisp)
        c.create_text(16, h//2, anchor="w", fill="white",
            font=("Segoe UI", 13, "bold"),
            text="Ra về ta tự hỏi ta - Tám giờ vàng ngọc làm ra cái gì?")

    def _blend(self, c1, c2, t):
        # hex mix
        def to_rgb(hexstr):
            hexstr = hexstr.lstrip("#")
            return tuple(int(hexstr[i:i+2], 16) for i in (0, 2, 4))
        def to_hex(rgb):
            return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
        a = to_rgb(c1); b = to_rgb(c2)
        m = tuple(int(a[i]*(1-t) + b[i]*t) for i in range(3))
        return to_hex(m)

    # ---------- UI ----------
    def _build_ui(self):
        P = self._palette()

        # Header gradient bar
        self.header_canvas = tk.Canvas(self, height=54, highlightthickness=0, bd=0, relief="flat")
        self.header_canvas.pack(fill=tk.X)
        self.header_canvas.bind("<Configure>", self._draw_header_gradient)

        # Status pill (right)
        status_bar = ttk.Frame(self, padding=(12, 6))
        status_bar.place(relx=1.0, y=27, anchor="e")  # overlay trên header
        self.status_dot = ttk.Label(status_bar, text="●", foreground="#9CA3AF", font=("Segoe UI", 16))
        self.status_text = ttk.Label(status_bar, text="Server: ĐÃ DỪNG", style="TLabel")
        self.status_dot.pack(side=tk.LEFT, padx=(0, 6))
        self.status_text.pack(side=tk.LEFT)

        # Main content: 2 cột
        wrap = ttk.Frame(self, padding="12")
        wrap.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(wrap)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=False)
        right = ttk.Frame(wrap)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0))

        # ===== URLs card =====
        urls_card = ttk.Labelframe(left, text="Truy cập trong LAN", style="Card.TLabelframe", padding=10)
        urls_card.pack(fill=tk.X, pady=(0, 12))

        self.url_local_var = tk.StringVar()
        self.url_lan_var   = tk.StringVar()
        self.url_host_var  = tk.StringVar()

        url_grid = ttk.Frame(urls_card, style="CardInner.TFrame")
        url_grid.pack(fill=tk.X, padx=4, pady=4)
        url_grid.columnconfigure(1, weight=1)

        self._mk_url_row(url_grid, 0, "Local", self.url_local_var,
                         self.open_local, lambda: self._copy(self.url_local_var.get()))
        self._mk_url_row(url_grid, 1, "LAN",   self.url_lan_var,
                         self.open_lan,   lambda: self._copy(self.url_lan_var.get()))
        self._mk_url_row(url_grid, 2, "Host",  self.url_host_var,
                         self.open_host,  lambda: self._copy(self.url_host_var.get()))

        ttk.Button(urls_card, text="↻ Cập nhật IP/URL", style="Ghost.TButton",
                   command=self.update_urls).pack(anchor=tk.E, padx=4, pady=(6, 2))

        # ===== Controls card =====
        ctrl_card = ttk.Labelframe(left, text="Điều khiển Server", style="Card.TLabelframe", padding=10)
        ctrl_card.pack(fill=tk.X, pady=(0, 12))

        ctrl = ttk.Frame(ctrl_card, style="CardInner.TFrame")
        ctrl.pack(fill=tk.X)

        self.start_button = ttk.Button(ctrl, text="▶  Bắt đầu Server", style="Primary.TButton",
                                       command=self.start_server)
        self.stop_button  = ttk.Button(ctrl, text="■  Dừng Server", style="Danger.TButton",
                                       command=self.stop_server)
        self.restart_button  = ttk.Button(ctrl, text="↻  Khởi động lại", style="Dark.TButton",
                                          command=self.restart_server)

        self.start_button.pack(fill=tk.X, padx=2, pady=4)
        self.stop_button.pack(fill=tk.X, padx=2, pady=4)
        self.restart_button.pack(fill=tk.X, padx=2, pady=4)

        # Toggles
        toggles = ttk.Frame(ctrl_card, style="CardInner.TFrame")
        toggles.pack(fill=tk.X, pady=(8, 0))
        self.dark_var = tk.BooleanVar(value=self._dark_mode)
        self.top_var  = tk.BooleanVar(value=self._always_on_top)

        ttk.Checkbutton(toggles, text="Dark mode", variable=self.dark_var,
                        command=self.toggle_dark).pack(side=tk.LEFT, padx=(2, 8))
        ttk.Checkbutton(toggles, text="Always on top", variable=self.top_var,
                        command=self.toggle_on_top).pack(side=tk.LEFT)

        # ★ User Manager card + nút mở
        user_card = ttk.Labelframe(left, text="Người dùng", style="Card.TLabelframe", padding=10)
        user_card.pack(fill=tk.X, pady=(12, 12))
        self.user_btn = ttk.Button(user_card, text="👤 Quản lý User (Ctrl+U)",
                                   style="Dark.TButton", command=self.open_user_manager)
        self.user_btn.pack(fill=tk.X)
        if not FLASK_APP_IMPORTED:
            self.user_btn.config(state=tk.DISABLED)

        # ===== About / Shortcuts =====
        help_card = ttk.Labelframe(left, text="Mẹo & Phím tắt", style="Card.TLabelframe", padding=10)
        help_card.pack(fill=tk.BOTH, expand=True)
        help_lbl = ttk.Label(help_card,
                             text="• Ctrl+S: Start/Stop\n"
                                  "• F5: Refresh IP/URL\n"
                                  "• Ctrl+L: Clear log\n"
                                  "• Ctrl+U: Mở Quản lý User\n"
                                  "• Click đường link → Mở trình duyệt",
                             justify="left")
        help_lbl.pack(anchor="w")

        # ===== Right column: Status + Log =====
        stat_card = ttk.Labelframe(right, text="Trạng thái", style="Card.TLabelframe", padding=10)
        stat_card.pack(fill=tk.X)
        self.progress = ttk.Progressbar(stat_card, orient="horizontal", mode="determinate", maximum=100)
        self.progress.pack(fill=tk.X, padx=2, pady=2)

        log_card = ttk.Labelframe(right, text="Log Server", style="Card.TLabelframe", padding=10)
        log_card.pack(fill=tk.BOTH, expand=True, pady=(12, 0))
        self.log_text = scrolledtext.ScrolledText(
            log_card, wrap=tk.WORD, state=tk.DISABLED,
            bg=self._palette()["LOG_BG"], fg=self._palette()["LOG_FG"], insertbackground="white"
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        # tags để tô màu level
        self.log_text.tag_config("INFO", foreground="#a7f3d0")
        self.log_text.tag_config("WARN", foreground="#fde68a")
        self.log_text.tag_config("ERROR", foreground="#fecaca")

        log_controls = ttk.Frame(log_card)
        log_controls.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(log_controls, text="Clear log", style="Ghost.TButton",
                   command=self.clear_log).pack(side=tk.LEFT)
        ttk.Button(log_controls, text="Copy LAN URL", style="Ghost.TButton",
                   command=lambda: self._copy(self.url_lan_var.get())).pack(side=tk.LEFT, padx=(8,0))

        # Disable buttons if Flask app missing
        if not FLASK_APP_IMPORTED:
            for b in (self.start_button, self.stop_button, self.restart_button):
                b.config(state=tk.DISABLED)

    def _mk_url_row(self, parent, row, label, var, open_fn, copy_fn):
        ttk.Label(parent, text=label, width=10).grid(row=row, column=0, sticky=tk.W, padx=2, pady=3)
        e = ttk.Entry(parent, textvariable=var, state="readonly")
        e.grid(row=row, column=1, sticky=tk.EW, padx=2, pady=3)
        ttk.Button(parent, text="Mở", style="Ghost.TButton", width=8, command=open_fn).grid(row=row, column=2, padx=2)
        ttk.Button(parent, text="Copy", style="Ghost.TButton", width=8, command=copy_fn).grid(row=row, column=3, padx=2)
        parent.columnconfigure(1, weight=1)

    # ---------- Shortcuts ----------
    def _bind_shortcuts(self):
        self.bind("<Control-s>", lambda e: self.start_server() if not self._server_running else self.stop_server())
        self.bind("<F5>", lambda e: self.update_urls())
        self.bind("<Control-l>", lambda e: self.clear_log())
        # ★ mở User Manager
        self.bind("<Control-u>", lambda e: self.open_user_manager() if FLASK_APP_IMPORTED else None)

    # ---------- Theme toggles ----------
    def toggle_dark(self):
        self._dark_mode = bool(self.dark_var.get())
        self._apply_style()
        # recolor log background immediately
        P = self._palette()
        self.log_text.config(bg=P["LOG_BG"], fg=P["LOG_FG"], insertbackground=("white" if self._dark_mode else "black"))
        self._draw_header_gradient()

    def toggle_on_top(self):
        self._always_on_top = bool(self.top_var.get())
        self.attributes("-topmost", self._always_on_top)

    # ---------- URL helpers ----------
    def update_urls(self):
        self.url_local_var.set(f"http://127.0.0.1:{APP_PORT}")
        self.url_lan_var.set(f"http://{get_lan_ip()}:{APP_PORT}")
        self.url_host_var.set(f"http://{get_hostname()}:{APP_PORT}")
        self._toast("Đã cập nhật địa chỉ truy cập.")

    def _copy(self, text):
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self._toast("Đã copy vào clipboard.")
        except Exception:
            pass
        self._log(f"COPY: {text}", level="INFO")

    def open_local(self): webbrowser.open(self.url_local_var.get())
    def open_lan(self):   webbrowser.open(self.url_lan_var.get())
    def open_host(self):  webbrowser.open(self.url_host_var.get())

    # ---------- Toast mini ----------
    def _toast(self, msg: str, ms: int = 1300):
        # label nhẹ ở góc phải
        P = self._palette()
        if hasattr(self, "_toast_lbl") and self._toast_lbl.winfo_exists():
            self._toast_lbl.destroy()
        self._toast_lbl = tk.Label(self, text=msg,
                                   bg=P["ACCENT"], fg="white",
                                   padx=10, pady=4)
        self._toast_lbl.place(relx=1.0, rely=1.0, x=-14, y=-14, anchor="se")
        self.after(ms, lambda: self._toast_lbl.destroy() if self._toast_lbl.winfo_exists() else None)

    # ---------- Log & Status ----------
    def _log(self, message: str, level: str = "INFO"):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {level:<5} {message.strip()}\n"
        tag = "INFO" if level not in ("WARN", "ERROR") else level
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, line, tag)
        self.log_text.config(state=tk.DISABLED)
        self.log_text.see(tk.END)

    def clear_log(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _update_status_ui(self):
        if self._server_running:
            self.status_text.config(text="Server: ĐANG CHẠY")
            self.status_dot.config(foreground="#22c55e")
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.restart_button.config(state=tk.NORMAL)
        else:
            self.status_text.config(text="Server: ĐÃ DỪNG")
            self.status_dot.config(foreground="#9CA3AF")
            self.start_button.config(state=tk.NORMAL if FLASK_APP_IMPORTED else tk.DISABLED)
            self.stop_button.config(state=tk.DISABLED)
            self.restart_button.config(state=tk.DISABLED)
        # progress reset
        self.progress["value"] = 0

    # ---------- Server lifecycle ----------
    def start_server(self):
        if not FLASK_APP_IMPORTED:
            messagebox.showerror("Lỗi", "Không thể import ứng dụng Flask.")
            return
        if self._server_running:
            return

        if port_in_use(APP_HOST, APP_PORT):
            msg = (f"Port {APP_PORT} đang được sử dụng.\n"
                   f"Hãy tắt tiến trình khác hoặc đổi APP_PORT.")
            messagebox.showerror("Port đang bận", msg)
            self._log(msg, level="ERROR")
            return

        def target():
            self._server_running = True
            self._update_status_ui()
            self.update_urls()
            self._log(f"Server đang chạy trên {APP_HOST}:{APP_PORT}")
            self._log(f"  Local:  {self.url_local_var.get()}")
            self._log(f"  LAN:    {self.url_lan_var.get()}")
            self._log(f"  Host:   {self.url_host_var.get()}")

            try:
                if HAVE_CREATE_SERVER:
                    self.server_obj = create_server(app, host=APP_HOST, port=APP_PORT, threads=8)
                    self.server_obj.run()  # block tới khi close()
                else:
                    self._log("[Lưu ý] Waitress bản cũ — không dừng mềm được.", level="WARN")
                    from waitress import serve
                    serve(app, host=APP_HOST, port=APP_PORT, threads=8, _quiet=True)
            except Exception as e:
                self._log(f"Server lỗi: {e}", level="ERROR")
                try:
                    messagebox.showerror("Server lỗi", str(e))
                except Exception:
                    pass
            finally:
                self._server_running = False
                self.server_obj = None
                self._update_status_ui()
                self._log("Server đã dừng.")

        self._log(f"Đang khởi động server tại {self.url_lan_var.get()} ...")
        self.server_thread = threading.Thread(target=target, daemon=True)
        self.server_thread.start()

    def stop_server(self):
        """Dừng server nhưng KHÔNG thoát app."""
        if not self._server_running:
            return
        if HAVE_CREATE_SERVER and self.server_obj is not None:
            self._log("Đang dừng server ...")
            try:
                self.progress.start(8)
                self.server_obj.close()  # yêu cầu waitress dừng
            except Exception as e:
                self._log(f"close() gặp lỗi: {e}", level="WARN")
            finally:
                # chờ thread kết thúc nhẹ nhàng
                if self.server_thread is not None:
                    self.server_thread.join(timeout=3)
                self.progress.stop()
        else:
            messagebox.showinfo("Không hỗ trợ", "Waitress bản này không hỗ trợ dừng mềm.\n"
                                                "Hãy nâng cấp waitress >= 2.1 hoặc chạy lại app.")
        self._server_running = False
        self.server_obj = None
        self._update_status_ui()

    def restart_server(self):
        """Dừng rồi khởi động lại."""
        if self._server_running:
            self.stop_server()
            # đợi chút cho port giải phóng
            time.sleep(0.3)
        self.start_server()

    # ---------- App lifecycle ----------
    def on_exit(self):
        if self._server_running:
            if not messagebox.askyesno("Thoát", "Server đang chạy. Dừng server rồi thoát?"):
                return
            self.stop_server()
        self.destroy()
        os._exit(0)

    # ---------- User Manager ----------
    def open_user_manager(self):
        """★ Mở (hoặc focus) cửa sổ Quản lý User."""
        if not FLASK_APP_IMPORTED:
            messagebox.showerror("Lỗi", "Không thể import Flask app.")
            return
        # nếu đã mở, focus
        if self._user_win is not None and self._user_win.winfo_exists():
            try:
                self._user_win.deiconify()
                self._user_win.lift()
                self._user_win.focus_force()
            except Exception:
                pass
            return
        # tạo mới
        self._user_win = UserManagerWindow(self)


# ============= USER MANAGER =============
class UserManagerWindow(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Quản lý Người dùng")
        self.geometry("480x520")
        self.transient(master)
        self.grab_set()

        PARENT_STYLE = master.style

        main = ttk.Frame(self, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        lf_list = ttk.Labelframe(main, text="Danh sách User", style="Card.TLabelframe", padding=10)
        lf_list.pack(fill=tk.BOTH, expand=True, pady=6)

        self.user_listbox = tk.Listbox(lf_list)
        self.user_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        sb = ttk.Scrollbar(lf_list, orient=tk.VERTICAL, command=self.user_listbox.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.user_listbox.config(yscrollcommand=sb.set)

        form = ttk.Labelframe(main, text="Thêm / Sửa User", style="Card.TLabelframe", padding=10)
        form.pack(fill=tk.X, pady=6)

        ttk.Label(form, text="Username:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.username_entry = ttk.Entry(form)
        self.username_entry.grid(row=0, column=1, padx=5, pady=5, sticky=tk.EW)

        ttk.Label(form, text="Mật khẩu mới:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.password_entry = ttk.Entry(form, show="*")
        self.password_entry.grid(row=1, column=1, padx=5, pady=5, sticky=tk.EW)
        form.columnconfigure(1, weight=1)

        btns = ttk.Frame(main)
        btns.pack(fill=tk.X, pady=8)
        ttk.Button(btns, text="Tạo User Mới", style="Primary.TButton",
                   command=self.create_user).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=3)
        self.update_button = ttk.Button(btns, text="Cập nhật Mật khẩu", style="Dark.TButton",
                                        command=self.update_password, state=tk.DISABLED)
        self.update_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=3)

        self.load_users()
        self.user_listbox.bind("<<ListboxSelect>>", self.on_user_select)

        # đóng cửa sổ -> giải phóng ref ở master
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        try:
            # dọn tham chiếu trong master để mở lại được
            self.master._user_win = None
        except Exception:
            pass
        self.destroy()

    def load_users(self):
        if not FLASK_APP_IMPORTED:
            return
        self.user_listbox.delete(0, tk.END)
        with app.app_context():
            for u in User.query.order_by(User.username).all():
                self.user_listbox.insert(tk.END, u.username)

    def on_user_select(self, _):
        sel = self.user_listbox.curselection()
        if not sel: return
        username = self.user_listbox.get(sel[0])
        self.username_entry.delete(0, tk.END)
        self.username_entry.insert(0, username)
        self.password_entry.delete(0, tk.END)
        self.update_button.config(state=tk.NORMAL)

    def create_user(self):
        if not FLASK_APP_IMPORTED:
            return
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        if not username or not password:
            messagebox.showerror("Lỗi", "Username và mật khẩu không được để trống.")
            return
        with app.app_context():
            if User.query.filter_by(username=username).first():
                messagebox.showerror("Lỗi", f"Username '{username}' đã tồn tại.")
                return
            u = User(username=username)
            u.set_password(password)
            db.session.add(u)
            db.session.commit()
        messagebox.showinfo("Thành công", f"Đã tạo người dùng '{username}'.")
        self.load_users()
        self.username_entry.delete(0, tk.END)
        self.password_entry.delete(0, tk.END)

    def update_password(self):
        if not FLASK_APP_IMPORTED:
            return
        sel = self.user_listbox.curselection()
        if not sel:
            messagebox.showerror("Lỗi", "Vui lòng chọn một user.")
            return
        username = self.user_listbox.get(sel[0])
        new_pw = self.password_entry.get().strip()
        if not new_pw:
            messagebox.showerror("Lỗi", "Mật khẩu mới không được để trống.")
            return
        if not messagebox.askyesno("Xác nhận", f"Đổi mật khẩu cho '{username}'?"):
            return
        with app.app_context():
            u = User.query.filter_by(username=username).first()
            if not u:
                messagebox.showerror("Lỗi", "Không tìm thấy user.")
                return
            u.set_password(new_pw)
            db.session.commit()
        messagebox.showinfo("Thành công", f"Đã cập nhật mật khẩu cho '{username}'.")
        self.password_entry.delete(0, tk.END)


# ============= MAIN =============
if __name__ == "__main__":
    app_win = AppLauncher()
    app_win.mainloop()
