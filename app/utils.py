# app/utils.py

import os
import sys
from datetime import datetime, timedelta, date, timezone
from calendar import monthrange

VN_TZ = timezone(timedelta(hours=7))

def to_vn_time(dt):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(VN_TZ)

def to_utc_time(dt):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=VN_TZ)
    return dt.astimezone(timezone.utc)

def get_vn_now():
    return datetime.now(VN_TZ)

def get_vn_today():
    return get_vn_now().date()

def _vn_day_bounds_to_utc(target_date: date):
    start_vn = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=VN_TZ)
    end_vn = start_vn + timedelta(days=1)
    start_utc = start_vn.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = end_vn.astimezone(timezone.utc).replace(tzinfo=None)
    return start_utc, end_utc

def _vn_range_to_utc(start_date: date, end_date_inclusive: date):
    start_utc, _ = _vn_day_bounds_to_utc(start_date)
    _, end_utc = _vn_day_bounds_to_utc(end_date_inclusive)
    return start_utc, end_utc

def get_date_range(view_mode, date_str):
    try:
        base_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        base_date = datetime.today().date()

    if view_mode == 'day':
        start_date = end_date = base_date
        date_display = f"Day {start_date.strftime('%d/%m/%Y')}"
    elif view_mode == 'month':
        start_date = base_date.replace(day=1)
        next_month = start_date.replace(day=28) + timedelta(days=4)
        end_date = next_month - timedelta(days=next_month.day)
        date_display = f"Month {start_date.strftime('%m/%Y')}"
    # === BỔ SUNG LOGIC CHO VIEW YEAR ===
    elif view_mode == 'year':
        start_date = date(base_date.year, 1, 1)
        end_date = date(base_date.year, 12, 31)
        date_display = f"Year {start_date.year}"
    # ====================================
    else: # Mặc định là 'week'
        start_date = base_date - timedelta(days=base_date.weekday())
        end_date = start_date + timedelta(days=6)
        date_display = f"Week {start_date.isocalendar()[1]} ({start_date.strftime('%d/%m')} - {end_date.strftime('%d/%m/%Y')})"
    return start_date, end_date, date_display

def get_time_range_from_filter(time_filter):
    today = date.today()
    if time_filter == 'today':
        start_date = end_date = today
    elif time_filter == 'this_month':
        start_date = today.replace(day=1)
        next_month = (start_date.replace(day=28) + timedelta(days=4))
        end_date = next_month - timedelta(days=next_month.day)
    elif time_filter == 'last_7_days':
        start_date = today - timedelta(days=6)
        end_date = today
    elif time_filter == 'last_30_days':
        start_date = today - timedelta(days=29)
        end_date = today
    else:
        start_date = today - timedelta(days=today.weekday())
        end_date = start_date + timedelta(days=6)
    return start_date, end_date