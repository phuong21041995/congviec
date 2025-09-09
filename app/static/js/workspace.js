document.addEventListener('DOMContentLoaded', function() {
    // Logic chung cho trang workspace, không thuộc về tab cụ thể nào

    // Logic cho Modal Sửa Project
    const editProjectModalEl = document.getElementById('editProjectModal');
    if (editProjectModalEl) {
        const editProjectModal = new bootstrap.Modal(editProjectModalEl);
        document.querySelectorAll('.btn-edit-project').forEach(button => {
            button.addEventListener('click', async function() {
                const currentProjectId = this.dataset.projectId;
                try {
                    const response = await fetch(`/api/project/${currentProjectId}`);
                    if (!response.ok) throw new Error('Network response was not ok.');
                    const data = await response.json();
                    
                    const form = document.getElementById('editProjectForm');
                    form.action = `/update-project/${currentProjectId}`;
                    document.getElementById('editProjectName').value = data.name || '';
                    document.getElementById('editProjectDescription').value = data.description || '';
                    document.getElementById('editProjectStartDate').value = data.start_date || '';
                    document.getElementById('editProjectEndDate').value = data.end_date || '';
                    document.getElementById('editProjectStatus').value = data.status || 'Active';
                    editProjectModal.show();
                } catch (error) {
                    console.error('Failed to fetch project details:', error);
                    alert('Could not load project details.');
                }
            });
        });
    }

    // Logic cho Modal Sửa Build
    const editBuildModalEl = document.getElementById('editBuildModal');
    if (editBuildModalEl) {
        const editBuildModal = new bootstrap.Modal(editBuildModalEl);
        document.body.addEventListener('click', async function(event) {
            const editBuildBtn = event.target.closest('.btn-edit-build');
            if (editBuildBtn) {
                const buildId = editBuildBtn.dataset.buildId;
                 try {
                    const response = await fetch(`/api/build/${buildId}`);
                    if (!response.ok) throw new Error('Network response was not ok.');
                    const data = await response.json();
                    
                    const form = document.getElementById('editBuildForm');
                    form.action = `/update-build/${buildId}`;
                    document.getElementById('editBuildName').value = data.name || '';
                    document.getElementById('editBuildProject').value = data.project_id || '';
                    document.getElementById('editBuildStartDate').value = data.start_date || '';
                    document.getElementById('editBuildEndDate').value = data.end_date || '';
                    editBuildModal.show();
                } catch (error) {
                    console.error('Failed to fetch build details:', error);
                    alert('Could not load build details.');
                }
            }
        });
    }

    // Logic cho Gantt Chart (Timeline Tab)
    if (window.active_tab === 'timeline' && window.project_id) {
        if (document.getElementById('gantt_here')) {
            gantt.init("gantt_here");
            gantt.load(`/api/dhtmlx-data?project_id=${window.project_id}`);
        }
    }
});
