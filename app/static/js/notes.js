document.addEventListener('DOMContentLoaded', function() {
    // --- KHỞI TẠO CÁC BIẾN VÀ MODAL ---
    const board = document.querySelector('.padlet-board');
    const createNoteModalEl = document.getElementById('createNoteModal');
    const editNoteModalEl = document.getElementById('editNoteModal');
    const createNoteModal = new bootstrap.Modal(createNoteModalEl);
    const editNoteModal = new bootstrap.Modal(editNoteModalEl);
    const createColumnModal = document.getElementById('createColumnModal') ? new bootstrap.Modal(document.getElementById('createColumnModal')) : null;

    // --- KHỞI TẠO TINYMCE ---
	function initTinyMCE(selector, content = '') {
		// Xóa instance cũ nếu có để tránh xung đột
		if (tinymce.get(selector.substring(1))) {
			tinymce.remove(selector);
		}
		
		tinymce.init({
			selector: selector,
			license_key: 'gpl',

			// --- Lấy từ cấu hình của bạn ---
			base_url: '/static/vendor/tinymce', // Giả định đường dẫn, bạn có thể cần sửa lại cho đúng
			suffix: '.min',
			plugins: 'autolink lists link image charmap preview anchor searchreplace visualblocks code fullscreen table help wordcount',
			toolbar: 'undo redo | formatselect | bold italic underline | alignleft aligncenter alignright | bullist numlist | link image | table | code | fullscreen | preview',
			promotion: false, // Ẩn banner quảng cáo
			// ---------------------------------
			
			// --- Giữ lại các tùy chọn cần thiết cho Ghi chú ---
			menubar: false,
			height: 300,
			paste_data_images: true,
			automatic_uploads: true,
			images_upload_url: UPLOAD_IMAGE_URL, 
			// ---------------------------------

			// *** DÒNG QUAN TRỌNG NHẤT ĐỂ SỬA LỖI LỒNG THẺ ***
			forced_root_block: 'div',

			// Setup nội dung ban đầu
			setup: (editor) => {
				editor.on('init', () => {
					if (content) {
						editor.setContent(content);
					}
				});
			}
		});
	}
    createNoteModalEl.addEventListener('shown.bs.modal', () => initTinyMCE('#createNoteContent'));
    createNoteModalEl.addEventListener('hidden.bs.modal', () => tinymce.remove('#createNoteContent'));
    editNoteModalEl.addEventListener('shown.bs.modal', (event) => {
        const noteContent = event.currentTarget.dataset.noteContent || '';
        initTinyMCE('#editNoteContent', noteContent);
    });
    editNoteModalEl.addEventListener('hidden.bs.modal', () => tinymce.remove('#editNoteContent'));

    // --- CÁC HÀM XỬ LÝ SỰ KIỆN ---
    const handleEditClick = (target) => {
        const noteId = target.dataset.noteId;
        const url = GET_NOTE_URL.replace('/0', '/' + noteId);
        fetch(url)
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    const note = data.note;
                    const form = document.getElementById('editNoteForm');
                    form.action = UPDATE_NOTE_URL.replace('/0', '/' + note.id);
                    
                    document.getElementById('editNoteId').value = note.id;
                    document.getElementById('editNoteTitle').value = note.title;
                    document.getElementById('editNoteColumn').value = note.column_id;
                    editNoteModalEl.dataset.noteContent = note.content;

                    const attachmentList = document.getElementById('edit-note-attachment-list');
                    attachmentList.innerHTML = '';
                    if (note.attachments && note.attachments.length > 0) {
                        const ul = document.createElement('ul');
                        ul.className = 'list-group';
                        note.attachments.forEach(att => {
                            const li = document.createElement('li');
                            li.className = 'list-group-item d-flex justify-content-between align-items-center';
                            li.innerHTML = `
                                <a href="${att.url}" target="_blank">${att.original_filename}</a>
                                <button type="button" class="btn btn-sm btn-outline-danger delete-attachment-btn" data-file-id="${att.id}">Xóa</button>
                            `;
                            ul.appendChild(li);
                        });
                        attachmentList.appendChild(ul);
                    } else {
                        attachmentList.innerHTML = '<p class="text-muted">Chưa có file nào.</p>';
                    }
                    editNoteModal.show();
                } else {
                    alert(data.message);
                }
            });
    };

    const handleDeleteClick = (target) => {
        const noteId = target.dataset.noteId;
        if (confirm('Bạn có chắc chắn muốn xóa ghi chú này không?')) {
            const url = DELETE_NOTE_URL.replace('/0', '/' + noteId);
            fetch(url, { method: 'DELETE' })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        target.closest('.note-card').remove();
                    } else {
                        alert(data.message);
                    }
                });
        }
    };
	
    const handleDeleteColumnClick = (target) => {
        const columnDiv = target.closest('.padlet-column');
        const columnId = columnDiv.dataset.columnId;
        const columnName = columnDiv.dataset.columnName;

        if (confirm(`Bạn có chắc chắn muốn xóa cột "${columnName}" không? Mọi ghi chú trong cột này cũng sẽ bị xóa vĩnh viễn.`)) {
            const url = DELETE_COLUMN_URL.replace('/0', '/' + columnId);
            fetch(url, { method: 'DELETE' })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    columnDiv.remove();
                } else {
                    alert(data.message);
                }
            });
        }
    };

    // --- GẮN SỰ KIỆN (EVENT LISTENERS) ---
    
    // Sử dụng Event Delegation để xử lý click cho các nút trên toàn board
    board.addEventListener('click', function(e) {
        const editBtn = e.target.closest('.edit-note-btn');
        const deleteBtn = e.target.closest('.delete-note-btn');
        const deleteColumnBtn = e.target.closest('.delete-column-btn');

        if (editBtn) handleEditClick(editBtn);
        if (deleteBtn) handleDeleteClick(deleteBtn);
        if (deleteColumnBtn) handleDeleteColumnClick(deleteColumnBtn);
    });

    // 1. Form Tạo ghi chú mới
    document.getElementById('createNoteForm').addEventListener('submit', function(e) {
        e.preventDefault();
        const form = e.target;
        const formData = new FormData(form);
        formData.set('content', tinymce.get('createNoteContent').getContent());

        fetch(form.action, { method: 'POST', body: formData })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    alert(data.message);
                    window.location.reload();
                } else {
                    alert(data.message || 'Không thể tạo ghi chú.');
                }
            });
    });

    // 2. Form Chỉnh sửa ghi chú
    document.getElementById('editNoteForm').addEventListener('submit', function(e) {
        e.preventDefault();
        const form = e.target;
        const formData = new FormData(form);
        formData.set('content', tinymce.get('editNoteContent').getContent());
        
        fetch(form.action, { method: 'POST', body: formData })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    alert(data.message);
                    window.location.reload();
                } else {
                    alert(data.message || 'Lỗi khi cập nhật.');
                }
            });
    });

    // 3. Form Tạo cột mới
    if (document.getElementById('createColumnForm')) {
        document.getElementById('createColumnForm').addEventListener('submit', function(e) {
            e.preventDefault();
            const columnName = document.getElementById('createColumnName').value;
            fetch(CREATE_COLUMN_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: columnName })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    window.location.reload();
                } else {
                    alert(data.message);
                }
            });
        });
    }


    // Yêu cầu 2: SỬA TÊN CỘT KHI DOUBLE CLICK
    board.addEventListener('dblclick', function(e) {
        const columnTitle = e.target.closest('.column-title');
        if (!columnTitle) return;

        const columnHeader = columnTitle.closest('.column-header');
        const columnId = columnHeader.closest('.padlet-column').dataset.columnId;
        const currentName = columnTitle.textContent;
        
        const input = document.createElement('input');
        input.type = 'text';
        input.value = currentName;
        input.className = 'form-control'; // Dùng class của bootstrap cho đẹp

        columnTitle.replaceWith(input);
        input.focus();

        const saveName = () => {
            const newName = input.value.trim();
            if (newName && newName !== currentName) {
                const url = RENAME_COLUMN_URL.replace('/0', '/' + columnId);
                fetch(url, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ name: newName })
                })
                .then(res => res.json())
                .then(data => {
                    if(data.success) {
                        columnTitle.textContent = data.new_name;
                    } else {
                        alert(data.message);
                        columnTitle.textContent = currentName; // Trả lại tên cũ nếu lỗi
                    }
                    input.replaceWith(columnTitle);
                });
            } else {
                columnTitle.textContent = currentName; // Trả lại tên cũ nếu không đổi
                input.replaceWith(columnTitle);
            }
        };
        
        input.addEventListener('blur', saveName);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') input.blur();
            if (e.key === 'Escape') {
                input.value = currentName;
                input.blur();
            }
        });
    });

    // Yêu cầu 3: KÉO THẢ CỘT
    new Sortable(board, {
        animation: 150,
        handle: '.column-header', // Chỉ cho phép kéo từ header của cột
        ghostClass: 'sortable-ghost',
        onEnd: function(evt) {
            const columnElements = Array.from(board.querySelectorAll('.padlet-column'));
            const newOrder = columnElements.map(col => col.dataset.columnId);
            
            fetch(UPDATE_COLUMN_ORDER_URL, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ order: newOrder })
            })
            .then(res => res.json())
            .then(data => {
                if (!data.success) {
                    alert('Lỗi khi lưu thứ tự cột.');
                    // Có thể thêm logic để hoàn tác lại vị trí nếu cần
                }
            });
        }
    });

    // 4. Khởi tạo Kéo-Thả (SortableJS)
    document.querySelectorAll('.note-cards-container').forEach(container => {
        new Sortable(container, {
            group: 'shared',
            animation: 50,
            onEnd: function (evt) {
                const noteId = evt.item.dataset.noteId;
                const newColumnId = evt.to.closest('.padlet-column').dataset.columnId;
                const url = UPDATE_NOTE_URL.replace('/0', '/' + noteId);
                fetch(url, {
                    method: 'POST', // Đã sửa ở routes.py để nhận cả JSON
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ column_id: newColumnId })
                })
                .then(res => res.json())
                .then(data => {
                    if (!data.success) {
                        alert('Lỗi khi cập nhật cột.');
                        window.location.reload();
                    }
                });
            }
        });
    });
});