"""Langkah 2 - Priority Score (bobot 40/20/15/15/10, dikurangi progres)."""
from datetime import datetime

WEIGHTS = {"deadline": 0.40, "difficulty": 0.20, "duration": 0.15,
           "importance": 0.15, "late_risk": 0.10}

IMPORTANCE = {"ujian": 1.0, "proyek": 0.9, "tugas": 0.7, "baca_materi": 0.5}
MAX_DAILY_MINUTES = 240      # pembagi untuk Duration Score
HORIZON_DAYS = 14            # deadline >= 14 hari = urgensi terendah
PROGRESS_REDUCTION = 0.85    # progres 100% menurunkan skor 85%


def deadline_dt(task) -> datetime:
    """Deadline sebagai datetime (waktu lokal tanpa zona). Pakai 'deadline_at' jika ada
    (dari backend), kalau tidak: tanggal 'deadline' + 23:59."""
    if task.get("deadline_at"):
        return task["deadline_at"]
    return datetime.strptime(task["deadline"] + " 23:59", "%Y-%m-%d %H:%M")


def remaining_minutes(task) -> int:
    """Sisa menit yang perlu dijadwalkan: dari progres, dikurangi sesi yang sudah direncanakan."""
    need = round(task["duration"] * (1 - task["progress"] / 100)) - task.get("planned_min", 0)
    return max(0, need)


def days_left(task, now: datetime) -> float:
    return (deadline_dt(task) - now).total_seconds() / 86400


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def score_task(task, now: datetime, weights=None) -> dict:
    w = weights or WEIGHTS
    dl = days_left(task, now)

    # Deadline urgency: skala 1-10 -> dinormalisasi 0-1
    if dl <= 0:
        urgency10 = 10.0
    else:
        urgency10 = clamp(10 - dl * (9 / HORIZON_DAYS), 1, 10)
    urgency = urgency10 / 10

    difficulty = (task["difficulty"] - 1) / 4
    duration = clamp(task["duration"] / MAX_DAILY_MINUTES, 0, 1)
    importance = IMPORTANCE.get(task["type"], 0.7)
    late_risk = 1.0 if (task["progress"] < 20 and dl < 3) else 0.0

    parts = {"deadline": urgency, "difficulty": difficulty, "duration": duration,
             "importance": importance, "late_risk": late_risk}
    raw = sum(w[k] * parts[k] for k in parts)
    total_w = sum(w.values()) or 1
    raw = raw / total_w
    final = raw * (1 - PROGRESS_REDUCTION * task["progress"] / 100)
    score = round(final * 100, 1)

    label = "high" if score >= 55 else "medium" if score >= 35 else "low"
    return {
        "task_id": task["id"], "title": task["title"], "subject": task.get("subject", ""),
        "type": task["type"], "deadline": task["deadline"],
        "days_left": round(dl, 1), "progress": task["progress"],
        "parts": {k: round(v, 2) for k, v in parts.items()},
        "score": score, "priority": label,
    }


def score_all(tasks, now: datetime, weights=None) -> list:
    done = [t for t in tasks if t["progress"] < 100]
    return sorted((score_task(t, now, weights) for t in done),
                  key=lambda r: r["score"], reverse=True)
