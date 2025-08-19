// File: static/js/kanban.js (phiên bản rút gọn)

document.addEventListener('DOMContentLoaded', function() {
    const kanbanBoard = document.querySelector('.kanban-board-container');
    const addTaskBtn = document.getElementById('add-task-btn');
    const updateUrl = kanbanBoard.dataset.updateUrl;

    // 1. KHỞI TẠO KÉO THẢ
    document.querySelectorAll('.kanban-cards-container').forEach(column => {
        new Sortable(column, {
            group: 'kanban-tasks',
            animation: 150,
            ghostClass: 'sortable-ghost',
            onEnd: function(evt) {
                // ... (Logic kéo thả giữ nguyên như file kanban.js cũ của bạn)
                const taskId = evt.item.dataset.taskId;
                const newStatus = evt.to.dataset.status;
                fetch(updateUrl, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ taskId: taskId, newStatus: newStatus })
                });
            }
        });
    });

    // 2. GẮN SỰ KIỆN CLICK
    // Click vào thẻ công việc để sửa
    kanbanBoard.addEventListener('click', function(event) {
        const card = event.target.closest('.kanban-card');
        if (card && typeof window.openEditModal === 'function') {
            try {
                const taskData = JSON.parse(card.dataset.taskJson);
                // GỌI HÀM DÙNG CHUNG TỪ calendar.js
                window.openEditModal(taskData); 
            } catch (e) {
                console.error('Could not parse task JSON data:', e);
            }
        }
    });
    
    // Click nút "Thêm công việc"
    if (addTaskBtn) {
        addTaskBtn.addEventListener('click', function() {
            if (typeof window.openCreateModal === 'function') {
                // GỌI HÀM DÙNG CHUNG TỪ calendar.js
                const pendingColumn = document.querySelector('.kanban-cards-container[data-status="Pending"]');
                const date = new Date().toISOString().split('T')[0];
                window.openCreateModal(date, ''); // Mở modal tạo mới
            }
        });
    }
});