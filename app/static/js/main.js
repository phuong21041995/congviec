// calendar.js
// Logic cho trang Lịch Công Việc (index.html)

document.addEventListener('DOMContentLoaded', function() {
    // --- 1. KHAI BÁO BIẾN & KHỞI TẠO ---
    const taskModalEl = document.getElementById('taskModal');
    const taskModal = taskModalEl ? new bootstrap.Modal(taskModalEl) : null;
    const imagePreviewModalEl = document.getElementById('imagePreviewModal');
    const imagePreviewModal = imagePreviewModalEl ? new bootstrap.Modal(imagePreviewModalEl) : null;
    const taskForm = document.getElementById('taskForm');
    const calendarContainer = document.getElementById('drop-zone');
    const appToastEl = document.getElementById('appToast');
    const appToast = appToastEl ? new bootstrap.Toast(appToastEl) : null;
    let selectedCell = null;
    let draggedTaskCard = null;

    // --- 2. CÁC HÀM HỖ TRỢ & RENDER ---

    function showToast(title, body, className = 'bg-primary text-white') {
        if (!appToast) return;
        const toastHeader = appToastEl.querySelector('.toast-header');
        const toastTitle = appToastEl.querySelector('#toastTitle');
        const toastBody = appToastEl.querySelector('#toastBody');
        toastHeader.className = 'toast-header ' + className;
        toastTitle.textContent = title;
        toastBody.textContent = body;
        appToast.show();
    }
    
    function renderTaskCard(task) {
        const hasAttachments = task.attachments && task.attachments.length > 0;
        return `
            <div class="task-card status-${task.status.toLowerCase().replace(' ', '-')}" data-task-id="${task.id}" draggable="true">
                <div class="task-what"><strong>${task.what}</strong></div>
                <div class="task-who text-muted"><i class="fa-solid fa-user me-1"></i> ${task.who}</div>
                ${hasAttachments ? '<i class="fa-solid fa-paperclip attachment-icon"></i>' : ''}
            </div>
        `;
    }

    function renderAttachments(attachments) {
        const listEl = document.getElementById('attachment-list');
        if (!listEl) return;
        listEl.innerHTML = '';
        if (!attachments || attachments.length === 0) {
            listEl.innerHTML = '<p class="text-muted text-center small my-2">Chưa có file đính kèm.</p>';
            return;
        }
        attachments.forEach(att => {
            const itemEl = document.createElement('div');
            itemEl.className = 'attachment-item';
            itemEl.setAttribute('data-id', att.id);
            itemEl.innerHTML = `
                <a href="${att.url}" target="_blank" class="text-decoration-none text-truncate">
                    <i class="fa-solid fa-paperclip me-2"></i>${att.original_filename}
                </a>
                <button type="button" class="btn btn-sm btn-outline-danger delete-attachment-btn" title="Xóa file"><i class="fa-solid fa-times"></i></button>
            `;
            listEl.appendChild(itemEl);
        });
    }

    function updatePreview(task) {
        const previewContent = document.getElementById('preview-content');
        const previewPlaceholder = document.getElementById('preview-placeholder');
        if (!previewContent || !previewPlaceholder) return;
        
        if (task) {
            previewPlaceholder.classList.add('d-none');
            previewContent.classList.remove('d-none');
            
            let attachmentsHtml = '';
            let imagePreviewHtml = '';

            if (task.attachments && task.attachments.length > 0) {
                attachmentsHtml += '<ul class="list-group list-group-flush mt-1">';
                task.attachments.forEach(att => {
                    const isImage = /\.(jpe?g|png|gif|webp)$/i.test(att.original_filename);
                    attachmentsHtml += `<li class="list-group-item px-0"><a href="${att.url}" target="_blank">${att.original_filename}</a></li>`;
                    if (isImage && !imagePreviewHtml) {
                        imagePreviewHtml = `<img src="${att.url}" class="img-fluid rounded preview-thumbnail mt-2" alt="Xem trước" style="cursor:pointer;" data-fullscreen-src="${att.url}">`;
                    }
                });
                attachmentsHtml += '</ul>';
            } else {
                attachmentsHtml = '<small class="text-muted">Nothing</small>';
            }
            
            previewContent.innerHTML = `
                <h5 class="mb-3">${task.what}</h5>
                <p class="mb-1"><strong>PIC:</strong> ${task.who || 'N/A'}</p>
                <p class="mb-1"><strong>Status:</strong> <span class="badge bg-secondary">${task.status}</span></p>
                <hr>
                <div class="mb-2"><strong>Attached:</strong>${attachmentsHtml}</div>
                ${imagePreviewHtml}
                <hr>
                <p><strong>Ghi chú:</strong></p>
                <div class="note-content bg-light p-2 rounded small">${(task.note || '').replace(/\n/g, '<br>')}</div>
            `;
        } else {
            previewPlaceholder.classList.remove('d-none');
            previewContent.classList.add('d-none');
        }
    }

    function openTaskModal(date, hour, file = null) {
        if (!taskModal) return;
        taskForm.reset();
        document.getElementById('taskDate').value = date;
        document.getElementById('taskHour').value = hour;
        document.getElementById('attachment-list').innerHTML = ''; // Xóa list cũ
        
        const key = `${date}_${hour}`;
        const taskData = TASKS_DATA[key];
        const deleteBtn = document.getElementById('deleteTaskBtn');
        const recurrenceWrapper = document.getElementById('recurrence-end-date-wrapper');

        if (taskData) { // Chế độ Sửa
            document.getElementById('taskModalLabel').textContent = `Chỉnh sửa công việc`;
            document.getElementById('taskId').value = taskData.id;
            document.getElementById('taskWhat').value = taskData.what;
            document.getElementById('taskWho').value = taskData.who;
            document.getElementById('taskStatus').value = taskData.status;
            document.getElementById('taskNote').value = taskData.note;
            document.getElementById('taskRecurrence').value = taskData.recurrence || 'none';
            if (deleteBtn) deleteBtn.style.display = 'block';
            renderAttachments(taskData.attachments);
        } else { // Chế độ Tạo mới
            document.getElementById('taskModalLabel').textContent = `Add new event`;
            document.getElementById('taskId').value = '';
            document.getElementById('taskRecurrence').value = 'none';
            if (deleteBtn) deleteBtn.style.display = 'none';
            renderAttachments([]);
        }

        const recurrenceValue = taskData ? (taskData.recurrence || 'none') : 'none';
        recurrenceWrapper.style.display = (recurrenceValue === 'none') ? 'none' : 'block';
        if (recurrenceValue !== 'none') {
            document.getElementById('taskRecurrenceEndDate').value = taskData.recurrence_end_date || '';
        }

        if (file) {
            const dataTransfer = new DataTransfer();
            dataTransfer.items.add(file);
            document.getElementById('taskFiles').files = dataTransfer.files;
            showToast('Thông báo', `Đã đính kèm file: ${file.name}`);
        }
        taskModal.show();
    }
    
    function selectCell(cell) {
        if (selectedCell) selectedCell.classList.remove('cell-selected');
        cell.classList.add('cell-selected');
        selectedCell = cell;
        
        const key = `${cell.dataset.date}_${cell.dataset.hour}`;
        const task = TASKS_DATA[key];
        updatePreview(task);

        const editCreateBtn = document.getElementById('edit-create-btn');
        editCreateBtn.disabled = false;
        editCreateBtn.textContent = task ? 'Sửa / Chi tiết' : 'Tạo mới';
    }
    
    function updateCellContent(task) {
        const cell = document.querySelector(`.task-cell[data-date='${task.date}'][data-hour='${task.hour}']`);
        if (cell) {
            cell.innerHTML = renderTaskCard(task);
            selectCell(cell);
        } else {
             window.location.reload();
        }
    }

    // --- 3. CÁC TRÌNH XỬ LÝ SỰ KIỆN ---

    if (taskForm && taskModal) {
        taskForm.addEventListener('submit', function(event) {
            event.preventDefault();
            const formData = new FormData(this);
            fetch(SAVE_TASK_URL, { method: 'POST', body: formData })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    taskModal.hide();
                    showToast('Thành công', data.message, 'bg-success text-white');
                    
                    const updatedTask = data.task;
                    const oldKey = `${updatedTask.date}_${updatedTask.hour}`;
                    delete TASKS_DATA[oldKey];
                    TASKS_DATA[`${updatedTask.date}_${updatedTask.hour}`] = updatedTask;
                    
                    updateCellContent(updatedTask);

                } else {
                    showToast('Lỗi', data.message || "Lưu thất bại!", 'bg-danger text-white');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                showToast('Lỗi', 'Lỗi kết nối server.', 'bg-danger text-white');
            });
        });

        document.getElementById('deleteTaskBtn')?.addEventListener('click', function() {
            const taskId = document.getElementById('taskId').value;
            if (!taskId) return;
            if (confirm('Bạn có chắc chắn muốn xóa công việc này không?')) {
                fetch(`${DELETE_TASK_URL_BASE}${taskId}`, { method: 'POST' })
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        taskModal.hide();
                        showToast('Thành công', data.message, 'bg-success text-white');
                        const key = `${document.getElementById('taskDate').value}_${document.getElementById('taskHour').value}`;
                        delete TASKS_DATA[key];
                        if (selectedCell) {
                             selectedCell.innerHTML = '';
                             updatePreview(null);
                        }
                    } else {
                        showToast('Lỗi', 'Không thể xóa công việc.', 'bg-danger text-white');
                    }
                });
            }
        });

        document.getElementById('taskRecurrence')?.addEventListener('change', function() {
            document.getElementById('recurrence-end-date-wrapper').style.display = (this.value === 'none') ? 'none' : 'block';
        });

        document.getElementById('attachment-list').addEventListener('click', function(event){
            const deleteBtn = event.target.closest('.delete-attachment-btn');
            if (!deleteBtn) return;
            const itemEl = deleteBtn.closest('.attachment-item');
            const attachmentId = itemEl.dataset.id;
            if (confirm('Bạn có chắc muốn xóa file này?')) {
                fetch(`${DELETE_ATTACHMENT_URL_BASE}${attachmentId}`, { method: 'POST' })
                .then(res => res.json())
                .then(data => {
                     if (data.success) {
                        itemEl.remove();
                        const taskId = document.getElementById('taskId').value;
                        for (const key in TASKS_DATA) {
                            if (TASKS_DATA[key].id == taskId) {
                                TASKS_DATA[key].attachments = TASKS_DATA[key].attachments.filter(att => att.id != attachmentId);
                                updatePreview(TASKS_DATA[key]);
                                break;
                            }
                        }
                     } else {
                         alert('Xóa file thất bại');
                     }
                });
            }
        });
    }

    if (calendarContainer) {
        const editCreateBtn = document.getElementById('edit-create-btn');

        calendarContainer.addEventListener('click', function(event) {
            const cell = event.target.closest('.task-cell');
            if(cell && !event.target.closest('.task-card')) {
                 selectCell(cell);
            }
            const card = event.target.closest('.task-card');
            if(card) {
                selectCell(card.parentElement);
            }
        });

        editCreateBtn?.addEventListener('click', function() {
            if (selectedCell) { openTaskModal(selectedCell.dataset.date, selectedCell.dataset.hour); }
        });

        calendarContainer.addEventListener('dblclick', function(event) {
            const cell = event.target.closest('.task-cell');
            if (cell) openTaskModal(cell.dataset.date, cell.dataset.hour);
        });
        
        calendarContainer.addEventListener('dragover', (e) => {
            e.preventDefault();
            const cell = e.target.closest('.task-cell');
            if(cell) cell.style.backgroundColor = '#e9ecef';
        });
        calendarContainer.addEventListener('dragleave', (e) => {
             e.preventDefault();
            const cell = e.target.closest('.task-cell');
            if(cell) cell.style.backgroundColor = '';
        });
        
        // Kéo-thả CÔNG VIỆC
        calendarContainer.addEventListener('dragstart', e => {
             if (e.target.classList.contains('task-card')) {
                draggedTaskCard = e.target;
                setTimeout(() => e.target.style.display = 'none', 0);
            }
        });
        
        calendarContainer.addEventListener('dragend', e => {
            if(draggedTaskCard) {
                draggedTaskCard.style.display = 'block';
            }
            draggedTaskCard = null;
        });
        
        calendarContainer.addEventListener('drop', e => {
            e.preventDefault();
            
            // Xử lý kéo thả file
            if (e.dataTransfer.files.length > 0) {
                const cell = e.target.closest('.task-cell');
                if (cell) {
                     cell.style.backgroundColor = '';
                     openTaskModal(cell.dataset.date, cell.dataset.hour, e.dataTransfer.files[0]);
                }
                return;
            }

            // Xử lý kéo thả task
            if (!draggedTaskCard) return;

            const targetCell = e.target.closest('.task-cell');
            
            if (targetCell && !targetCell.querySelector('.task-card')) {
                const taskId = draggedTaskCard.dataset.taskId;
                const newDate = targetCell.dataset.date;
                const newHour = targetCell.dataset.hour;
                const oldCell = draggedTaskCard.parentElement;
                const oldKey = `${oldCell.dataset.date}_${oldCell.dataset.hour}`;

                fetch(UPDATE_TASK_TIME_URL, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ taskId, newDate, newHour })
                })
                .then(res => res.json())
                .then(data => { 
                    if (data.success) {
                        targetCell.appendChild(draggedTaskCard);
                        showToast('Thành công', data.message, 'bg-success text-white');

                        const taskData = TASKS_DATA[oldKey];
                        delete TASKS_DATA[oldKey];
                        taskData.date = newDate;
                        taskData.hour = parseInt(newHour);
                        TASKS_DATA[`${newDate}_${newHour}`] = taskData;
                        
                        updatePreview(taskData);
                        selectCell(targetCell);
                    } else { 
                        showToast('Lỗi', data.message, 'bg-danger text-white');
                        draggedTaskCard.style.display = 'block';
                    } 
                })
                .catch(error => {
                    console.error('Fetch error:', error);
                    showToast('Lỗi', 'Không thể kết nối tới máy chủ.', 'bg-danger text-white');
                    draggedTaskCard.style.display = 'block';
                });
            } else {
                 draggedTaskCard.style.display = 'block';
            }
        });

        // Click vào ảnh thumbnail để xem full
        document.getElementById('preview-pane').addEventListener('click', function(e){
            if(e.target.classList.contains('preview-thumbnail')){
                document.getElementById('fullscreen-image').src = e.target.dataset.fullscreenSrc;
                imagePreviewModal.show();
            }
        })
    }
});