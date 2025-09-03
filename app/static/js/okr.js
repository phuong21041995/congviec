// ============================================================================
// OKR SCRIPT - PHIÊN BẢN NÂNG CẤP
// ============================================================================

document.addEventListener('DOMContentLoaded', function () {
    // Chỉ thực thi code nếu đang ở đúng tab OKR
    const okrTabContent = document.getElementById('okr-tab-content');
    if (!okrTabContent) return;

    // --- Biến toàn cục cho các Modal và Form ---
    const objectiveModalEl = document.getElementById('addObjectiveModal');
    const krModalEl = document.getElementById('krModal');
    const krEditModalEl = document.getElementById('krEditModal');

    const objectiveModal = objectiveModalEl ? new bootstrap.Modal(objectiveModalEl) : null;
    const krModal = krModalEl ? new bootstrap.Modal(krModalEl) : null;
    const krEditModal = krEditModalEl ? new bootstrap.Modal(krEditModalEl) : null;
    
    const objectiveForm = document.getElementById('objectiveForm');
    const addKrForm = document.getElementById('addKrForm');
    const editKrForm = document.getElementById('editKrForm');

    // ========================================================
    // LOGIC CHO CÁC SỰ KIỆN CLICK VÀ SUBMIT
    // ========================================================

    // --- Logic nút "+ New Objective" ---
    const newObjectiveBtn = document.getElementById('addNewObjectiveBtn');
    if (newObjectiveBtn && objectiveModal && objectiveForm) {
        newObjectiveBtn.addEventListener('click', function() {
            objectiveForm.reset();
            objectiveForm.action = window.ADD_OBJECTIVE_URL;
            objectiveForm.querySelector('[name="objective_id"]').value = '';
            objectiveModalEl.querySelector('.modal-title').textContent = 'Add New Objective';
            
            // Tự động chọn project hiện tại
            const params = new URLSearchParams(window.location.search);
            const currentProjectId = params.get('project_id');
            const projectIdField = objectiveForm.querySelector('[name="project_id"]');
            if (currentProjectId && projectIdField) {
                projectIdField.value = currentProjectId;
            }
            objectiveModal.show();
        });
    }

    // --- Xử lý submit form THÊM MỚI Key Result (CẢI TIẾN) ---
    if (addKrForm && krModal) {
        addKrForm.addEventListener('submit', function(event) {
            event.preventDefault(); 

            const objectiveId = addKrForm.querySelector('#objectiveId').value;
            const content = addKrForm.querySelector('#krContent').value.trim();
            const startDate = addKrForm.querySelector('#krStartDate').value;
            const endDate = addKrForm.querySelector('#krEndDate').value;

            if (!content) {
                showToast?.('Warning', 'Key Result content cannot be empty.', 'warning');
                return;
            }
            
            const formData = { objective_id: objectiveId, content, start_date: startDate, end_date: endDate };

            fetch(window.ADD_KEY_RESULT_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formData)
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    showToast?.('Success', 'Key Result added successfully!', 'success');
                    krModal.hide();
                    // === THAY THẾ location.reload() ===
                    appendNewKrToDom(data.kr);
                } else {
                    showToast?.('Error', data.message || 'Failed to add Key Result.', 'danger');
                }
            })
            .catch(err => {
                console.error('Fetch error:', err);
                showToast?.('Error', 'A network error occurred.', 'danger');
            });
        });
    }

    // --- Xử lý submit form SỬA Key Result (CẢI TIẾN) ---
    if (editKrForm && krEditModal) {
        editKrForm.addEventListener('submit', function(event) {
            event.preventDefault();
            const krId = editKrForm.querySelector('#editKrId').value;
            const url = window.UPDATE_ITEM_URL_BASE + `key_result/${krId}`;
            
            const formData = {
                content: editKrForm.querySelector('#editKrContent').value.trim(),
                start_date: editKrForm.querySelector('#editKrStartDate').value,
                end_date: editKrForm.querySelector('#editKrEndDate').value
            };

            fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formData)
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    showToast?.('Success', 'Key Result updated.', 'success');
                    krEditModal.hide();
                    // === THAY THẾ location.reload() ===
                    updateKrInDom(krId, formData);
                } else {
                    showToast?.('Error', data.message || 'Update failed.', 'danger');
                }
            })
            .catch(err => {
                 console.error('Fetch error:', err);
                 showToast?.('Error', 'A network error occurred.', 'danger');
            });
        });
    }

    // --- Sử dụng Event Delegation để xử lý tất cả các click khác ---
    okrTabContent.addEventListener('click', function(event) {
        const target = event.target;
        const button = target.closest('button');

        // Mở modal Thêm KR
        if (button && button.matches('.add-kr-btn')) {
            openKrModal(button.dataset.objId);
        }
        // Mở modal Sửa KR
        else if (button && button.matches('.edit-kr-btn')) {
            openEditKrModal(button.dataset.krId);
        }
        // Mở modal Sửa Objective
        else if (button && button.matches('.edit-obj-btn')) {
            openEditObjectiveModal(button.dataset.objId);
        }
        // Mở modal Thêm Task
        else if (button && button.matches('.add-task-btn')) {
            const krId = button.dataset.krId;
            const today = new Date().toISOString().split('T')[0];
            if (window.openCreateModal) {
                window.openCreateModal({ key_result_id: krId, status: 'Pending', date: today });
            }
        }
        // Mở modal Sửa Task
        else if (button && button.matches('.open-task-modal-btn')) {
             const taskId = button.closest('.action-item')?.dataset.taskId;
             if (taskId && window.openEditModal) {
                 fetch(`/api/task/${taskId}`).then(r => r.json()).then(data => {
                     if (data.success) window.openEditModal(data.task);
                 });
             }
        }
        // Xử lý nút Xóa
        else if (button && button.matches('.delete-btn')) {
            if (!confirm('Are you sure you want to delete this item? This action cannot be undone.')) return;

            const itemType = button.dataset.type;
            const itemId = button.dataset.id;
            const url = window.DELETE_ITEM_URL_BASE + `${itemType}/${itemId}`;

            fetch(url, { method: 'POST' })
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        showToast?.('Success', `${itemType} has been deleted.`, 'success');
                        button.closest('.objective-block, .kr-block, .action-item').remove();
                        if (data.objective_id) updateObjectiveProgress(data.objective_id, data.obj_progress);
                    } else {
                        showToast?.('Error', data.message || `Failed to delete ${itemType}.`, 'danger');
                    }
                })
                .catch(() => showToast?.('Error', 'A network error occurred.', 'danger'));
        }
    });

    // ========================================================
    // CÁC HÀM HELPER
    // ========================================================

    function openKrModal(objectiveId) {
        if (!addKrForm || !krModal) return;
        addKrForm.reset();
        addKrForm.querySelector('#objectiveId').value = objectiveId;
        krModal.show();
    }

    async function openEditKrModal(krId) {
        try {
            const response = await fetch(`/api/key-result/${krId}`);
            const data = await response.json();
            if (data.success) {
                const kr = data.key_result;
                editKrForm.querySelector('#editKrId').value = kr.id;
                editKrForm.querySelector('#editKrContent').value = kr.content || '';
                editKrForm.querySelector('#editKrStartDate').value = kr.start_date || '';
                editKrForm.querySelector('#editKrEndDate').value = kr.end_date || '';
                krEditModal.show();
            } else {
                showToast?.('Error', 'Could not load Key Result data.', 'danger');
            }
        } catch (error) {
            showToast?.('Error', 'Network error while fetching Key Result.', 'danger');
        }
    }

    async function openEditObjectiveModal(objId) {
        try {
            const response = await fetch(`/api/objective/${objId}`);
            const data = await response.json();
            if (data.success) {
                const o = data.objective;
                objectiveModalEl.querySelector('.modal-title').textContent = 'Edit Objective';
                objectiveForm.action = window.UPDATE_ITEM_URL_BASE + `objective/${o.id}`;
                objectiveForm.querySelector('[name="objective_id"]').value = o.id;
                objectiveForm.querySelector('input[name="content"]').value = o.content;
                objectiveForm.querySelector('select[name="owner_id"]').value = o.owner_id || '';
                objectiveForm.querySelector('select[name="project_id"]').value = o.project_id || '';
                objectiveForm.querySelector('select[name="build_id"]').value = o.build_id || '';
                objectiveForm.querySelector('input[name="start_date_obj"]').value = o.start_date || '';
                objectiveForm.querySelector('input[name="end_date_obj"]').value = o.end_date || '';
                objectiveModal.show();
            } else {
                showToast?.('Error', 'Could not load Objective data.', 'danger');
            }
        } catch (error) {
            showToast?.('Error', 'Network error while fetching Objective.', 'danger');
        }
    }

    function updateObjectiveProgress(objectiveId, progress) {
        const objBlock = okrTabContent.querySelector(`.objective-block[data-obj-id="${objectiveId}"]`);
        if (objBlock) {
            const progressBar = objBlock.querySelector(`#obj-progress-bar-${objectiveId}`);
            const progressText = objBlock.querySelector(`#obj-progress-text-${objectiveId}`);
            if (progressBar) progressBar.style.width = `${progress}%`;
            if (progressText) progressText.textContent = `${Math.round(progress)}%`;
        }
    }

    function appendNewKrToDom(kr) {
        const objectiveContainer = document.querySelector(`.objective-block[data-obj-id="${kr.objective_id}"] .kr-container`);
        if (!objectiveContainer) return;
        
        const krCount = objectiveContainer.querySelectorAll('.kr-block').length + 1;

        const newKrHtml = `
            <div class="kr-block" data-kr-id="${kr.id}">
                <div class="d-flex align-items-center justify-content-between">
                    <div><i class="fa-solid fa-flag me-2 text-success"></i><span><strong>KR${krCount}: ${kr.content}</strong></span></div>
                    <div class="d-flex align-items-center">
                        <span class="badge bg-secondary me-2" id="kr-progress-text-${kr.id}">0/0</span>
                        <button class="btn btn-sm btn-outline-primary me-2 add-task-btn" data-kr-id="${kr.id}" title="Add Task"><i class="fa-solid fa-plus"></i></button>
                        <button class="btn btn-sm btn-outline-secondary me-2 edit-kr-btn" data-kr-id="${kr.id}" title="Edit Key Result"><i class="fa-solid fa-pen"></i></button>
                        <button class="btn btn-sm btn-outline-secondary delete-btn" data-type="key_result" data-id="${kr.id}" title="Delete Key Result"><i class="fa-solid fa-trash-can"></i></button>
                    </div>
                </div>
                <div class="progress mt-1" style="height: 5px;">
                    <div id="kr-progress-bar-${kr.id}" class="progress-bar" role="progressbar" style="width: 0%;"></div>
                </div>
                <div class="tasks-container mt-2"></div>
            </div>
        `;
        objectiveContainer.insertAdjacentHTML('beforeend', newKrHtml);
    }

    function updateKrInDom(krId, krData) {
        const krBlock = document.querySelector(`.kr-block[data-kr-id="${krId}"]`);
        if (krBlock) {
            const contentSpan = krBlock.querySelector('div > span');
            if (contentSpan) {
                const strongTag = contentSpan.querySelector('strong');
                strongTag.textContent = strongTag.textContent.split(':')[0] + ': ';
                contentSpan.append(krData.content);
            }
        }
    }
});