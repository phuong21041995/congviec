/**
 * calendar.js - Unified Logic for Calendar and Kanban Views
 * This script handles task creation, editing, deletion, and drag-and-drop
 * for both the calendar grid and the kanban board.
 */
(function() {
    // --- 1. HELPERS & GLOBAL ELEMENTS ---
    const bsModal = (id) => bootstrap.Modal.getOrCreateInstance(document.getElementById(id));
    const bsOffcanvas = (id) => bootstrap.Offcanvas.getOrCreateInstance(document.getElementById(id));
    const f = (id) => document.getElementById(id);

    // Shared Modals & Forms
    const taskModal = bsModal('taskModal');
    const detailOffcanvas = bsOffcanvas('taskDetailOffcanvas');
    const form = f('taskForm');

    // Shared Form Inputs
    const inputTaskId = f('taskId');
    const inputRecurrence = f('taskRecurrence');
    const recurrenceWrapper = f('recurrence-end-date-wrapper');
    const attachmentListContainer = document.getElementById('existing-attachments-list');
	

    // A unified selector for task cards across all views
    const TASK_CARD_SELECTOR = '.timed-task-item, .kanban-card';
	let lastCreatingCell = null;

    // --- 2. CORE MODAL & DATA FUNCTIONS (Shared Logic) ---

    /**
     * Fills the task form with data from a task object.
     * Resets the form if no task object is provided.
     * @param {object} task - The task data object.
     */
    function fillFormFromTask(task = {}) {
        form.reset();
        window.queuedFiles = []; // Reset any pending file uploads

        f('taskId').value = task.id || '';
        f('taskWhat').value = task.what || '';
        f('taskDate').value = task.date || task.task_date || ''; // Handle both date formats
        f('taskHour').value = task.hour ?? '';
        f('taskStatus').value = task.status || 'Pending';
        f('taskNote').value = task.note || '';
        f('taskRecurrence').value = task.recurrence || 'none';
        f('taskRecurrenceEndDate').value = task.recurrence_end_date || '';
        f('taskWho').value = task.id ? (task.who_id || '') : (window.CURRENT_USER_ID || '');

        f('taskModalLabel').textContent = task.id ? 'Edit Task' : 'Create New Task';

        const deleteBtn = f('deleteTaskBtn');
        deleteBtn.style.display = task.id ? 'inline-block' : 'none';
        deleteBtn.onclick = () => handleDeleteTask(task.id);

        // Populate existing attachments
        if (attachmentListContainer) {
            attachmentListContainer.innerHTML = '';
            if (task.attachments && task.attachments.length > 0) {
                task.attachments.forEach(file => {
                    // Create a standardized attachment element (you might need a global function for this)
                    const fileEl = document.createElement('div');
                    fileEl.innerHTML = `<a href="${file.url || '#'}" target="_blank">${file.original_filename}</a>`;
                    attachmentListContainer.appendChild(fileEl);
                });
                attachmentListContainer.style.display = 'block';
            } else {
                attachmentListContainer.style.display = 'none';
            }
        }


        if (inputRecurrence) inputRecurrence.dispatchEvent(new Event('change'));
    }

    /**
     * Handles the task deletion process.
     * @param {number} taskId - The ID of the task to delete.
     */
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
            console.error('Connection error during task deletion:', err);
            alert('A connection error occurred.');
        }
    }

    /**
     * Renders the task details in the offcanvas.
     * @param {object} task - The task data object.
     */
    function renderDetail(task) {
        const root = f('taskDetailBody');
        if (!root) return;

        const renderAttachmentsHTML = (attachments = []) => {
            if (!attachments.length) return '<p class="text-muted small">No attached files.</p>';
            return attachments.map(file => `
                <a href="${file.url || '#'}" target="_blank" class="list-group-item list-group-item-action">
                    <i class="fa-solid fa-paperclip me-2"></i>${file.original_filename}
                </a>`).join('');
        };

		const assignee = task.assignee ? task.assignee.username : (task.who || 'Not assigned');

        root.innerHTML = `
            <h4>${task.what || ''}</h4>
            <p><span class="badge bg-primary">${task.status || 'N/A'}</span></p>
            <hr>
            <p><strong><i class="fa-solid fa-calendar-day me-2"></i>Date:</strong> ${task.date || task.task_date || 'N/A'}</p>
            <p><strong><i class="fa-solid fa-clock me-2"></i>Time:</strong> ${task.hour != null && task.hour !== '' ? task.hour + ':00' : 'All day'}</p>
            <p><strong><i class="fa-solid fa-user me-2"></i>Assignee:</strong> ${assignee}</p>
            <h6><i class="fa-solid fa-note-sticky me-2"></i>Note:</h6>
            <div class="p-2 bg-light border rounded mb-3" style="white-space: pre-wrap;">${task.note || 'None'}</div>
            <h6><i class="fa-solid fa-paperclip me-2"></i>Attachments:</h6>
            <div class="list-group list-group-flush">${renderAttachmentsHTML(task.attachments)}</div>
            <div class="mt-4 d-flex gap-2">
                <button class="btn btn-primary" id="btnEditTaskFromDetail"><i class="fa-solid fa-pen-to-square me-1"></i>Edit</button>
                <button class="btn btn-outline-danger" id="btnDeleteTaskFromDetail"><i class="fa-solid fa-trash-can me-1"></i>Delete</button>
            </div>`;

        f('btnEditTaskFromDetail').onclick = () => { detailOffcanvas.hide(); openEditModal(task); };
        f('btnDeleteTaskFromDetail').onclick = () => handleDeleteTask(task.id);
    }

    // Publicly expose modal opening functions
    window.openCreateModal = (defaults = {}) => {
        fillFormFromTask(defaults);
        taskModal.show();
    };
    window.openEditModal = (task) => {
        fillFormFromTask(task);
        taskModal.show();
    };


    // --- 3. MAIN INITIALIZATION ---
    document.addEventListener('DOMContentLoaded', () => {

        // --- SHARED EVENT LISTENERS ---

        // Attach click listener to all task cards (from any view) to open detail panel
        document.body.addEventListener('click', function(e) {
            const taskCard = e.target.closest(TASK_CARD_SELECTOR);
            if (taskCard) {
                try {
                    const taskData = JSON.parse(taskCard.dataset.taskJson);
                    renderDetail(taskData);
                    detailOffcanvas.show();
                } catch (err) {
                    console.error("Error parsing task JSON for detail view:", err);
                }
            }
        });

        // Handle the main task form submission
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            if (!form.checkValidity()) {
                e.stopPropagation();
                form.classList.add('was-validated');
                return;
            }
            const fd = new FormData(form);
            try {
                const res = await fetch(window.SAVE_TASK_URL, { method: 'POST', body: fd });
                const data = await res.json();
                if (data.success) {
                    // Handle file uploads for new tasks if needed
                    location.reload();
                } else {
                    alert(data.message || 'Failed to save task.');
                }
            } catch (err) {
                 console.error('Connection error during task save:', err);
                 alert('A connection error occurred.');
            }
        });

        // Toggle recurrence end date visibility
        if (inputRecurrence && recurrenceWrapper) {
            inputRecurrence.addEventListener('change', () => {
                recurrenceWrapper.style.display = inputRecurrence.value === 'none' ? 'none' : 'block';
            });
        }


        // --- PAGE-SPECIFIC INITIALIZATIONS ---

        // ** A. CALENDAR VIEW LOGIC **
        const calendarGridContainer = document.querySelector('.calendar-grid-container');
        if (calendarGridContainer) {
            // A1. Enable creating tasks by clicking on empty cells
            calendarGridContainer.querySelectorAll('.task-cell, .allday-cell').forEach(cell => {
                cell.addEventListener('click', (e) => {
                    // Only trigger if clicking on the cell itself, not a task card inside it
                    if (e.target.closest(TASK_CARD_SELECTOR)) return;
					// Xóa highlight ở ô cũ nếu có
					if (lastCreatingCell) {
						lastCreatingCell.classList.remove('cell-creating');
					}

					// Highlight ô hiện tại và lưu lại
					const currentCell = e.currentTarget;
					currentCell.classList.add('cell-creating');
					lastCreatingCell = currentCell;
                    window.openCreateModal({ date: cell.dataset.date, hour: cell.dataset.hour || '' });
                });
            });

            // A2. Initialize SortableJS for changing task date/time
            calendarGridContainer.querySelectorAll('.task-cell, .allday-cell').forEach(container => {
                new Sortable(container, {
                    group: 'shared-tasks',
                    animation: 150,
					ghostClass: 'sortable-ghost',
                    onEnd: function(evt) {
                        const taskId = evt.item.dataset.taskId;
                        const newDate = evt.to.dataset.date;
                        const newHour = evt.to.dataset.hour; // Can be undefined for all-day

                        fetch(window.UPDATE_TASK_TIME_URL, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                taskId: taskId,
                                newDate: newDate,
                                newHour: newHour === '' ? null : newHour
                            })
                        })
                        .then(res => res.json())
                        .then(data => {
                            if (!data.success) {
                                alert('Could not move task: ' + data.message);
                                evt.from.appendChild(evt.item); // Revert on failure
                            }
                        })
                        .catch(err => {
                             console.error('Connection error during task time update:', err);
                             evt.from.appendChild(evt.item); // Revert on failure
                        });
                    }
                });
            });
        }
        // DỌN DẸP HIGHLIGHT KHI MODAL TẠO TASK BỊ ĐÓNG
        document.getElementById('taskModal').addEventListener('hidden.bs.modal', () => {
            if (lastCreatingCell) {
                lastCreatingCell.classList.remove('cell-creating');
                lastCreatingCell = null;
            }
        });

        // ** B. KANBAN VIEW LOGIC **
        const kanbanBoardContainer = document.querySelector('.kanban-board-container');
        if (kanbanBoardContainer) {
            // B1. Enable "Add Task" button
            const addTaskBtn = document.getElementById('add-task-btn');
            if (addTaskBtn) {
                addTaskBtn.addEventListener('click', function() {
                    const today = new Date().toISOString().split('T')[0];
                    window.openCreateModal({ date: today, status: 'Pending' });
                });
            }

            // B2. Initialize SortableJS for changing task status
            kanbanBoardContainer.querySelectorAll('.kanban-cards-container').forEach(column => {
                new Sortable(column, {
                    group: 'kanban-tasks',
                    animation: 150,
                    ghostClass: 'sortable-ghost',
                    onEnd: function(evt) {
                        const taskId = evt.item.dataset.taskId;
                        const newStatus = evt.to.dataset.status;
                        const updateUrl = kanbanBoardContainer.dataset.updateUrl;

                        fetch(updateUrl, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ taskId, newStatus })
                        })
                        .then(res => res.json())
                        .then(data => {
                            if (!data.success) {
                                console.error("Failed to update task status.");
                                evt.from.appendChild(evt.item); // Revert on failure
                            }
                        });
                    }
                });
            });
        }
    });
})();