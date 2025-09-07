import os
import json
import hashlib
from datetime import datetime
from flask import Blueprint, current_app, request, jsonify, url_for
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from sqlalchemy.exc import IntegrityError
from app import db
from app.models import UploadedFile

bp = Blueprint("uploads_api", __name__, url_prefix="/api/uploads")

def _ensure_dirs():
    up_dir = current_app.config['UPLOAD_FOLDER']
    tmp_dir = os.path.join(up_dir, "_chunks")
    os.makedirs(up_dir, exist_ok=True)
    os.makedirs(tmp_dir, exist_ok=True)
    return up_dir, tmp_dir

def _safe_name(name: str) -> str:
    return secure_filename(name or "unnamed")

@bp.route("/init", methods=["POST"])
@login_required
def upload_init():
    """
    Body (JSON): { filename, total_size, checksum? }
    Trả về: { upload_id }
    """
    data = request.get_json(silent=True) or {}
    filename = _safe_name(data.get("filename", "unnamed"))
    total_size = int(data.get("total_size") or 0)
    checksum = data.get("checksum")  # optional (md5/sha1 tự do, không ép)
    project_id = data.get("project_id") # <-- Lấy project_id

    up_dir, tmp_dir = _ensure_dirs()

    # Tạo upload_id đơn giản dựa trên thời gian + tên
    base_id = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{filename}"
    upload_id = hashlib.sha1(base_id.encode("utf-8")).hexdigest()

    meta = {
        "filename": filename,
        "total_size": total_size,
        "received": 0,
        "checksum": checksum,
        "project_id": project_id
    }

    with open(os.path.join(tmp_dir, f"{upload_id}.meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f)

    # Tạo file .part rỗng
    open(os.path.join(tmp_dir, f"{upload_id}.part"), "ab").close()

    return jsonify({"success": True, "upload_id": upload_id})

@bp.route("/chunk", methods=["POST"])
@login_required
def upload_chunk():
    """
    FormData: upload_id, index, chunk (binary)
    """
    upload_id = request.form.get("upload_id")
    index = request.form.get("index")
    chunk = request.files.get("chunk")

    if not upload_id or index is None or not chunk:
        return jsonify({"success": False, "message": "Missing index"}), 400

    _, tmp_dir = _ensure_dirs()

    meta_path = os.path.join(tmp_dir, f"{upload_id}.meta.json")
    part_path = os.path.join(tmp_dir, f"{upload_id}.part")

    if not os.path.exists(meta_path):
        return jsonify({"success": False, "message": "Upload timeout"}), 404

    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
    except Exception:
        return jsonify({"success": False, "message": "Cannot read meta."}), 500

    # Ghi nối tiếp
    try:
        data = chunk.read()
        with open(part_path, "ab") as pf:
            pf.write(data)
        meta["received"] = int(meta.get("received", 0)) + len(data)
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f)
        return jsonify({"success": True, "received": meta["received"]})
    except Exception as e:
        return jsonify({"success": False, "message": f"Write chunk error: {e}"}), 500

@bp.route("/complete", methods=["POST"])
@login_required
def upload_complete():
    """
    Body (JSON): { upload_id }
    Ghép file: move .part -> uploads + tạo record UploadedFile
    """
    data = request.get_json(silent=True) or {}
    upload_id = data.get("upload_id")
    if not upload_id:
        return jsonify({"success": False, "message": "Miss upload id"}), 400

    up_dir, tmp_dir = _ensure_dirs()
    meta_path = os.path.join(tmp_dir, f"{upload_id}.meta.json")
    part_path = os.path.join(tmp_dir, f"{upload_id}.part")

    if not (os.path.exists(meta_path) and os.path.exists(part_path)):
        return jsonify({"success": False, "message": "Cannot find upload version"}), 404

    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        filename = _safe_name(meta["filename"])
        total_size = int(meta.get("total_size") or 0)
        project_id = meta.get("project_id")

        # Đổi tên part => file đích
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        saved_filename = f"{timestamp}_{filename}"
        final_path = os.path.join(up_dir, saved_filename)
        os.replace(part_path, final_path)  # move/rename

        file_size = os.path.getsize(final_path)
        _, file_ext = os.path.splitext(filename)

        # (Tuỳ chọn) kiểm tra tổng bytes khớp total_size
        if total_size and file_size != total_size:
            # Không xoá file vì có thể vẫn muốn giữ, chỉ cảnh báo
            warn = f"Size mismatch: received {file_size}, expected {total_size}"

        # Ghi DB
        new_file = UploadedFile(
            original_filename=filename,
            saved_filename=saved_filename,
            file_type=(file_ext.lower() or ""),
            file_size=file_size,
            uploader_id=current_user.id,
            upload_source='direct',
            project_id=project_id
        )
        db.session.add(new_file)
        db.session.commit()

        # Xoá meta
        try:
            os.remove(meta_path)
        except Exception:
            pass

        return jsonify({
            "success": True,
            "message": "Uploaded!",
            "file": {
                "id": new_file.id,
                "original_filename": new_file.original_filename,
                "url": url_for('main.uploaded_file', filename=new_file.saved_filename)
            }
        })
    except IntegrityError:
        db.session.rollback()
        return jsonify({"success": False, "message": "Error: File name existed"}), 409
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error when finish: {e}"}), 500
