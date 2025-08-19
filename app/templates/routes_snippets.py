# === INSERT / REPLACE BELOW FUNCTIONS IN app/routes.py ===

from sqlalchemy import asc, desc  # add near other SQLAlchemy imports

@bp.route('/projects')
@login_required
def projects_list():
    status_choices = ['Planned', 'Active', 'On Hold', 'Done']
    current_status = request.args.get('status', 'all')
    q = Project.query
    if current_status != 'all':
        q = q.filter(Project.status == current_status)
    projects = q.order_by(Project.name).all()
    return render_template(
        'projects.html',
        projects=projects,
        page_name='projects',
        status_choices=status_choices,
        current_status=current_status
    )

@bp.route('/update-project/<int:project_id>', methods=['POST'])
@login_required
def update_project(project_id):
    project = Project.query.get_or_404(project_id)
    new_status = request.form.get('status')
    allowed = ['Planned','Active','On Hold','Done']
    if new_status not in allowed:
        flash('Status not true.', 'danger')
        return redirect(url_for('main.projects_list'))

    project.status = new_status
    db.session.commit()
    db.session.add(Log(action=f"Update project status ID {project.id} -> {new_status}", user_id=current_user.id))
    db.session.commit()
    flash('Updated project status', 'success')
    return redirect(request.referrer or url_for('main.projects_list'))

@bp.route('/add-project', methods=['POST'])
@login_required
def add_project():
    name = request.form.get('name')
    status = request.form.get('status') or 'Active'
    if not name:
        flash('Project name must be fill', 'danger')
    else:
        if status not in ['Planned','Active','On Hold','Done']:
            status = 'Active'
        new_project = Project(name=name, description=request.form.get('description'), status=status)
        db.session.add(new_project)
        db.session.commit()
        db.session.add(Log(action=f"Create new project: '{new_project.name}' ({status})", user_id=current_user.id))
        db.session.commit()
        flash('Created new project!', 'success')
    return redirect(url_for('main.projects_list'))

@bp.route('/uploads-manager')
@login_required
def uploads_manager():
    # Search
    query = request.args.get('q', type=str, default='')

    # Sorting
    sort_by = request.args.get('sort_by', 'upload_date')
    order = request.args.get('order', 'desc')
    allowed_fields = {
        'original_filename': UploadedFile.original_filename,
        'file_type': UploadedFile.file_type,
        'file_size': UploadedFile.file_size,
        'upload_date': UploadedFile.upload_date,
    }
    sort_field = allowed_fields.get(sort_by, UploadedFile.upload_date)
    sort_clause = desc(sort_field) if order == 'desc' else asc(sort_field)

    # Pagination
    page = max(1, request.args.get('page', default=1, type=int))
    per_page = request.args.get('per_page', default=20, type=int)
    per_page = min(max(per_page, 1), 100)

    files_query = UploadedFile.query.order_by(sort_clause)
    if query:
        search_term = f"%{query}%"
        files_query = files_query.filter(UploadedFile.original_filename.ilike(search_term))

    files = files_query.paginate(page=page, per_page=per_page, error_out=False)

    # Disk usage
    try:
        total_space, used_space, free_space = shutil.disk_usage('/')
        total_disk_space_gb = total_space / (1024**3)
        used_disk_space_gb = used_space / (1024**3)
        free_space_gb = free_space / (1024**3)
    except Exception:
        total_disk_space_gb, used_disk_space_gb, free_space_gb = 0, 0, 0

    total_files = UploadedFile.query.count()
    uploaded_size_bytes = db.session.query(func.sum(UploadedFile.file_size)).scalar() or 0
    uploaded_size_gb = uploaded_size_bytes / (1024**3)

    other_data_size_gb = max(0, used_disk_space_gb - uploaded_size_gb)

    files_by_type_query = db.session.query(
        UploadedFile.file_type,
        func.count(UploadedFile.id),
        func.sum(UploadedFile.file_size)
    ).group_by(UploadedFile.file_type).all()
    files_by_type_list = [list(row) for row in files_by_type_query]

    uploads_by_user_query = db.session.query(
        User,
        func.sum(UploadedFile.file_size).label('total_size')
    ).join(UploadedFile).group_by(User).order_by(func.sum(UploadedFile.file_size).desc()).all()
    uploads_by_user = [{'user': user, 'total_size': total_size} for user, total_size in uploads_by_user_query]

    file_type_colors = ['#ff7f0e', '#d62728', '#2ca02c', '#1f77b4', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']

    context = {
        'page_name': 'uploads_manager',
        'files': files,
        'total_files': total_files,
        'total_size_mb': uploaded_size_bytes / (1024**2),
        'files_by_type': files_by_type_query,
        'query': query,
        'chart_data': {
            'uploaded_size_gb': round(uploaded_size_gb, 2),
            'other_data_size_gb': round(other_data_size_gb, 2),
            'free_space_gb': round(free_space_gb, 2),
            'files_by_type': files_by_type_list,
        },
        'total_disk_space': round(total_disk_space_gb, 2),
        'used_disk_space': round(used_disk_space_gb, 2),
        'uploads_by_user': uploads_by_user,
        'file_type_colors': file_type_colors,
        'sort_by': sort_by,
        'order': order,
        'page': page,
        'per_page': per_page,
    }
    return render_template('uploads_manager.html', **context)
# === END OF INSERT ===
