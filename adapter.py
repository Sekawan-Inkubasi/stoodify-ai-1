"""Adapter: payload dari backend Go -> struktur data engine, dan hasil engine -> format backend."""
import re
from datetime import datetime, time as dtime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

from slots import DAYS, fmt, to_min

DEFAULT_TZ = "Asia/Jakarta"
WIB = timezone(timedelta(hours=7))  # Indonesia tidak memakai DST, jadi offset tetap aman sebagai cadangan

TYPE_MAP = {
    "exam": "ujian", "ujian": "ujian",
    "project": "proyek", "proyek": "proyek",
    "assignment": "tugas", "tugas": "tugas",
    "reading": "baca_materi", "baca_materi": "baca_materi", "baca materi": "baca_materi",
}

_DAY_NAMES = {
    "mon": ["monday", "mon", "senin"], "tue": ["tuesday", "tue", "selasa"],
    "wed": ["wednesday", "wed", "rabu"], "thu": ["thursday", "thu", "kamis"],
    "fri": ["friday", "fri", "jumat", "jumat"], "sat": ["saturday", "sat", "sabtu"],
    "sun": ["sunday", "sun", "minggu", "ahad"],
}
DAY_ALIASES = {alias: key for key, names in _DAY_NAMES.items() for alias in names}
DAY_ALIASES.update({"1": "mon", "2": "tue", "3": "wed", "4": "thu", "5": "fri",
                    "6": "sat", "7": "sun", "0": "sun"})

DEFAULT_ACTIVE = ["mon", "tue", "wed", "thu", "fri", "sat"]


class PayloadError(ValueError):
    """Payload dari backend tidak bisa dipakai sama sekali."""


def norm_day(value):
    if value is None:
        return None
    key = str(value).strip().lower().replace("'", "")
    return DAY_ALIASES.get(key)


def norm_hhmm(value):
    m = re.match(r"^\s*(\d{1,2}):(\d{2})", str(value or ""))
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        return None
    return f"{h:02d}:{mi:02d}"


def get_tz(name):
    try:
        return ZoneInfo(name or DEFAULT_TZ)
    except Exception:
        return WIB


def parse_dt(value, tz):
    """RFC3339 / ISO -> datetime lokal tanpa zona (di zona tz). Tanggal saja = akhir hari (23:59)."""
    if not value:
        return None
    text = str(value).strip()
    try:
        if len(text) == 10:
            return datetime.strptime(text, "%Y-%m-%d").replace(hour=23, minute=59)
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(tz).replace(tzinfo=None)


def _int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_active_days(value):
    if value is None:
        return []
    items = value if isinstance(value, list) else str(value).split(",")
    days = []
    for it in items:
        d = norm_day(it)
        if d and d not in days:
            days.append(d)
    return days


