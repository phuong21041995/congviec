# Centralized constants for tasks/statuses used across views

TASK_STATUSES = ['Pending', 'In Progress', 'Review', 'Done', 'Drop']

STATUS_META = {
    'Pending':     {'color': '#6c757d', 'icon': 'fa-solid fa-hourglass-half'},
    'In Progress': {'color': '#0d6efd', 'icon': 'fa-solid fa-person-digging'},
    'Review':      {'color': '#6f42c1', 'icon': 'fa-solid fa-magnifying-glass'},
    'Done':        {'color': '#198754', 'icon': 'fa-solid fa-circle-check'},
    'Drop':        {'color': '#dc3545', 'icon': 'fa-solid fa-circle-xmark'},
}
