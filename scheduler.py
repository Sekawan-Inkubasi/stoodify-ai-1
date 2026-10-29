"""Langkah 4 - Fallback scheduler (greedy, tanpa AI)."""
from datetime import datetime
from priority import score_all, deadline_dt, days_left, remaining_minutes
from slots import find_free_slots, fmt

BREAK = 10          # menit jeda antar sesi
MIN_SESSION = 20    # sesi terpendek yang masih masuk akal
MAX_PER_TASK_PER_DAY = 2


def make_chunks(slots, session_len):
    chunks = []
    for s in slots:
        cur = s["start"]
        while s["end"] - cur >= MIN_SESSION:
            end = min(cur + session_len, s["end"])
            chunks.append({"date": s["date"], "start": cur, "end": end})
            cur = end + BREAK
    return chunks


def reason_text(task, sc) -> str:
    dl = sc["days_left"]
    if dl <= 0:
        when = "Deadline sudah lewat, selesaikan secepatnya"
    elif dl < 1:
        when = "Deadline tinggal hari ini"
    elif dl < 2:
        when = "Deadline besok"
    else:
        when = f"Deadline tinggal {int(dl)} hari"
    extra = []
    if task["difficulty"] >= 4:
        extra.append("tingkat kesulitan tinggi")
    if task["type"] == "ujian":
        extra.append("persiapan ujian butuh waktu cukup")
    if task["progress"] >= 50:
        extra.append("progres sudah separuh lebih, tinggal diselesaikan")
    elif task["progress"] < 20 and dl < 3:
        extra.append("belum banyak dikerjakan")
    return when + (", " + ", ".join(extra) if extra else "") + "."


def fallback_schedule(student, now: datetime, weights=None):
    scores = score_all(student["tasks"], now, weights)
    by_id = {t["id"]: t for t in student["tasks"]}
    session_len = student["preferences"]["session_duration"]
    chunks = make_chunks(find_free_slots(student, now), session_len)
    used = set()
    sessions, warnings = [], []

    # tugas yang sudah lewat deadline didahulukan, sisanya urut skor
    ordered = sorted(scores, key=lambda x: (x["days_left"] > 0, -x["score"]))
    for sc in ordered:
        task = by_id[sc["task_id"]]
        need = remaining_minutes(task)
        if need <= 0:
            continue
        overdue = days_left(task, now) <= 0
        dl_dt = deadline_dt(task)
        progress = task["progress"]
        per_day = {}
        for i, c in enumerate(chunks):
            if need <= 0:
                break
            if i in used:
                continue
            c_end = datetime.strptime(f"{c['date']} {fmt(c['end'])}", "%Y-%m-%d %H:%M")
            if not overdue and c_end > dl_dt:
                continue
            if per_day.get(c["date"], 0) >= MAX_PER_TASK_PER_DAY:
                continue
            length = min(c["end"] - c["start"], need)
            if length < 15:
                length = 15
            gained = round(length / task["duration"] * 100)
            progress = min(100, progress + gained)
            sessions.append({
                "task_id": task["id"], "title": task["title"], "subject": task.get("subject", ""),
                "date": c["date"], "start_time": fmt(c["start"]),
                "end_time": fmt(c["start"] + length), "duration": length,
                "target_progress": progress, "priority": sc["priority"],
                "reason": reason_text(task, sc), "source": "fallback",
            })
            used.add(i)
            per_day[c["date"]] = per_day.get(c["date"], 0) + 1
            need -= length
        if need > 0:
            warnings.append(f"Waktu tidak cukup untuk \"{task['title']}\": "
                            f"kurang sekitar {need} menit sebelum deadline.")
    sessions.sort(key=lambda s: (s["date"], s["start_time"]))
    return {"scores": scores, "sessions": sessions, "warnings": warnings}
