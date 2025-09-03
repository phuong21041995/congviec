/**
 * calendar.js - PHIÊN BẢN HOÀN CHỈNH & CHUẨN XÁC
 * * - Giữ lại 100% các hàm và tính năng gốc (tạo, sửa, xóa, kéo thả, dropdown liên cấp...).
 * - Chỉ thay đổi duy nhất hành vi: Click vào một công việc có sẵn sẽ mở thẳng cửa sổ Sửa (Modal).
 * - Áp dụng cho cả Lịch (Calendar) và Bảng (Kanban).
 */
(function() {
    // --- 1. HELPERS & GLOBAL ELEMENTS (GIỮ NGUYÊN TỪ FILE GỐC CỦA BẠN) ---
    const bsModal = (id) => bootstrap.Modal.getOrCreateInstance(document.getElementById(id));
    const bsOffcanvas = (id) => bootstrap.Offcanvas.getOrCreateInstance(document.getElementById(id));
    const f = (id) => document.getElementById(id);

    // Shared Modals & Forms
    const taskModalEl = f('taskModal');
    const taskModal = taskModalEl ? bsModal('taskModal') : null;
    const form = f('taskForm');
    
    const detailOffcanvasEl = f('taskDetailOffcanvas');
    const detailOffcanvas = detailOffcanvasEl ? bsOffcanvas('taskDetailOffcanvas') : null;

    // Shared Form Inputs
    const inputRecurrence = f('taskRecurrence');
    const recurrenceWrapper = f('recurrence-end-date-wrapper');
    const attachmentListContainer = document.getElementById('existing-attachments-list');
    let lastCreatingCell = null;

    // A unified selector for task cards across all views
    const TASK_CARD_SELECTOR = '.timed-task-item, .kanban-card';

    // Global data for cascading dropdowns
    let allProjectsData = [];
    let allBuildsData = {};
    let allObjectivesData = {};
    let allKeyResultsData = {};

    // --- 2. CORE MODAL & DATA FUNCTIONS (GIỮ NGUYÊN TOÀN BỘ TÍNH NĂNG GỐC CỦA BẠN) ---
    
    function renderAttachments(attachments = []) {
        if (!attachmentListContainer) return;
        attachmentListContainer.innerHTML = ''; // Clear previous list

        if (attachments.length === 0) {
            attachmentListContainer.innerHTML = '<p class="text-muted small my-1">No files currently attached.</p>';
            return;
        }
        
        const listGroup = document.createElement('div');
        listGroup.className = 'list-group list-group-flush';

        attachments.forEach(file => {
            const fileEl = document.createElement('div');
            fileEl.className = 'list-group-item d-flex justify-content-between align-items-center px-0 py-1';
            fileEl.innerHTML = `
                <a href="${file.url}" target="_blank" class="text-decoration-none text-truncate" title="${file.original_filename}">
                    <i class="fa-solid fa-paperclip me-2 text-muted"></i>
                    ${file.original_filename}
                </a>
                <button type="button" class="btn btn-sm btn-outline-danger delete-attachment-btn" data-file-id="${file.id}" title="Delete this file">
                    <i class="fa-solid fa-trash-can"></i>
                </button>
            `;
            listGroup.appendChild(fileEl);
        });

        attachmentListContainer.appendChild(listGroup);

        attachmentListContainer.querySelectorAll('.delete-attachment-btn').forEach(btn => {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                const fileId = this.dataset.fileId;
                if (confirm('Are you sure you want to delete this attachment?')) {
                    fetch(`${window.DELETE_UPLOADED_FILE_URL_BASE}${fileId}`, { method: 'POST' })
                    .then(res => res.json())
                    .then(data => {
                        if (data.success) {
                            this.closest('.list-group-item').remove();
                        } else {
                            alert(data.message || 'Could not delete file');
                        }
                    });
                }
            });
        });
    }

    function fillFormFromTask(task = {}) {
        if (!form) return;
        form.reset();
        window.queuedFiles = [];

        f('taskId').value = task.id || '';
        f('taskWhat').value = task.what || '';
        f('taskDate').value = task.date || task.task_date || '';
        f('taskHour').value = task.hour ?? '';
        f('taskStatus').value = task.status || 'Pending';
        f('taskPriority').value = task.priority || 'Medium';
        f('taskNote').value = task.note || '';
        f('taskRecurrence').value = task.recurrence || 'none';
        f('taskRecurrenceEndDate').value = task.recurrence_end_date || '';
        f('taskWho').value = task.id ? (task.who_id || '') : (window.CURRENT_USER_ID || '');
        
        if (task.key_result_id) {
             const kr = allKeyResultsData[task.key_result_id];
             if (kr) {
                 const obj = allObjectivesData[kr.objective_id];
                 if (obj) {
                     const build = allBuildsData[obj.build_id];
                     if (build) {
                          f('taskProject').value = build.project_id || '';
                          loadBuilds(f('taskProject').value, obj.build_id);
                          loadObjectives(obj.build_id, obj.id);
                          loadKeyResults(obj.id, kr.id);
                     }
                 }
             }
        } else {
             f('taskProject').value = '';
             loadBuilds('', '');
             loadObjectives('', '');
             loadKeyResults('', '');
        }

        f('taskModalLabel').textContent = task.id ? 'Edit Task' : 'Create New Task';

        const deleteBtn = f('deleteTaskBtn');
        if (deleteBtn) {
            deleteBtn.style.display = task.id ? 'inline-block' : 'none';
            if (task.id) {
                deleteBtn.onclick = () => handleDeleteTask(task.id);
            }
        }
        
        renderAttachments(task.attachments);

        if (inputRecurrence) inputRecurrence.dispatchEvent(new Event('change'));
    }
    
    async function loadProjects() {
        // ... (Giữ nguyên toàn bộ các hàm loadProjects, loadBuilds, loadObjectives, loadKeyResults...)
        const res = await fetch('/api/projects');
        const data = await res.json();
        allProjectsData = data.projects;
        const select = f('taskProject');
        select.innerHTML = '<option value="">--- Select ---</option>';
        allProjectsData.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p.id;
            opt.textContent = p.name;
            select.appendChild(opt);
        });
    }

    function loadBuilds(projectId, selectedBuildId = '') {
        const select = f('taskBuild');
        select.innerHTML = '<option value="">--- Select ---</option>';
        const project = allProjectsData.find(p => p.id == projectId);
        if (project) {
            project.builds.forEach(b => {
                const opt = document.createElement('option');
                opt.value = b.id;
                opt.textContent = b.name;
                select.appendChild(opt);
                if (b.id == selectedBuildId) {
                    opt.selected = true;
                }
            });
        }
    }

    function loadObjectives(buildId, selectedObjectiveId = '') {
        const select = f('taskObjective');
        select.innerHTML = '<option value="">--- Select ---</option>';
        const objectives = Object.values(allObjectivesData).filter(o => o.build_id == buildId);
        if (objectives) {
            objectives.forEach(o => {
                const opt = document.createElement('option');
                opt.value = o.id;
                opt.textContent = o.content;
                select.appendChild(opt);
                if (o.id == selectedObjectiveId) {
                    opt.selected = true;
                }
            });
        }
    }

    function loadKeyResults(objectiveId, selectedKeyResultId = '') {
        const select = f('taskKeyResult');
        select.innerHTML = '<option value="">--- Select ---</option>';
        const objective = allObjectivesData[objectiveId];
        if (objective) {
            objective.key_results.forEach(kr => {
                const opt = document.createElement('option');
                opt.value = kr.id;
                opt.textContent = kr.content;
                select.appendChild(opt);
                if (kr.id == selectedKeyResultId) {
                    opt.selected = true;
                }
            });
        }
    }

    async function fetchAllOkrData() {
        const res = await fetch('/api/all-okr-data');
        const data = await res.json();
        allObjectivesData = data.objectives;
        allBuildsData = data.builds;
        allKeyResultsData = data.key_results;
    }

    async function handleDeleteTask(taskId) {
        if (!window.DELETE_TASK_URL_BASE || !taskId) return;
        if (!confirm('Are you sure you want to delete this task?')) return;
        try {
            const res = await fetch(window.DELETE_TASK_URL_BASE + taskId, { method: 'POST' });
            const data = await res.json();
            if (data.success) {
                location.reload();
            } else {
                alert(data.message || 'Deletion failed');
            }
        } catch (err) {
            alert('A connection error occurred.');
        }
    }
    
    // Hàm renderDetail vẫn được giữ lại để không làm ảnh hưởng đến các tính năng khác có thể đang dùng nó
    function renderDetail(task) {
        if (!detailOffcanvas) return;
        const root = f('taskDetailBody');
        if (!root) return;
        const renderAttachmentsHTML = (attachments = []) => {
            if (!attachments.length) return '<p class="text-muted small">No attached files.</p>';
            return attachments.map(file => `<a href="${file.url || '#'}" target="_blank" class="list-group-item list-group-item-action"><i class="fa-solid fa-paperclip me-2"></i>${file.original_filename}</a>`).join('');
        };
        const assignee = task.assignee ? task.assignee.username : (task.who || 'Not assigned');
        root.innerHTML = `<h4>${task.what || ''}</h4><p><span class="badge bg-primary">${task.status || 'N/A'}</span></p><hr><p><strong><i class="fa-solid fa-calendar-day me-2"></i>Date:</strong> ${task.date || task.task_date || 'N/A'}</p><p><strong><i class="fa-solid fa-clock me-2"></i>Time:</strong> ${task.hour != null && task.hour !== '' ? task.hour + ':00' : 'All day'}</p><p><strong><i class="fa-solid fa-user me-2"></i>Assignee:</strong> ${assignee}</p><h6><i class="fa-solid fa-note-sticky me-2"></i>Note:</h6><div class="p-2 bg-light border rounded mb-3" style="white-space: pre-wrap;">${task.note || 'None'}</div><h6><i class="fa-solid fa-paperclip me-2"></i>Attachments:</h6><div class="list-group list-group-flush">${renderAttachmentsHTML(task.attachments)}</div><div class="mt-4 d-flex gap-2"><button class="btn btn-primary" id="btnEditTaskFromDetail"><i class="fa-solid fa-pen-to-square me-1"></i>Edit</button><button class="btn btn-outline-danger" id="btnDeleteTaskFromDetail"><i class="fa-solid fa-trash-can me-1"></i>Delete</button></div>`;
        f('btnEditTaskFromDetail').onclick = () => { detailOffcanvas.hide(); openEditModal(task); };
        f('btnDeleteTaskFromDetail').onclick = () => handleDeleteTask(task.id);
        detailOffcanvas.show();
    }

    // Các hàm global để mở Modal (GIỮ NGUYÊN)
    window.openCreateModal = (defaults = {}) => {
        if (!taskModal) return;
        fillFormFromTask(defaults);
        taskModal.show();
    };
    window.openEditModal = (task) => {
        if (!taskModal) return;
        fillFormFromTask(task);
        taskModal.show();
    };

    // --- 3. MAIN INITIALIZATION & EVENT LISTENERS (PHẦN DUY NHẤT ĐƯỢC THAY ĐỔI) ---
    document.addEventListener('DOMContentLoaded', async () => {
        await fetchAllOkrData();
        await loadProjects();
        
        // **BỘ LẮNG NGHE SỰ KIỆN CLICK TẬP TRUNG (GLOBAL CLICK LISTENER)**
        // Bắt tất cả các click trên trang
        document.body.addEventListener('click', function(e) {
            // Kiểm tra xem có phải click vào một thẻ công việc không
            const taskCard = e.target.closest(TASK_CARD_SELECTOR);

            if (taskCard && taskCard.dataset.taskJson) {
                // Nếu đúng, ngăn các hành vi mặc định và sự lan truyền sự kiện
                e.preventDefault();
                e.stopPropagation();

                try {
                    const taskData = JSON.parse(taskCard.dataset.taskJson);
                    
                    // **===> THAY ĐỔI CHÍNH NẰM Ở ĐÂY <===**
                    // Gọi thẳng hàm openEditModal để mở cửa sổ Sửa
                    window.openEditModal(taskData);
                    
                } catch (err) {
                    console.error("JSON Parse Error:", err, taskCard.dataset.taskJson);
                    alert("Could not read task data.");
                }
                return; // Dừng xử lý tại đây
            }
            
            // Logic cho việc TẠO task mới khi click vào ô LỊCH TRỐNG
            // Logic này chỉ chạy nếu click không phải vào một taskCard đã có
            const calendarGridContainer = document.querySelector('.calendar-grid-container');
            if (calendarGridContainer && calendarGridContainer.contains(e.target)) {
                 const taskCell = e.target.closest('.task-cell, .allday-cell');
                 if (taskCell) {
                     if (lastCreatingCell) {
                         lastCreatingCell.classList.remove('cell-creating');
                     }
                     taskCell.classList.add('cell-creating');
                     lastCreatingCell = taskCell;
                     window.openCreateModal({
                         date: taskCell.dataset.date,
                         hour: taskCell.dataset.hour || ''
                     });
                 }
            }
        });
        
        // -- CÁC LOGIC KHÁC ĐƯỢC GIỮ NGUYÊN --
        
        // Logic submit form
        if (form) {
            form.addEventListener('submit', async (e) => {
                e.preventDefault();
                if (!form.checkValidity()) {
                    e.stopPropagation();
                    form.classList.add('was-validated');
                    return;
                }
                const formData = new FormData(form);
                if (window.queuedFiles && window.queuedFiles.length > 0) {
                    window.queuedFiles.forEach(file => {
                        formData.append('attachments[]', file);
                    });
                }
                try {
                    const response = await fetch(window.SAVE_TASK_URL, { method: 'POST', body: formData });
                    const data = await response.json();
                    if (data.success) {
                        location.reload();
                    } else {
                        alert(data.message || 'Failed to save task.');
                    }
                } catch (err) {
                    alert('A connection or data format error occurred.');
                }
            });
        }
        
        // Dropdown liên cấp
        const taskProjectSelect = f('taskProject');
        if(taskProjectSelect) {
            taskProjectSelect.addEventListener('change', (e) => loadBuilds(e.target.value));
        }
        const taskBuildSelect = f('taskBuild');
        if(taskBuildSelect) {
            taskBuildSelect.addEventListener('change', (e) => loadObjectives(e.target.value));
        }
        const taskObjectiveSelect = f('taskObjective');
        if(taskObjectiveSelect) {
            taskObjectiveSelect.addEventListener('change', (e) => loadKeyResults(e.target.value));
        }

        // Logic ẩn/hiện ngày lặp lại
        if (inputRecurrence && recurrenceWrapper) {
            inputRecurrence.addEventListener('change', () => {
                recurrenceWrapper.style.display = inputRecurrence.value === 'none' ? 'none' : 'block';
            });
        }

        // Kéo thả trên Lịch (Calendar)
        const calendarGridContainer = document.querySelector('.calendar-grid-container');
        if (calendarGridContainer) {
            calendarGridContainer.querySelectorAll('.task-cell, .allday-cell').forEach(container => {
                new Sortable(container, {
                    group: 'shared-tasks',
                    animation: 150,
                    ghostClass: 'sortable-ghost',
					onEnd: function(evt) {
						const taskId = evt.item.dataset.taskId;
						const newDate = evt.to.dataset.date;
						const newHour = evt.to.dataset.hour;
						fetch(window.UPDATE_TASK_TIME_URL, {
							method: 'POST',
							headers: { 'Content-Type': 'application/json' },
							body: JSON.stringify({ taskId: taskId, newDate: newDate, newHour: newHour === '' ? null : newHour })
						}).then(res => res.json()).then(data => {
							// --- THÊM LOGIC CẬP NHẬT Ở ĐÂY ---
							if (data.success && data.task) {
								// Cập nhật lại data-task-json của thẻ với dữ liệu mới từ server
								evt.item.dataset.taskJson = JSON.stringify(data.task);
							} else {
								// Nếu thất bại, trả thẻ về vị trí cũ
								alert('Could not move task: ' + data.message);
								evt.from.appendChild(evt.item);
							}
						});
					}
                });
            });
        }
        
        if (taskModalEl) {
            taskModalEl.addEventListener('hidden.bs.modal', () => {
                if (lastCreatingCell) {
                    lastCreatingCell.classList.remove('cell-creating');
                    lastCreatingCell = null;
                }
            });
        }

        // Kéo thả trên Bảng (Kanban)
        const kanbanBoardContainer = document.querySelector('.kanban-board-container');
        if (kanbanBoardContainer) {
            kanbanBoardContainer.querySelectorAll('.kanban-cards-container').forEach(column => {
                new Sortable(column, {
                    group: 'kanban-tasks',
                    animation: 150,
                    ghostClass: 'sortable-ghost',
					onEnd: function(evt) {
						const taskId = evt.item.dataset.taskId;
						const newStatus = evt.to.dataset.status;
						fetch(window.UPDATE_TASK_STATUS_URL, {
							method: 'POST',
							headers: { 'Content-Type': 'application/json' },
							body: JSON.stringify({ taskId, newStatus })
						}).then(res => res.json()).then(data => {
							// --- THÊM LOGIC CẬP NHẬT Ở ĐÂY ---
							if (data.success && data.task) {
								// Cập nhật lại data-task-json của thẻ với dữ liệu mới từ server
								evt.item.dataset.taskJson = JSON.stringify(data.task);
							} else {
								// Nếu thất bại, trả thẻ về vị trí cũ
								evt.from.appendChild(evt.item);
							}
						});
					}
                });
            });
        }
    });
})();