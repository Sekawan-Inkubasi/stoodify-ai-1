"""Payload contoh yang meniru JSON dari backend Go (struct Task serialisasi GORM, dll.)."""
import copy
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _task(id, title, type_, deadline, difficulty, minutes, progress, status="pending", snoozed=False):
    return {
        "id": id, "created_at": "2026-10-01T03:00:00Z", "updated_at": "2026-10-04T03:00:00Z",
        "user_id": 7, "subject_id": 2, "title": title, "description": "catatan pribadi",
        "type": type_, "deadline": deadline, "difficulty": difficulty,
        "estimated_duration": minutes, "priority_score": 50.0, "status": status,
        "progress": progress, "is_snoozed": snoozed, "notes": "",
    }


def _sched(day, start, end, id=1):
    return {"id": id, "user_id": 7, "subject_id": 2, "day_of_week": day,
            "start_time": start, "end_time": end}


def contoh_payload(**over):
    p = {
        "user_id": 7,
        "date": "2026-10-05",
        "now": "2026-10-05T08:00:00+07:00",
        "timezone": "Asia/Jakarta",
        "preferences": {"start_time": "15:00", "end_time": "21:00",
                        "session_duration": 45, "active_days": "1,2,3,4,5,6"},
        "tasks": [
            _task(1, "Laporan Konfigurasi Jaringan", "project", "2026-10-07T23:59:00+07:00", 4, 180, 10, "in_progress"),
            _task(2, "Latihan Soal Basis Data", "assignment", "2026-10-06T16:59:00Z", 2, 45, 80, "in_progress"),
            _task(3, "Persiapan Ujian Matematika", "exam", "2026-10-10T23:59:00+07:00", 5, 240, 0),
            _task(4, "Baca Bab 3 Sistem Operasi", "reading", "2026-10-20T23:59:00+07:00", 2, 40, 0),
            _task(5, "Tugas Sudah Selesai", "assignment", "2026-10-09T23:59:00+07:00", 3, 60, 100, "done"),
            _task(6, "Tugas Ditunda", "assignment", "2026-10-09T23:59:00+07:00", 3, 60, 0, "pending", True),
        ],
        "schedules": [
            _sched("Monday", "07:00", "16:00", 1), _sched("Tuesday", "07:00", "15:30", 2),
            _sched("Wednesday", "07:00", "15:30", 3), _sched("Thursday", "07:00", "16:00", 4),
            _sched("Friday", "07:00", "14:30", 5),
        ],
        "activities": [
            {"id": 1, "user_id": 7, "title": "Ekskul DKV", "day_of_week": "Wednesday",
             "start_time": "16:00", "end_time": "17:30", "recurrence": "weekly"},
            {"id": 2, "user_id": 7, "title": "Makan malam", "start_time": "18:00",
             "end_time": "19:00", "recurrence": "daily"},
        ],
        "existing_sessions": [
            {"id": 11, "user_id": 7, "task_id": 3, "session_date": "2026-10-06T00:00:00Z",
             "start_time": "16:00", "duration": 45, "status": "planned", "ai_generated": True},
        ],
    }
    p = copy.deepcopy(p)
    p.update(over)
    return p


if __name__ == "__main__":
    with open(os.path.join(ROOT, "contoh_payload.json"), "w", encoding="utf-8") as f:
        json.dump(contoh_payload(), f, indent=2, ensure_ascii=True)
    print("contoh_payload.json dibuat")
