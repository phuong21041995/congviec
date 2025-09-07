// uploads_manager.js
// Logic cho trang Quản lý File (uploads_manager.html)

document.addEventListener('DOMContentLoaded', function() {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const progressArea = document.getElementById('progress-area');
    const deleteButtons = document.querySelectorAll('.delete-file-btn');

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

    // Vẽ biểu đồ tròn
    function createDiskUsageChart(data, fileTypeColors) {
        const ctx = document.getElementById('diskUsageChart');
        if (!ctx) return;
        
        // Tạo labels và data cho biểu đồ loại file
        const fileTypeLabels = data.files_by_type.map(item => `${item[0]} (${(item[2] / 1024 / 1024).toFixed(2)} MB)`);
        const fileTypeData = data.files_by_type.map(item => item[2] / (1024 * 1024)); // Chuyển sang MB
        const fileTypeBgColors = fileTypeColors;

        // Tổng hợp dữ liệu biểu đồ
        const labels = ['Dung lượng đã upload (GB)', 'Dữ liệu khác (GB)', 'Dung lượng trống (GB)'];
        const datasets = [{
            label: 'Dung lượng',
            data: [data.uploaded_size_gb, data.other_data_size_gb, data.free_space_gb],
            backgroundColor: ['#fd7e14', '#dc3545', '#e9ecef'], // Gam màu nóng
            hoverOffset: 4
        }];

        new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                let label = context.label || '';
                                if (label) {
                                    label += ': ';
                                }
                                if (context.parsed !== null) {
                                    label += context.parsed.toFixed(2) + ' GB';
                                }
                                return label;
                            }
                        }
                    }
                }
            }
        });
    }

    // `chartData` được truyền từ template
    if (typeof chartData !== 'undefined') {
        createDiskUsageChart(chartData);
    }
    
    if (!dropZone || !fileInput || !progressArea) return;
    
    const uploadUrl = dropZone.dataset.uploadUrl;
    if (!uploadUrl) {
        console.error("Upload URL is not defined.");
        return;
    }

    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, e => {
            e.preventDefault();
            e.stopPropagation();
        });
    });

    ['dragenter', 'dragover'].forEach(eventName => dropZone.addEventListener(eventName, () => dropZone.classList.add('drag-over')));
    ['dragleave', 'drop'].forEach(eventName => dropZone.addEventListener(eventName, () => dropZone.classList.remove('drag-over')));

    dropZone.addEventListener('drop', handleFiles);
    fileInput.addEventListener('change', handleFiles);

    function handleFiles(event) {
        const files = event.type === 'drop' ? event.dataTransfer.files : this.files;
        if (files.length > 0) {
            for(const file of files) {
                uploadFile(file);
            }
        }
    }

    function uploadFile(file) {
        const formData = new FormData();
        formData.append('file', file);
        // Bên trong hàm uploadFile, ngay trước khi fetch(INIT_URL, ...)
		const projectSelect = document.getElementById('uploadProjectSelect');
		const projectId = projectSelect ? projectSelect.value : null;

		// ----- BƯỚC 1: BÁO CÁO LÊN SERVER ĐỂ LẤY UPLOAD_ID -----
		updateProgress(0, 'Khởi tạo...');
		const initResponse = await fetch(INIT_URL, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ 
				filename: file.name, 
				total_size: file.size,
				project_id: projectId // <-- Gửi project_id đi
			})
		});
        const progressId = `progress-${Math.random().toString(36).substr(2, 9)}`;
        const progressHTML = `
            <div class="upload-item" id="${progressId}">
                <div class="d-flex justify-content-between mb-1">
                    <span class="text-truncate">${file.name}</span>
                    <span class="progress-percent">0%</span>
                </div>
                <div class="progress" style="height: 10px;">
                    <div class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar" style="width: 0%;"></div>
                </div>
            </div>`;
        progressArea.insertAdjacentHTML('beforeend', progressHTML);
        
        const progressBar = document.querySelector(`#${progressId} .progress-bar`);
        const progressPercent = document.querySelector(`#${progressId} .progress-percent`);
        
        const xhr = new XMLHttpRequest();
        xhr.open('POST', uploadUrl, true);

        xhr.upload.onprogress = function(event) {
            if (event.lengthComputable) {
                const percentComplete = Math.round((event.loaded / event.total) * 100);
                progressBar.style.width = percentComplete + '%';
                progressPercent.textContent = percentComplete + '%';
            }
        };

        xhr.onload = function() {
            progressBar.classList.remove('progress-bar-animated');
            if (xhr.status === 200) {
                try {
                    const data = JSON.parse(xhr.responseText);
                    if (data.success) {
                        progressBar.classList.add('bg-success');
                        progressPercent.textContent = 'Thành công!';
                        showToast('Thành công', data.message, 'bg-success text-white');
                        setTimeout(() => window.location.reload(), 1500);
                    } else {
                        progressBar.classList.add('bg-danger');
                        progressPercent.textContent = 'Thất bại!';
                        showToast('Lỗi', data.message || 'Tải file thất bại.', 'bg-danger text-white');
                    }
                } catch (e) {
                     progressBar.classList.add('bg-danger');
                     progressPercent.textContent = 'Lỗi server.';
                     showToast('Lỗi', 'Không thể đọc phản hồi từ server.', 'bg-danger text-white');
                }
            } else {
                 progressBar.classList.add('bg-danger');
                 progressPercent.textContent = `Lỗi: ${xhr.status}`;
                 showToast('Lỗi', `Server trả về mã lỗi ${xhr.status}.`, 'bg-danger text-white');
            }
        };

        xhr.onerror = function() {
            progressBar.classList.remove('progress-bar-animated');
            progressBar.classList.add('bg-danger');
            progressPercent.textContent = 'Lỗi mạng.';
            showToast('Lỗi', 'Lỗi kết nối mạng.', 'bg-danger text-white');
        };
        
        xhr.send(formData);
    }

    // Xử lý nút xóa file
    deleteButtons.forEach(button => {
        button.addEventListener('click', function() {
            if (!confirm('Bạn có chắc chắn muốn xóa file này không? Hành động này không thể hoàn tác.')) return;

            const fileId = this.closest('tr').dataset.fileId;
            const row = this.closest('tr');
            
            fetch(`${DELETE_FILE_URL_BASE}${fileId}`, {
                method: 'POST'
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    showToast('Thành công', data.message, 'bg-success text-white');
                    // Tải lại trang để cập nhật thống kê
                    setTimeout(() => window.location.reload(), 1000);
                } else {
                    showToast('Lỗi', data.message, 'bg-danger text-white');
                }
            })
            .catch(() => {
                showToast('Lỗi', 'Không thể kết nối tới server.', 'bg-danger text-white');
            });
        });
    });
});