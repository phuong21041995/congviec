document.addEventListener('DOMContentLoaded', function() {
    tinymce.init({
        selector: 'textarea#report-editor',
        license_key: 'gpl',
        plugins: 'autolink lists link image charmap preview anchor pagebreak code',
        toolbar: 'undo redo | bold italic underline | alignleft aligncenter alignright | bullist numlist outdent indent | link image | code',
        menubar: false,
        height: 400,
        images_upload_url: UPLOAD_IMAGE_URL, // Sử dụng biến đã được định nghĩa trong HTML
        automatic_uploads: true,
        file_picker_types: 'image',
    });

    const reportForm = document.getElementById('reportForm');
    const actionId = "{{ action.id }}";
    
    reportForm.addEventListener('submit', function(event) {
        event.preventDefault();
        
        const editor = tinymce.get('report-editor');
        if (editor) editor.save();
        
        const formData = new FormData(this);
        const reportContent = formData.get('report_content');

        if (!reportContent.trim()) {
            alert('Nội dung báo cáo không được để trống.');
            return;
        }

        fetch(this.action, {
            method: 'POST',
            body: formData,
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                alert('Đã lưu báo cáo thành công!');
            } else {
                alert('Lỗi: ' + data.message);
            }
        })
        .catch(error => {
            alert('Lỗi kết nối server.');
        });
    });
});