def adapt_request(payload, now=None):
    """Kembalikan (student, now_efektif, warnings, meta). Raise PayloadError jika payload tidak bisa dipakai."""
    if not isinstance(payload, dict):
        raise PayloadError("body harus berupa objek JSON")
    warnings = []
    tz = get_tz(payload.get("timezone"))

    real_now = parse_dt(payload.get("now"), tz) if payload.get("now") else None
    if real_now is None:
        real_now = now or datetime.now(tz).replace(tzinfo=None)

    raw_date = str(payload.get("date") or real_now.date().isoformat())[:10]
    try:
        target = datetime.strptime(raw_date, "%Y-%m-%d")
    except ValueError:
        raise PayloadError('format "date" harus YYYY-MM-DD')
    start_now = max(real_now, datetime.combine(target.date(), dtime(0, 0)))

    # ---- preferensi ----
    p = payload.get("preferences") or {}
    p_start = norm_hhmm(p.get("start_time")) or "15:00"
    p_end = norm_hhmm(p.get("end_time")) or "21:00"
    if to_min(p_start) >= to_min(p_end):
        warnings.append("Jam belajar di preferensi tidak valid, dipakai 15:00-21:00.")
        p_start, p_end = "15:00", "21:00"
    session_duration = _int(p.get("session_duration"), 0)
    if session_duration <= 0:
        session_duration = 60
    active = parse_active_days(p.get("active_days")) or DEFAULT_ACTIVE
    prefs = {"start_time": p_start, "end_time": p_end,
             "session_duration": session_duration, "active_days": active}

    # ---- tugas ----
    tasks, snoozed = [], 0
    for t in payload.get("tasks") or []:
        if not isinstance(t, dict) or t.get("id") is None:
            continue
        status = str(t.get("status") or "").lower()
        progress = min(100, max(0, _int(t.get("progress"), 0)))
        if status == "done" or progress >= 100:
            continue
        if t.get("is_snoozed"):
            snoozed += 1
            continue
        deadline_at = parse_dt(t.get("deadline"), tz)
        if deadline_at is None:
            warnings.append(f'Tugas "{t.get("title", t["id"])}" tidak punya deadline valid, dilewati.')
            continue
        subject = t.get("subject")
        tasks.append({
            "id": _int(t["id"], 0),
            "title": str(t.get("title") or "Tugas"),
            "subject": subject.get("name", "") if isinstance(subject, dict) else "",
            "type": TYPE_MAP.get(str(t.get("type") or "").lower(), "tugas"),
            "deadline": deadline_at.date().isoformat(),
            "deadline_at": deadline_at,
            "difficulty": min(5, max(1, _int(t.get("difficulty"), 3))),
            "duration": max(1, _int(t.get("estimated_duration"), 60) or 60),
            "progress": progress,
            "planned_min": 0,
        })
    by_id = {t["id"]: t for t in tasks}

    # ---- jadwal sekolah ----
    schedules = []
    if payload.get("schedules") is None:
        warnings.append("Backend tidak mengirim jadwal sekolah: jam sekolah tidak diperhitungkan, sesi bisa bentrok.")
    for s in payload.get("schedules") or []:
        day, a, b = norm_day(s.get("day_of_week", s.get("day"))), norm_hhmm(s.get("start_time", s.get("start"))), norm_hhmm(s.get("end_time", s.get("end")))
        if day and a and b and to_min(a) < to_min(b):
            schedules.append({"day": day, "start": a, "end": b, "title": str(s.get("title") or "Sekolah")})

    # ---- kegiatan rutin ----
    activities = []
    if payload.get("activities") is None:
        warnings.append("Backend tidak mengirim kegiatan rutin: ekskul dan kegiatan lain tidak diperhitungkan.")
    for act in payload.get("activities") or []:
        a, b = norm_hhmm(act.get("start_time", act.get("start"))), norm_hhmm(act.get("end_time", act.get("end")))
        if not (a and b and to_min(a) < to_min(b)):
            continue
        title = str(act.get("title") or "Kegiatan")
        recurrence = str(act.get("recurrence") or "").lower()
        day = norm_day(act.get("day_of_week", act.get("day")))
        one_date = str(act.get("date") or "")[:10] or None
        if recurrence == "daily":
            activities += [{"day": d, "start": a, "end": b, "title": title} for d in DAYS]
        elif day:
            activities.append({"day": day, "start": a, "end": b, "title": title})
        elif one_date:
            activities.append({"date": one_date, "start": a, "end": b, "title": title})
        elif recurrence == "monthly":
            warnings.append(f'Kegiatan "{title}" berulang bulanan tanpa tanggal, diabaikan.')
        else:
            activities += [{"day": d, "start": a, "end": b, "title": title} for d in DAYS]
            warnings.append(f'Kegiatan "{title}" tidak punya hari, dianggap berlangsung setiap hari.')

    # ---- sesi yang sudah direncanakan ----
    if payload.get("existing_sessions") is None:
        warnings.append("Backend tidak mengirim sesi yang sudah ada: bisa terjadi sesi ganda atau bertumpuk.")
    today_iso = start_now.date().isoformat()
    for s in payload.get("existing_sessions") or []:
        if str(s.get("status") or "planned").lower() != "planned":
            continue
        date_iso = str(s.get("session_date") or s.get("date") or s.get("recommended_date") or "")[:10]
        a, dur = norm_hhmm(s.get("start_time")), _int(s.get("duration"), 0)
        if not (date_iso and a and dur > 0) or date_iso < today_iso:
            continue
        end = min(to_min(a) + dur, 23 * 60 + 59)
        activities.append({"date": date_iso, "start": a, "end": fmt(end), "title": "Sesi terjadwal"})
        task = by_id.get(_int(s.get("task_id"), -1))
        if task:
            task["planned_min"] += dur

    student = {"name": "Siswa", "preferences": prefs, "schedules": schedules,
               "activities": activities, "tasks": tasks}
    meta = {"date": target.date().isoformat(), "snoozed_skipped": snoozed, "tasks_used": len(tasks)}
    return student, start_now, warnings, meta


def to_backend_sessions(sessions):
    """Format persis seperti struct slotRekomendasi di backend Go."""
    return [{
        "task_id": s["task_id"],
        "recommended_date": s["date"],
        "start_time": s["start_time"],
        "end_time": s["end_time"],
        "duration": s["duration"],
        "target_progress": s["target_progress"],
        "priority": s["priority"],
        "reason": s["reason"],
    } for s in sessions]
