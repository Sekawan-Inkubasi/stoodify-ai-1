"""Pembantu untuk tes: pembuat data siswa/tugas dan pengecek tabrakan jam."""
from copy import deepcopy
from datetime import datetime
from slots import to_min

NOW = datetime(2026, 10, 5, 8, 0)  # Senin


def make_task(**kw):
    base = {"id": 1, "title": "Tugas", "subject": "X", "type": "tugas",
            "deadline": "2026-10-10", "difficulty": 3, "duration": 60, "progress": 0}
    base.update(kw)
    return base


def make_student(tasks=None, schedules=None, activities=None, **prefs):
    p = {"start_time": "15:00", "end_time": "21:00", "session_duration": 45,
         "active_days": ["mon", "tue", "wed", "thu", "fri", "sat"]}
    p.update(prefs)
    return {"name": "Tes", "preferences": p,
            "schedules": deepcopy(schedules or []),
            "activities": deepcopy(activities or []),
            "tasks": deepcopy(tasks or [])}


def overlaps(a_start, a_end, b_start, b_end):
    return a_start < b_end and b_start < a_end


def day_key(date_iso):
    from slots import DAYS
    return DAYS[datetime.strptime(date_iso, "%Y-%m-%d").weekday()]


def session_hits_busy(session, student):
    k = day_key(session["date"])
    s, e = to_min(session["start_time"]), to_min(session["end_time"])
    for item in student["schedules"] + student["activities"]:
        if item["day"] == k and overlaps(s, e, to_min(item["start"]), to_min(item["end"])):
            return True
    return False
