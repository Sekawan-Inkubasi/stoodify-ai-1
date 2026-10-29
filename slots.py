"""Langkah 3 - Time-Slot Finder: jam belajar - jadwal sekolah - kegiatan rutin."""
from datetime import datetime, timedelta

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
MIN_SLOT = 30  # slot lebih pendek dari ini dibuang


def to_min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def fmt(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def subtract(window, busy_list):
    """Kurangi satu rentang (start, end) dengan daftar rentang sibuk."""
    free = [window]
    for b_start, b_end in sorted(busy_list):
        nxt = []
        for f_start, f_end in free:
            if b_end <= f_start or b_start >= f_end:
                nxt.append((f_start, f_end))
                continue
            if b_start > f_start:
                nxt.append((f_start, b_start))
            if b_end < f_end:
                nxt.append((b_end, f_end))
        free = nxt
    return free


def busy_for_day(student, day_key, date_iso=None):
    """Rentang sibuk pada satu hari. Item dengan kunci 'date' hanya berlaku di tanggal itu;
    item lain berlaku tiap minggu pada hari 'day'."""
    busy = []
    for i in student["schedules"] + student["activities"]:
        if i.get("date"):
            if i["date"] == date_iso:
                busy.append((to_min(i["start"]), to_min(i["end"])))
        elif i.get("day") == day_key:
            busy.append((to_min(i["start"]), to_min(i["end"])))
    return busy


def find_free_slots(student, now: datetime, days_ahead: int = 14):
    prefs = student["preferences"]
    p_start, p_end = to_min(prefs["start_time"]), to_min(prefs["end_time"])
    slots = []
    for offset in range(days_ahead):
        d = (now + timedelta(days=offset)).date()
        key = DAYS[d.weekday()]
        if key not in prefs["active_days"]:
            continue
        start = p_start
        if offset == 0:  # hari ini: mulai dari waktu sekarang, dibulatkan ke 15 menit
            cur = now.hour * 60 + now.minute
            start = max(start, ((cur + 14) // 15) * 15)
        if start >= p_end:
            continue
        for s, e in subtract((start, p_end), busy_for_day(student, key, d.isoformat())):
            if e - s >= MIN_SLOT:
                slots.append({"date": d.isoformat(), "day": key, "start": s, "end": e})
    return slots
