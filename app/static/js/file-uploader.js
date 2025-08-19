// static/js/file-uploader.js

/**
 * Hiển thị một thông báo Toast của Bootstrap.
 * @param {string} title Tiêu đề của thông báo.
 * @param {string} message Nội dung thông báo.
 * @param {string} type Loại thông báo ('success', 'danger', 'info').
 */
function showToast(title, message, type = 'info') {
    const toastEl = document.getElementById('appToast');
    if (!toastEl) return;

    const toastHeader = toastEl.querySelector('.toast-header');
    const toastTitle = toastEl.querySelector('#toastTitle');
    const toastBody = toastEl.querySelector('#toastBody');

    toastTitle.textContent = title;
    toastBody.textContent = message;

    // Reset classes
    toastHeader.classList.remove('bg-success', 'bg-danger', 'bg-info', 'text-white');
    
    // Add new class based on type
    if (type === 'success' || type === 'danger') {
        toastHeader.classList.add(`bg-${type}`, 'text-white');
    } else {
        toastHeader.classList.add('bg-light');
    }

    const toast = bootstrap.Toast.getOrCreateInstance(toastEl);
    toast.show();
}

// Biến toàn cục để lưu các file đang chờ upload khi tạo task mới
window.queuedFiles = [];

/**
 * Upload một file lên server và trả về promise.
 * @param {File} file Đối tượng file cần upload.
 * @param {string} uploadUrl URL của API endpoint.
 * @param {FormData} additionalData Dữ liệu form bổ sung (ví dụ: task_id).
 * @returns {Promise<any>}
 */
async function uploadFile(file, uploadUrl, additionalData = new FormData()) {
    const formData = additionalData;
    // Check if a file with the same name is already in the form data
    if (!formData.has('file')) {
        formData.append('file', file);
    }

    try {
        const response = await fetch(uploadUrl, {
            method: 'POST',
            body: formData,
        });
        const result = await response.json();
        // Nâng cấp: Tải lại trang sau khi upload thành công trên trang quản lý
        if (result.success && window.location.pathname.includes('/uploads-manager')) {
            showToast('Thành công', `Đã tải lên file: ${file.name}`, 'success');
            setTimeout(() => location.reload(), 1000);
        }
        return result;
    } catch (error) {
        console.error('Upload error:', error);
        return { success: false, message: `Lỗi mạng khi tải file: ${file.name}` };
    }
}


function createAttachmentElement(file, isQueueItem = false) {
    const item = document.createElement('div');
    item.className = 'attachment-item d-flex justify-content-between align-items-center p-1 border-bottom';
    if(file.id) item.dataset.fileId = file.id;

    const link = document.createElement('a');
    link.href = file.url || '#';
    link.textContent = isQueueItem ? `(Chờ lưu) ${file.name}` : file.original_filename;
    link.target = '_blank';
    item.appendChild(link);

    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.className = 'btn btn-sm btn-outline-danger ms-2';
    removeBtn.innerHTML = '<i class="fa-solid fa-times"></i>';
    
    if (isQueueItem) {
        removeBtn.onclick = () => {
            window.queuedFiles = window.queuedFiles.filter(f => f !== file);
            item.remove();
        };
    } else {
        removeBtn.onclick = async (e) => {
            e.preventDefault();
            if (confirm(`Bạn có chắc muốn xóa file "${file.original_filename}" không?`)) {
                try {
                    const res = await fetch(file.delete_url, { method: 'POST' });
                    const result = await res.json();
                    if (result.success) {
                        item.remove();
                        showToast('Thành công', 'Đã xóa file.', 'success');
                    } else { 
                        showToast('Lỗi', result.message, 'danger');
                    }
                } catch (err) { 
                    showToast('Lỗi mạng', err.message, 'danger');
                }
            }
        };
    }
    item.appendChild(removeBtn);
    return item;
}

/**
 * Xử lý các file được người dùng chọn
 * @param {FileList} files Danh sách file
 * @param {HTMLElement} dropZone Khu vực upload tương ứng
 */
function handleFiles(files, dropZone) {
    const parentIdField = document.getElementById(dropZone.dataset.parentIdField);
    const attachmentList = dropZone.closest('.card-body, .modal-body').querySelector('.attachment-list');
    
    // SỬA LỖI LOGIC: Kiểm tra xem có cần ID của đối tượng cha không
    const requiresParentId = dropZone.dataset.parentIdField.trim() !== '';
    const isCreatingParent = !parentIdField || !parentIdField.value;

    // Chỉ đưa vào hàng đợi KHI VÀ CHỈ KHI:
    // 1. Uploader này CẦN ID cha (ví dụ: modal tạo task)
    // 2. VÀ chúng ta đang ở chế độ TẠO MỚI (chưa có ID cha)
    const shouldQueue = requiresParentId && isCreatingParent;

    for (const file of files) {
        if (shouldQueue) {
            window.queuedFiles.push(file);
            attachmentList.appendChild(createAttachmentElement(file, true));
        } else {
            // Tải lên ngay lập tức trong các trường hợp còn lại (sửa task, trang quản lý file,...)
            const loadingEl = createAttachmentElement({ name: file.name }, true);
            loadingEl.textContent = `Đang tải lên: ${file.name}...`;
            attachmentList.appendChild(loadingEl);

            const fd = new FormData();
            if (parentIdField && parentIdField.value) {
                fd.append(dropZone.dataset.parentIdName, parentIdField.value);
            }
			if (window.location.pathname.includes('/uploads-manager')) {
				fd.append('source', 'direct');
			}

            uploadFile(file, dropZone.dataset.uploadUrl, fd).then(result => {
                loadingEl.remove();
                if (result.success) {
                    // Trên trang quản lý, không cần thêm file vào danh sách vì trang sẽ tự reload
                    if (!window.location.pathname.includes('/uploads-manager')) {
                       attachmentList.appendChild(createAttachmentElement(result.file));
                    }
                } else {
                    showToast('Lỗi Upload', result.message, 'danger');
                }
            });
        }
        attachmentList.style.display = 'block';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.file-drop-zone').forEach(dropZone => {
        const parentElement = dropZone.closest('.card-body, .modal-body');
        if (!parentElement) return;

        const fileInput = parentElement.querySelector('.file-input-trigger');
        const selectButton = parentElement.querySelector('button.file-select-button');

        dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('border-primary'); });
        dropZone.addEventListener('dragleave', () => dropZone.classList.remove('border-primary'));
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('border-primary');
            handleFiles(e.dataTransfer.files, dropZone);
        });
        dropZone.addEventListener('paste', (e) => {
            handleFiles(e.clipboardData.files, dropZone);
        });

        if (fileInput && selectButton) {
            selectButton.onclick = () => fileInput.click();
            fileInput.addEventListener('change', (e) => {
                handleFiles(e.target.files, dropZone);
                e.target.value = '';
            });
        }
    });
});