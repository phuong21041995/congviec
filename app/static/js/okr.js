// ============================================================================
// OKR SCRIPT - PHIÊN BẢN SỬA LỖI CUỐI CÙNG
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
            
            const params = new URLSearchParams(window.location.search);
            const currentProjectId = params.get('project_id');
            const projectIdField = objectiveForm.querySelector('[name="project_id"]');
            if (currentProjectId && projectIdField) {
                projectIdField.value = currentProjectId;
            }
            objectiveModal.show();
        });
    }
    
    if (objectiveForm && objectiveModal) {
        objectiveForm.addEventListener('submit', function(event) {
            if (objectiveForm.action.includes('/update/')) {
                event.preventDefault();
                const url = objectiveForm.action;
                const formData = new FormData(objectiveForm);
                const payload = Object.fromEntries(formData.entries());

                fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                })
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        showToast?.('Success', 'Objective updated successfully!', 'success');
                        objectiveModal.hide();
                        setTimeout(() => location.reload(), 500);
                    } else {
                        showToast?.('Error', data.message || 'Failed to update Objective.', 'danger');
                    }
                });
            }
        });
    }

    if (addKrForm && krModal) {
        addKrForm.addEventListener('submit', function(event) {
            event.preventDefault(); 
            const payload = {
                objective_id: addKrForm.querySelector('#objectiveId').value,
                content: addKrForm.querySelector('#krContent').value.trim(),
                start_date: addKrForm.querySelector('#krStartDate').value,
                end_date: addKrForm.querySelector('#krEndDate').value,
                owner_id: addKrForm.querySelector('#krOwner').value,
                note: addKrForm.querySelector('#krNote').value.trim()
            };
            
            fetch(window.ADD_KEY_RESULT_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    showToast?.('Success', 'Key Result added successfully!', 'success');
                    krModal.hide();
                    setTimeout(() => location.reload(), 500);
                } else {
                    showToast?.('Error', data.message || 'Failed to add Key Result.', 'danger');
                }
            });
        });
    }

    if (editKrForm && krEditModal) {
        editKrForm.addEventListener('submit', function(event) {
            event.preventDefault();
            const krId = editKrForm.querySelector('#editKrId').value;
            const url = window.UPDATE_ITEM_URL_BASE + `key_result/${krId}`;
            const payload = {
                content: editKrForm.querySelector('#editKrContent').value.trim(),
                start_date: editKrForm.querySelector('#editKrStartDate').value,
                end_date: editKrForm.querySelector('#editKrEndDate').value,
                owner_id: editKrForm.querySelector('#editKrOwner').value,
                note: editKrForm.querySelector('#editKrNote').value.trim()
            };
            fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    showToast?.('Success', 'Key Result updated.', 'success');
                    krEditModal.hide();
                    setTimeout(() => location.reload(), 500);
                } else {
                    showToast?.('Error', data.message || 'Update failed.', 'danger');
                }
            });
        });
    }

    okrTabContent.addEventListener('click', function(event) {
        const target = event.target;
        const button = target.closest('button');
        if (!button) return;

        if (button.matches('.add-kr-btn')) {
            openKrModal(button.dataset.objId);
        }
        else if (button.matches('.edit-kr-btn')) {
            openEditKrModal(button.dataset.krId);
        }
        else if (button.matches('.edit-obj-btn')) {
            openEditObjectiveModal(button.dataset.objId);
        }
        else if (button.matches('.add-task-btn')) {
            const krId = button.dataset.krId;
            const today = new Date().toISOString().split('T')[0];
            const currentUserId = document.querySelector('main.project-main')?.dataset.currentUserId || '';
            
            // === SỬA LỖI CUỐI CÙNG: Đổi tên hàm thành openCreateModal ===
            if (window.openCreateModal) { 
                 window.openCreateModal({ 
                    key_result_id: krId, 
                    status: 'Pending', 
                    date: today, 
                    who_id: currentUserId 
                });
            } else {
                 console.error("Function to open task modal (window.openCreateModal) not found.");
                 showToast?.('Error', 'Cannot open task modal.', 'danger');
            }
        }
        else if (button.matches('.open-task-modal-btn')) {
             const taskId = button.closest('.action-item')?.dataset.taskId;
             if (taskId && window.openEditModal) {
                 fetch(`/api/task/${taskId}`).then(r => r.json()).then(data => {
                     if (data.success) window.openEditModal(data.task);
                 });
             }
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
                editKrForm.querySelector('#editKrOwner').value = kr.owner_id || '';
                editKrForm.querySelector('#editKrNote').value = kr.note || '';
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
                objectiveForm.querySelector('textarea[name="note"]').value = o.note || '';
                objectiveModal.show();
            } else {
                showToast?.('Error', 'Could not load Objective data.', 'danger');
            }
        } catch (error) {
            showToast?.('Error', 'Network error while fetching Objective.', 'danger');
        }
    }
});

