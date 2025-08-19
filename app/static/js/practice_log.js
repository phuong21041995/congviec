{% block scripts %}
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
document.addEventListener('DOMContentLoaded', () => {
    // --- KHAI BÁO BIẾN ---
    let trendChart, pieChart;
    let currentCalDate = new Date();
    const deepLogModalEl = document.getElementById('deepLogModal');
    const deepLogModal = new bootstrap.Modal(deepLogModalEl);
    const dayLogsOffcanvasEl = document.getElementById('dayLogsOffcanvas');
    const dayLogsOffcanvas = new bootstrap.Offcanvas(dayLogsOffcanvasEl);
    const deepLogForm = document.getElementById('deepLogForm');
    const deleteLogButton = document.getElementById('deleteLogButton');

    const API_URLS = {
        getChartData: "{{ url_for('main.get_chart_data') }}",
        getCalendarData: "{{ url_for('main.get_practice_calendar_data') }}",
        getLogsByDate: "{{ url_for('main.get_logs_by_date') }}",
        getRecentLogs: "{{ url_for('main.get_recent_logs') }}",
        getDeepLog: "{{ url_for('main.get_deep_log', log_id=0) }}".slice(0, -1),
        saveLog: "{{ url_for('main.save_practice_log') }}",
        deleteLog: "{{ url_for('main.delete_practice_log', log_id=0) }}".slice(0, -1)
    };

    // --- CÁC HÀM XỬ LÝ SỰ KIỆN & LOGIC ---
    
    // Hàm cập nhật tất cả các thành phần giao diện sau khi có thay đổi
    async function updateUI() {
        console.log("Bắt đầu cập nhật giao diện...");
        await initAndRenderCharts();
        await renderPracticeCalendar(currentCalDate.getFullYear(), currentCalDate.getMonth() + 1);
        await updateRecentLogs();
        console.log("Cập nhật giao diện hoàn tất.");
    }

    // Hàm cập nhật danh sách ghi nhận mới nhất
    async function updateRecentLogs() {
        const recentLogsList = document.getElementById('recentLogsList');
        recentLogsList.innerHTML = `<div class="list-group-item text-center p-3"><div class="spinner-border spinner-border-sm"></div> Đang cập nhật...</div>`;
        
        try {
            const response = await fetch(`${API_URLS.getRecentLogs}?_ts=${new Date().getTime()}`);
            const data = await response.json();
            
            let logsHtml = '';
            if (data.success && data.logs && data.logs.length > 0) {
                logsHtml = data.logs.map(log => {
                    const logDate = new Date(log.log_ts);
                    const formattedTime = logDate.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });
                    const formattedDate = logDate.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit' });
                    return `
                        <div class="list-group-item">
                            <div class="d-flex w-100 justify-content-between">
                                <p class="mb-1"><strong>${log.tag}:</strong> ${log.note || '(không có ghi chú)'}</p>
                                <small class="text-nowrap ms-3">${formattedTime}, ${formattedDate}</small>
                            </div>
                            <button class="btn btn-sm btn-outline-secondary mt-1" data-log-id="${log.id}">
                                <i class="fa-solid fa-magnifying-glass"></i> Xem & Quán chiếu
                            </button>
                        </div>
                    `;
                }).join('');
            } else {
                logsHtml = `<div class="list-group-item text-center text-muted p-3">Chưa có ghi nhận nào.</div>`;
            }
            recentLogsList.innerHTML = logsHtml;

        } catch (error) {
            console.error("Lỗi khi cập nhật danh sách log gần nhất:", error);
            recentLogsList.innerHTML = `<div class="list-group-item text-center text-danger p-3">Lỗi cập nhật. Vui lòng tải lại trang.</div>`;
        }
    }

    function openDeepLogModal(logData = {}) {
        deepLogForm.reset();
        deepLogForm.querySelectorAll('.btn-check').forEach(radio => radio.checked = false);
        
        document.getElementById('logIdInput').value = logData.id || '';
        document.getElementById('logDateInput').value = logData.log_date || '';

        let displayTime = new Date();
        if (logData.log_date && logData.log_time_vn) {
            document.getElementById('logTimeInput').value = logData.log_time_vn;
            const datetimeStr = `${logData.log_date}T${logData.log_time_vn}`;
            displayTime = new Date(datetimeStr);
        } else {
            const now = new Date();
            const vnOffset = 7 * 60;
            const localOffset = now.getTimezoneOffset();
            now.setMinutes(now.getMinutes() + localOffset + vnOffset);

            const vnDateStr = now.toISOString().split('T')[0];
            const vnTimeStr = now.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit', hour12: false });
            
            document.getElementById('logDateInput').value = logData.log_date || vnDateStr;
            document.getElementById('logTimeInput').value = vnTimeStr;
            displayTime = new Date(`${document.getElementById('logDateInput').value}T${vnTimeStr}`);
        }

        document.getElementById('logDateTimeDisplay').value = displayTime.toLocaleDateString('vi-VN') + ' ' + displayTime.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });

        if (logData.id) {
            deleteLogButton.style.display = 'inline-block';
            document.getElementById('logTagInput').value = logData.tag || '';
            document.getElementById('logNoteInput').value = logData.note || '';
            deepLogForm.querySelector('[name="situation"]').value = logData.situation || logData.note || '';
            deepLogForm.querySelector('[name="contemplation"]').value = logData.contemplation || '';
            deepLogForm.querySelector('[name="outcome"]').value = logData.outcome || '';
            const door = logData.sense_door || 'Ý (Suy nghĩ)';
            const tabElement = Array.from(document.querySelectorAll('#senseDoorTabs button')).find(t => t.textContent.trim() === door.split(' ')[0]);
            if (tabElement) new bootstrap.Tab(tabElement).show();
            const tabId = tabElement ? tabElement.id.replace('tab-', '') : 'y';
            const senseObjectInput = deepLogForm.querySelector(`[name="sense_object_${tabId}"]`);
            if (senseObjectInput) senseObjectInput.value = logData.sense_object || '';
            if (logData.feeling) {
                const feelingRadio = deepLogForm.querySelector(`input[name="feeling_${tabId}"][value="${logData.feeling}"]`);
                if (feelingRadio) feelingRadio.checked = true;
            }
            if (logData.craving) {
                const cravingRadio = deepLogForm.querySelector(`input[name="craving_${tabId}"][value="${logData.craving}"]`);
                if (cravingRadio) cravingRadio.checked = true;
            }
        } else {
            deleteLogButton.style.display = 'none';
        }
        deepLogModal.show();
    }

    async function handleDayClick(event) {
        const dayDiv = event.target;
        const dateStr = dayDiv.dataset.date;
        if (!dateStr) return;

        const listEl = document.getElementById('dayLogsList');
        document.getElementById('dayLogsTitle').textContent = `Các ghi nhận ngày ${new Date(dateStr + 'T00:00:00').toLocaleDateString('vi-VN')}`;
        listEl.innerHTML = `<div class="text-center p-3"><div class="spinner-border spinner-border-sm"></div></div>`;
        dayLogsOffcanvas.show();

        try {
            const response = await fetch(`${API_URLS.getLogsByDate}?date=${dateStr}`);
            const data = await response.json();
            let logsHtml = '';
            if (data.success && data.logs && data.logs.length > 0) {
                logsHtml = data.logs.map(log => `
                    <a href="#" class="list-group-item list-group-item-action day-log-item" data-log-id="${log.id}">
                        <div class="d-flex w-100 justify-content-between">
                            <h6 class="mb-1">${log.tag}</h6>
                            <small>${new Date(log.log_ts).toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })}</small>
                        </div>
                        <p class="mb-1 small text-muted">${log.note || ''}</p>
                    </a>`).join('');
            } else {
                logsHtml = `<div class="list-group-item text-muted">Chưa có ghi nhận nào cho ngày này.</div>`;
            }
            logsHtml += `
                <div class="list-group-item">
                    <button class="btn btn-primary w-100" id="addLogButton" data-log-date="${dateStr}">
                        <i class="fa-solid fa-plus me-2"></i> Thêm quán chiếu mới
                    </button>
                </div>
            `;
            listEl.innerHTML = logsHtml;

        } catch (error) {
            listEl.innerHTML = `<div class="list-group-item text-danger">Lỗi tải dữ liệu.</div>`;
        }
    }

    async function editLogById(logId) {
        if (!logId) return;
        try {
            const response = await fetch(API_URLS.getDeepLog + logId);
            const data = await response.json();
            if (response.ok && data.success) {
                openDeepLogModal(data.log);
            }
        } catch (error) {
            console.error("Lỗi tải chi tiết log:", error);
        }
    }

    function initEventListeners() {
        document.getElementById('practiceCalendarBody').addEventListener('click', e => {
            if (e.target.classList.contains('calendar-day')) handleDayClick(e);
        });
        document.getElementById('dayLogsList').addEventListener('click', e => {
            const logItem = e.target.closest('.day-log-item');
            const addLogButton = e.target.closest('#addLogButton');
            if (logItem) {
                e.preventDefault();
                dayLogsOffcanvas.hide();
                editLogById(logItem.dataset.logId);
            } else if (addLogButton) {
                e.preventDefault();
                dayLogsOffcanvas.hide();
                openDeepLogModal({ log_date: addLogButton.dataset.logDate });
            }
        });
        document.getElementById('recentLogsList').addEventListener('click', e => {
            const button = e.target.closest('button[data-log-id]');
            if (button) editLogById(button.dataset.logId);
        });
        
        // Sự kiện submit form
        deepLogForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            const situationText = deepLogForm.querySelector('[name="situation"]').value;
            document.getElementById('logNoteInput').value = situationText || 'Quán chiếu sâu';
            const activeTabId = document.getElementById('activeTabInput').value || 'y';
            const checkedCraving = deepLogForm.querySelector(`input[name="craving_${activeTabId}"]:checked`);
            let newTag = 'Chánh niệm';
            if(checkedCraving) {
                if (checkedCraving.value.includes('Tham')) newTag = 'Tham';
                else if (checkedCraving.value.includes('Sân')) newTag = 'Sân';
                else if (checkedCraving.value.includes('Si')) newTag = 'Si';
            }
            document.getElementById('logTagInput').value = newTag;

            // Log giá trị trước khi gửi để kiểm tra
            console.log("Giá trị Sense Object chuẩn bị gửi:", deepLogForm.querySelector(`[name="sense_object_${activeTabId}"]`).value);

            const formData = new FormData(this);
            try {
                const response = await fetch(API_URLS.saveLog, {
                    method: 'POST',
                    body: formData
                });
                const result = await response.json();
                if (result.success) {
                    deepLogModal.hide();
                    await updateUI();
                } else {
                    console.error('Lỗi khi lưu: ', result.message);
                }
            } catch (error) {
                console.error('Lỗi kết nối:', error);
            }
        });

        // Sự kiện xóa log
        deleteLogButton.addEventListener('click', async () => {
            const logId = document.getElementById('logIdInput').value;
            if (!logId || !confirm('Bạn có chắc chắn muốn xóa quán chiếu này không?')) return;
            try {
                const response = await fetch(`${API_URLS.deleteLog}${logId}`, {
                    method: 'DELETE'
                });
                const result = await response.json();
                if (result.success) {
                    deepLogModal.hide();
                    await updateUI();
                } else {
                    console.error('Lỗi khi xóa: ' + result.message);
                }
            } catch (error) {
                console.error('Lỗi kết nối:', error);
            }
        });

        document.querySelectorAll('#senseDoorTabs button').forEach(tab => { tab.addEventListener('shown.bs.tab', event => { document.getElementById('activeTabInput').value = event.target.id.replace('tab-', ''); }); });
        document.getElementById('cal-prev-month').addEventListener('click', () => { currentCalDate.setMonth(currentCalDate.getMonth() - 1); renderPracticeCalendar(currentCalDate.getFullYear(), currentCalDate.getMonth() + 1); });
        document.getElementById('cal-next-month').addEventListener('click', () => { currentCalDate.setMonth(currentCalDate.getMonth() + 1); renderPracticeCalendar(currentCalDate.getFullYear(), currentCalDate.getMonth() + 1); });
    }

    // --- CÁC HÀM KHÁC (BIỂU ĐỒ, LỊCH) ---
    async function initAndRenderCharts() { try { const response = await fetch(`${API_URLS.getChartData}?days=30&_ts=${new Date().getTime()}`); if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`); const data = await response.json(); renderTrendChart(data.trend_data || []); renderTodayPieChart(data.today_pie_data || {}); } catch (err) { console.error('Lỗi khi tải dữ liệu biểu đồ:', err); } }
    
    function renderTrendChart(trendData) { 
        const colorMap = { 'Tham': '#fbbf24', 'Sân': '#f87171', 'Si': '#60a5fa'}; 
        const coreTags = ['Tham', 'Sân', 'Si']; 
        const ctx = document.getElementById('trendChart').getContext('2d'); 
        const today = new Date(); 
        const labels = Array.from({ length: 30 }, (_, i) => { 
            const d = new Date(today); 
            d.setDate(d.getDate() - (29 - i)); 
            return d.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit' }); 
        }); 
        
        const datasetMap = new Map(coreTags.map(tag => [tag, { 
            label: tag, 
            data: new Array(30).fill(0), 
            backgroundColor: colorMap[tag] || '#ccc' 
        }])); 
        
        trendData.forEach(item => { 
            const itemDate = new Date(item.date + 'T00:00:00'); 
            const itemDateNormalized = new Date(itemDate.getFullYear(), itemDate.getMonth(), itemDate.getDate()); 
            const diffTime = today.setHours(0,0,0,0) - itemDateNormalized.setHours(0,0,0,0); 
            const diffDays = Math.round(diffTime / (1000 * 60 * 60 * 24)); 
            const index = 29 - diffDays; 
            if (index >= 0 && index < 30 && datasetMap.has(item.tag)) { 
                datasetMap.get(item.tag).data[index] = item.count; 
            } 
        }); 
        
        if (trendChart) trendChart.destroy(); 
        trendChart = new Chart(ctx, { 
            type: 'bar', 
            data: { 
                labels, 
                datasets: Array.from(datasetMap.values()) 
            }, 
            options: { 
                responsive: true,
                scales: { 
                    x: { 
                        stacked: true, 
                    }, 
                    y: { 
                        stacked: true, 
                        beginAtZero: true, 
                        ticks: { 
                            stepSize: 1 
                        } 
                    } 
                } 
            } 
        }); 
    }

    function renderTodayPieChart(pieData) { 
        const colorMap = { 'Tham': '#fbbf24', 'Sân': '#f87171', 'Si': '#60a5fa', 'Nghi': '#a78bfa', 'Mạn': '#f472b6', 'Chánh niệm': '#4ade80', 'Từ bi': '#34d399', 'Hỷ': '#2dd4bf', 'Bình tĩnh': '#a3a3a3' }; 
        const ctx = document.getElementById('todayPieChart').getContext('2d'); 
        const pieLabels = Object.keys(pieData); 
        const pieValues = Object.values(pieData); 
        if (pieChart) pieChart.destroy(); 
        if (pieLabels.length === 0) { 
            ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height); 
            ctx.save(); 
            ctx.textAlign = 'center'; 
            ctx.textBaseline = 'middle'; 
            ctx.fillStyle = '#9ca3af'; 
            ctx.font = '16px sans-serif'; 
            ctx.fillText('Chưa có ghi nhận nào cho hôm nay.', ctx.canvas.width / 2, ctx.canvas.height / 2); 
            ctx.restore(); 
            return; 
        } 
        pieChart = new Chart(ctx, { 
            type: 'doughnut', 
            data: { 
                labels: pieLabels, 
                datasets: [{ 
                    data: pieValues, 
                    backgroundColor: pieLabels.map(label => colorMap[label] || '#e5e7eb'), 
                    hoverOffset: 4 
                }] 
            }, 
            options: { responsive: true, maintainAspectRatio: false } 
        }); 
    }

    async function renderPracticeCalendar(year, month) {
        const localToday = new Date();
        const todayStr = `${localToday.getFullYear()}-${String(localToday.getMonth() + 1).padStart(2, '0')}-${String(localToday.getDate()).padStart(2, '0')}`;
        
        const calendarBody = document.getElementById('practiceCalendarBody');
        const monthYearLabel = document.getElementById('cal-month-year');
        if (!calendarBody || !monthYearLabel) return;
        monthYearLabel.textContent = `Tháng ${month}/${year}`;
        calendarBody.innerHTML = '<tr><td colspan="7" class="text-center p-5"><div class="spinner-border spinner-border-sm"></div></td></tr>';
        try {
            const response = await fetch(`${API_URLS.getCalendarData}?year=${year}&month=${month}&_ts=${new Date().getTime()}`);
            const data = await response.json();
            const loggedDates = new Set(data.logged_dates || []);
            const firstDay = new Date(year, month - 1, 1);
            const daysInMonth = new Date(year, month, 0).getDate();
            let startingDay = firstDay.getDay();
            if (startingDay === 0) startingDay = 7;
            let date = 1, html = '';
            for (let i = 0; i < 6; i++) {
                html += '<tr>';
                for (let j = 1; j <= 7; j++) {
                    if ((i === 0 && j < startingDay) || date > daysInMonth) {
                        html += '<td></td>';
                    } else {
                        const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(date).padStart(2, '0')}`;
                        let classes = 'calendar-day';
                        if (loggedDates.has(dateStr)) classes += ' day-has-log';
                        if (dateStr === todayStr) classes += ' is-today';
                        html += `<td><div class="${classes}" data-date="${dateStr}">${date}</div></td>`;
                        date++;
                    }
                }
                html += '</tr>';
                if (date > daysInMonth) break;
            }
            calendarBody.innerHTML = html;
        } catch (err) {
            console.error("Lỗi tải lịch:", err);
            calendarBody.innerHTML = '<tr><td colspan="7" class="text-danger p-3">Không thể tải lịch.</td></tr>';
        }
    }

    // --- KHỞI CHẠY ---
    initEventListeners();
    (async () => {
        await renderPracticeCalendar(currentCalDate.getFullYear(), currentCalDate.getMonth() + 1);
        await initAndRenderCharts();
    })();
});
</script>
{% endblock %}