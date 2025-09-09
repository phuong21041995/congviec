// File: app/static/js/task-modal-handler.js

// This script handles the logic for the shared task creation/editing modal.

let taskModal;
let taskForm;

const SAVE_TASK_URL = window.SAVE_TASK_URL || '/save-task';
const DELETE_TASK_URL_BASE = window.DELETE_TASK_URL_BASE || '/delete-task/';
const DELETE_ATTACHMENT_URL_BASE = window.DELETE_ATTACHMENT_URL_BASE || '/delete-uploaded-file/';

document.addEventListener('DOMContentLoaded', function() {
    const taskModalEl = document.getElementById('taskModal');
    if (!taskModalEl) {
        console.error("Task modal element #taskModal not found!");
        return;
    }
    taskModal = new bootstrap.Modal(taskModalEl);
    taskForm = document.getElementById('taskForm');

    // Handle form submission
    taskForm.addEventListener('submit', function(event) {
        event.preventDefault();
        const formData = new FormData(taskForm);
        
        fetch(SAVE_TASK_URL, {
            method: 'POST',
            body: formData
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                showToast('Success', data.message || 'Task saved successfully!', 'success');
                taskModal.hide();
                setTimeout(() => window.location.reload(), 500);
            } else {
                showToast('Error', data.message || 'Failed to save task.', 'danger');
            }
        }).catch(err => {
            console.error('Save Task Error:', err);
            showToast('Error', 'An unexpected error occurred.', 'danger');
        });
    });

    // Handle delete button click
    const deleteBtn = document.getElementById('deleteTaskBtn');
    deleteBtn.addEventListener('click', function() {
        const taskId = document.getElementById('taskId').value;
        if (taskId && confirm('Are you sure you want to delete this task?')) {
            const url = DELETE_TASK_URL_BASE + taskId;
            fetch(url, { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    showToast('Success', data.message, 'success');
                    taskModal.hide();
                    setTimeout(() => window.location.reload(), 500);
                } else {
                    showToast('Error', data.message, 'danger');
                }
            });
        }
    });

    // --- Dependent dropdowns for OKR linking ---
    const projectSelect = document.getElementById('taskProject');
    const buildSelect = document.getElementById('taskBuild');
    const objectiveSelect = document.getElementById('taskObjective');
    const keyResultSelect = document.getElementById('taskKeyResult');

    async function fetchAndPopulate(selectElement, url, placeholder) {
        selectElement.innerHTML = `<option value="">${placeholder}</option>`;
        selectElement.disabled = true;
        if (!url) return;
        try {
            const res = await fetch(url);
            const data = await res.json();
            if (data.success) {
                data.items.forEach(item => {
                    const option = new Option(item.name, item.id);
                    selectElement.add(option);
                });
                selectElement.disabled = false;
            }
        } catch (error) {
            console.error('Failed to fetch dropdown data:', error);
        }
    }
    
    projectSelect?.addEventListener('change', async function() {
        const projectId = this.value;
        await fetchAndPopulate(buildSelect, projectId ? `/api/builds/${projectId}` : null, '--- Select Build ---');
        objectiveSelect.innerHTML = '<option value="">--- Select Objective ---</option>';
        keyResultSelect.innerHTML = '<option value="">--- Select Key Result ---</option>';
    });

    buildSelect?.addEventListener('change', async function() {
        const buildId = this.value;
        await fetchAndPopulate(objectiveSelect, buildId ? `/api/objectives/${buildId}` : null, '--- Select Objective ---');
        keyResultSelect.innerHTML = '<option value="">--- Select Key Result ---</option>';
    });

    objectiveSelect?.addEventListener('change', async function() {
        const objectiveId = this.value;
        await fetchAndPopulate(keyResultSelect, objectiveId ? `/api/key-results/${objectiveId}` : null, '--- Select Key Result ---');
    });
});

/**
 * Resets the task form to its default state.
 */
function resetTaskForm() {
    taskForm.reset();
    document.getElementById('taskId').value = '';
    document.getElementById('taskModalLabel').textContent = 'Create New Task';
    document.getElementById('deleteTaskBtn').style.display = 'none';
    document.getElementById('existing-attachments-list').innerHTML = ''; // Clear old attachments
    
    document.getElementById('taskBuild').innerHTML = '<option value="">--- Select Build ---</option>';
    document.getElementById('taskObjective').innerHTML = '<option value="">--- Select Objective ---</option>';
    document.getElementById('taskKeyResult').innerHTML = '<option value="">--- Select Key Result ---</option>';
}

/**
 * Helper function to pre-populate the entire OKR chain for a given Key Result ID.
 */
