// okr.js
// Logic cho trang OKR (okr.html)

document.addEventListener('DOMContentLoaded', function() {
    const krModalElement = document.getElementById('krModal');
    const krModal = krModalElement ? new bootstrap.Modal(krModalElement) : null;
    const actionModalElement = document.getElementById('actionModal');
    const actionModal = actionModalElement ? new bootstrap.Modal(actionModalElement) : null;
    const mainColumn = document.getElementById('okr-main-column');

    function initTinyMCE() {
        tinymce.init({
            selector: 'textarea.tinymce-editor',
            license_key: 'gpl',
            plugins: 'autolink lists link image charmap preview anchor pagebreak',
            toolbar: 'undo redo | bold italic underline | alignleft aligncenter alignright | bullist numlist outdent indent | link image',
            menubar: false,
			height: 30,
            images_upload_url: UPLOAD_IMAGE_URL,
            automatic_uploads: true,
            file_picker_types: 'image',
        });
    }

    initTinyMCE();

    function showToast(title, body, className = 'bg-primary text-white') {
        const appToastEl = document.getElementById('appToast');
        if (!appToastEl) return;
        const appToast = new bootstrap.Toast(appToastEl);
        const toastHeader = appToastEl.querySelector('.toast-header');
        const toastTitle = appToastEl.querySelector('#toastTitle');
        const toastBody = appToastEl.querySelector('#toastBody');
        toastHeader.className = 'toast-header ' + className;
        toastTitle.textContent = title;
        toastBody.textContent = body;
        appToast.show();
    }

    function createActionElement(action) {
        const actionItem = document.createElement('div');
        actionItem.className = `action-item ${action.is_overdue ? 'overdue' : ''}`;
        actionItem.dataset.actionId = action.id;
        
        const actionContent = document.createElement('div');
        actionContent.className = 'action-content';
        actionContent.onclick = () => window.location.href = action.detail_url;

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'form-check-input me-3 action-checkbox';
        checkbox.dataset.id = action.id;
        if (action.status === 'Done') {
            checkbox.checked = true;
        }
        actionContent.appendChild(checkbox);

        const actionText = document.createElement('div');
        actionText.className = `action-text-container`;
        
        const actionTextContent = document.createElement('div');
        actionTextContent.className = `action-text ${action.status === 'Done' ? 'done' : ''}`;
        actionTextContent.id = `action-content-${action.id}`;
        actionTextContent.dataset.id = action.id;
        actionTextContent.innerHTML = action.content;
        actionTextContent.addEventListener('dblclick', function(e) {
            e.stopPropagation();
            e.preventDefault();
            editActionContent(this);
        });
        actionText.appendChild(actionTextContent);
        
        actionContent.appendChild(actionText);

        const actionMeta = document.createElement('div');
        actionMeta.className = 'action-meta';

        if (action.assignee_name) {
            const assigneeBadge = document.createElement('span');
            assigneeBadge.className = 'badge bg-info-subtle text-info-emphasis mb-1';
            assigneeBadge.textContent = action.assignee_name;
            actionMeta.appendChild(assigneeBadge);
        }

        if (action.due_date) {
            const dueDateBadge = document.createElement('span');
            dueDateBadge.className = 'badge bg-warning-subtle text-warning-emphasis mb-1 action-due-date';
            dueDateBadge.textContent = new Date(action.due_date).toLocaleDateString('vi-VN', { month: '2-digit', day: '2-digit' });
            actionMeta.appendChild(dueDateBadge);
        }

        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'delete-btn';
        deleteBtn.dataset.type = 'action_item';
        deleteBtn.dataset.id = action.id;
        deleteBtn.innerHTML = '<i class="fa-solid fa-trash-can"></i>';
        actionMeta.appendChild(deleteBtn);
        
        const detailBtn = document.createElement('button');
        detailBtn.className = 'btn btn-sm btn-outline-secondary ms-2';
        detailBtn.onclick = () => window.location.href = action.detail_url;
        detailBtn.innerHTML = '<i class="fa-solid fa-file-pen"></i>';
        actionMeta.appendChild(detailBtn);

        actionItem.appendChild(actionContent);
        actionItem.appendChild(actionMeta);

        return actionItem;
    }

    window.openKrModal = function(objectiveId) {
        if (krModal) {
            document.getElementById('objectiveId').value = objectiveId;
            document.getElementById('krContent').value = '';
            krModal.show();
        }
    }

    window.openActionModal = function(krId) {
        if (actionModal) {
            document.getElementById('actionModalKrId').value = krId;
            document.getElementById('actionContent').value = '';
            document.getElementById('actionAssignee').value = '';
            document.getElementById('actionDueDate').value = '';
            actionModal.show();
        }
    }

    function updateProgressUI(data) {
        if (data.objective_id) {
            const objProgressBar = document.getElementById(`obj-progress-bar-${data.objective_id}`);
            const objProgressText = document.getElementById(`obj-progress-text-${data.objective_id}`);
            if (objProgressBar) objProgressBar.style.width = `${data.obj_progress}%`;
            if (objProgressText) objProgressText.textContent = `${Math.round(data.obj_progress)}%`;
        }
        if (data.kr_id) {
            const krProgressBar = document.getElementById(`kr-progress-bar-${data.kr_id}`);
            const krProgressText = document.getElementById(`kr-progress-text-${data.kr_id}`);
            if (krProgressBar) krProgressBar.style.width = `${data.kr_progress}%`;
            if (krProgressText) krProgressText.textContent = `${Math.round(data.kr_current)}/${Math.round(data.kr_target)}`;
            if (data.kr_progress >= 100) {
                confetti({ particleCount: 100, spread: 70, origin: { y: 0.6 } });
            }
        }
    }

    if (!mainColumn) return;

    const addKrForm = document.getElementById('addKrForm');
    if (addKrForm) {
        addKrForm.addEventListener('submit', function(event) {
            event.preventDefault();
            const formData = new FormData(this);
            const data = Object.fromEntries(formData.entries());

            fetch(ADD_KEY_RESULT_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            })
            .then(res => res.json())
            .then(response => {
                if (response.success) {
                    krModal.hide();
                    showToast('success', 'Added New Key Result.', 'bg-success text-white');
                    window.location.reload();
                } else {
                    showToast('Error', response.message, 'bg-danger text-white');
                }
            })
            .catch(error => {
                showToast('Error', 'Error connect to server.', 'bg-danger text-white');
            });
        });
    }

    const addActionForm = document.getElementById('addActionForm');
    if (addActionForm) {
        addActionForm.addEventListener('submit', function(event) {
            event.preventDefault();
            const formData = new FormData(this);
            const krId = formData.get('key_result_id');
            
            fetch(ADD_ACTION_URL, {
                method: 'POST',
                body: formData
            })
            .then(res => res.json())
            .then(data => {
                if(data.success) {
                    showToast('Success', data.message, 'bg-success text-white');
                    actionModal.hide();
                    
                    const krBlock = document.querySelector(`.kr-block[data-kr-id='${krId}'] .actions-container`);
                    if (krBlock) {
                        const newActionElement = createActionElement(data.action);
                        krBlock.appendChild(newActionElement);
                    }
                    
                    updateProgressUI(data);

                } else {
                    showToast('Error', data.message, 'bg-danger text-white');
                }
            })
            .catch(error => {
                showToast('Error', 'Error connect to server.', 'bg-danger text-white');
            });
        });
    }

    mainColumn.addEventListener('click', function(event) {
        const deleteButton = event.target.closest('.delete-btn');
        if (deleteButton) {
            event.preventDefault();
            event.stopPropagation();
            
            const type = deleteButton.dataset.type;
            const id = deleteButton.dataset.id;
            
            if (confirm(`Are you sure to delete ${type.replace('_', ' ')} this one?`)) {
                handleDelete(type, id);
            }
        }

        const addActionButton = event.target.closest('.add-action-btn');
        if (addActionButton) {
            event.stopPropagation();
            const krId = addActionButton.dataset.krId;
            openActionModal(krId);
        }
    });
    
    // Hàm xử lý sửa nhanh Action
    window.editActionContent = function(target) {
        if (target.querySelector('input')) return;
        
        const actionId = target.dataset.id;
        const originalText = target.textContent.trim();
        
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'form-control form-control-sm';
        input.value = originalText;
        
        target.style.display = 'none';
        target.parentNode.insertBefore(input, target);
        input.focus();

        const saveChanges = () => {
            const newText = input.value.trim();
            input.remove();
            target.style.display = '';

            if (newText === '' || newText === originalText) return;

            fetch(`${UPDATE_ACTION_URL_BASE}${actionId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content: newText })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    target.innerHTML = data.action.content;
                    showToast('Success', 'Updated Action.', 'bg-success text-white');
                } else {
                    showToast('Error', data.message, 'bg-danger text-white');
                }
            })
            .catch(() => {
                showToast('Error', 'Error connect to server.', 'bg-danger text-white');
            });
        };
        
        input.addEventListener('blur', saveChanges);
        input.addEventListener('keydown', e => {
            if (e.key === 'Enter') {
                input.blur();
            }
            if (e.key === 'Escape') {
                input.remove();
                target.style.display = '';
            }
        });
    }

    mainColumn.addEventListener('dblclick', function(event) {
        const editableContent = event.target.closest('.editable-content');
        if (editableContent) handleEdit(editableContent);
    });

    mainColumn.addEventListener('change', function(event) {
        const checkbox = event.target.closest('.action-checkbox');
        if (checkbox) handleCheckboxChange(checkbox);
    });

    function handleEdit(target) {
        // ... (hàm cũ để sửa O và KR) ...
        if (target.querySelector('input')) return;
        const originalTextWithNumber = target.textContent.trim();
        const type = target.dataset.type;
        const id = target.dataset.id;
        const numberingMatch = originalTextWithNumber.match(/^([\w\d]+\.\s*)/);
        const numbering = numberingMatch ? numberingMatch[0] : '';
        const originalText = originalTextWithNumber.replace(numbering, '').trim();
        
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'form-control form-control-sm';
        input.value = originalText;

        const strongTag = target.querySelector('strong');
        const parentOfStrong = strongTag ? strongTag.parentNode : target;
        
        parentOfStrong.style.display = 'none';
        parentOfStrong.parentNode.insertBefore(input, parentOfStrong);
        input.focus();

        const saveChanges = () => {
            const newText = input.value.trim();
            input.remove();
            parentOfStrong.style.display = '';

            if (newText === '' || newText === originalText) return;
            
            fetch(`${UPDATE_ITEM_URL_BASE}${type}/${id}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content: newText })
            })
            .then(res => res.json())
            .then(data => {
                if(data.success) {
                     if (strongTag) {
                        strongTag.textContent = `${numbering}${data.new_content}`;
                     } else {
                        target.textContent = data.new_content;
                     }
                } else { showToast('Error', data.message, 'bg-danger text-white'); }
            })
            .catch(() => showToast('Error', 'Cannot connect to server.', 'bg-danger text-white'));
        };
        input.addEventListener('blur', saveChanges);
        input.addEventListener('keydown', e => {
            if (e.key === 'Enter') input.blur();
            if (e.key === 'Escape') {
                input.remove();
                parentOfStrong.style.display = '';
            }
        });
    }

    function handleDelete(type, id) {
        fetch(`${DELETE_ITEM_URL_BASE}${type}/${id}`, { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            if(data.success) {
                let elementToRemove;
                if (type === 'objective') elementToRemove = document.querySelector(`.objective-block[data-obj-id='${id}']`);
                else if (type === 'key_result') elementToRemove = document.querySelector(`.kr-block[data-kr-id='${id}']`);
                else if (type === 'action_item') elementToRemove = document.querySelector(`.action-item[data-action-id='${id}']`);
                
                if (elementToRemove) {
                    elementToRemove.style.opacity = '0';
                    setTimeout(() => elementToRemove.remove(), 300);
                }
                
                if (data.kr_id && data.objective_id) {
                     updateProgressUI(data);
                }
                showToast('Success', 'Deleted Success.', 'bg-success text-white');
            } else {
                showToast('Error', 'Cannot remove.', 'bg-danger text-white');
            }
        })
        .catch(() => showToast('Error', 'Cannot connect to server.', 'bg-danger text-white'));
    }

    function handleCheckboxChange(checkbox) {
        const actionId = checkbox.dataset.id;
        const isChecked = checkbox.checked;
        
        fetch(`${UPDATE_ACTION_STATUS_URL_BASE}${actionId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ checked: isChecked })
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                const actionText = document.getElementById(`action-content-${actionId}`);
                actionText.classList.toggle('done', isChecked);
                updateProgressUI(data);
            } else {
                showToast('Error', 'Error happend, Cannot update.', 'bg-danger text-white');
                checkbox.checked = !isChecked;
            }
        })
        .catch(() => {
            showToast('Error', 'Cannot connect to server.', 'bg-danger text-white');
            checkbox.checked = !isChecked;
        });
    }

    document.querySelectorAll('.kr-container').forEach(collapseEl => {
        const header = collapseEl.previousElementSibling;
        if(header) {
            collapseEl.addEventListener('show.bs.collapse', () => header.classList.remove('collapsed'));
            collapseEl.addEventListener('hide.bs.collapse', () => header.classList.add('collapsed'));
        }
    });
});