async function populateOkrChain(keyResultId) {
    if (!keyResultId) return;

    const projectSelect = document.getElementById('taskProject');
    const buildSelect = document.getElementById('taskBuild');
    const objectiveSelect = document.getElementById('taskObjective');
    const keyResultSelect = document.getElementById('taskKeyResult');

    try {
        const response = await fetch(`/api/kr-context/${keyResultId}`);
        const data = await response.json();

        if (data.success) {
            const { project_id, build_id, objective_id, key_result_id } = data.context;

            const waitForPopulate = (selectElement) => {
                return new Promise(resolve => {
                    if (selectElement.options.length > 1) return resolve();
                    const observer = new MutationObserver((_, obs) => {
                        if (selectElement.options.length > 1) { obs.disconnect(); resolve(); }
                    });
                    observer.observe(selectElement, { childList: true });
                });
            };

            projectSelect.value = project_id;
            projectSelect.dispatchEvent(new Event('change'));
            await waitForPopulate(buildSelect);

            buildSelect.value = build_id;
            buildSelect.dispatchEvent(new Event('change'));
            await waitForPopulate(objectiveSelect);

            objectiveSelect.value = objective_id;
            objectiveSelect.dispatchEvent(new Event('change'));
            await waitForPopulate(keyResultSelect);

            keyResultSelect.value = key_result_id;
        }
    } catch (error) {
        console.error("Failed to pre-populate OKR chain:", error);
        showToast('Error', 'Could not load OKR details for this task.', 'danger');
    }
}

/**
 * NEW - Renders the list of existing attachments.
 */
function renderAttachments(attachments = []) {
    const container = document.getElementById('existing-attachments-list');
    container.innerHTML = ''; // Clear previous list
    if (attachments.length === 0) {
        container.innerHTML = '<p class="text-muted small">No files attached.</p>';
        return;
    }
    
    const list = document.createElement('ul');
    list.className = 'list-unstyled';
    attachments.forEach(file => {
        const item = document.createElement('li');
        item.className = 'd-flex justify-content-between align-items-center mb-1';
        item.innerHTML = `
            <div>
                <i class="fa-solid fa-paperclip me-2"></i>
                <a href="${file.url}" target="_blank">${file.original_filename}</a>
            </div>
            <button type="button" class="btn btn-sm btn-outline-danger delete-attachment-btn" data-file-id="${file.id}">&times;</button>
        `;
        list.appendChild(item);
    });
    container.appendChild(list);

    // Add event listeners to new delete buttons
    container.querySelectorAll('.delete-attachment-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const fileId = this.dataset.fileId;
            if (confirm('Delete this attachment?')) {
                fetch(`${DELETE_ATTACHMENT_URL_BASE}${fileId}`, { method: 'POST' })
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        this.closest('li').remove(); // Remove from UI
                        showToast('Success', 'Attachment deleted!', 'success');
                    } else {
                        showToast('Error', data.message, 'danger');
                    }
                });
            }
        });
    });
}

/**
 * Opens the modal for creating a new task.
 */
window.openCreateModal = async function(initialData = {}) {
    resetTaskForm();
    document.getElementById('taskModalLabel').textContent = 'Create New Task';

    if (initialData.date) document.getElementById('taskDate').value = initialData.date;
    if (initialData.hour) document.getElementById('taskHour').value = initialData.hour;
    if (initialData.status) document.getElementById('taskStatus').value = initialData.status;

    await populateOkrChain(initialData.key_result_id);
    
    renderAttachments([]); // No attachments for new task

    taskModal.show();
};

/**
 * Opens the modal for editing an existing task.
 */
window.openEditModal = async function(taskData) {
    resetTaskForm();
    document.getElementById('taskModalLabel').textContent = 'Edit Task';
    document.getElementById('deleteTaskBtn').style.display = 'block';

    // Populate all form fields with task data
    document.getElementById('taskId').value = taskData.id || '';
    document.getElementById('taskWhat').value = taskData.what || '';
    
    // ===== FIX FOR DATE =====
    // Take only the YYYY-MM-DD part of the date string
    if (taskData.task_date) {
        document.getElementById('taskDate').value = taskData.task_date.split('T')[0];
    }
    
    document.getElementById('taskHour').value = taskData.hour || '';
    document.getElementById('taskWho').value = taskData.who_id || '';
    document.getElementById('taskStatus').value = taskData.status || 'Pending';
    document.getElementById('taskPriority').value = taskData.priority || 'Medium';
    document.getElementById('taskNote').value = taskData.note || '';

    // ===== NEW: RENDER ATTACHMENTS =====
    renderAttachments(taskData.attachments);
    
    // Pre-populate the OKR chain
    await populateOkrChain(taskData.key_result_id);

    taskModal.show();
};