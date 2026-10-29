"""Validasi output LLM: struktur JSON (Pydantic) + aturan jadwal (slot, deadline, tabrakan)."""
import json
import re
from datetime import datetime
from pydantic import AliasChoices, BaseModel, Field, ValidationError, field_validator
from priority import deadline_dt, days_left, remaining_minutes
from slots import to_min

TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
MIN_LEN, MAX_LEN = 15, 120   # menit per sesi
TOLERANCE = 15               # kelebihan menit yang masih ditoleransi per tugas


class SessionOut(BaseModel):
    task_id: int
    # PRD memakai "recommended_date"; "date" juga diterima
    date: str = Field(validation_alias=AliasChoices("date", "recommended_date"))
    start_time: str
    end_time: str
    target_progress: int = Field(ge=0, le=100)
    reason: str = Field(min_length=5)

    @field_validator("date")
    @classmethod
    def _date(cls, v):
        datetime.strptime(v, "%Y-%m-%d")
        return v

    @field_validator("start_time", "end_time")
    @classmethod
    def _time(cls, v):
        if not TIME_RE.match(v):
            raise ValueError("format jam harus HH:MM")
        return v


def extract_json(text: str):
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.I).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        a, b = t.find("{"), t.rfind("}")
        if a != -1 and b > a:
            return json.loads(t[a:b + 1])
        raise


def parse_llm_output(text: str):
    """Kembalikan (sesi_valid_struktur, daftar_error). Raise ValueError jika bukan JSON sama sekali."""
    try:
        data = extract_json(text)
    except (json.JSONDecodeError, TypeError) as e:
        raise ValueError(f"bukan JSON yang valid ({e})")
    items = data.get("sessions") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError('JSON tidak punya daftar "sessions"')
    sessions, errors = [], []
    for i, it in enumerate(items):
        try:
            sessions.append(SessionOut.model_validate(it))
        except ValidationError as e:
            errors.append(f"sesi #{i + 1} struktur salah: {e.errors()[0]['msg']}")
    return sessions, errors


def validate_sessions(sessions, student, now: datetime, free_slots):
    """Saring sesi yang melanggar aturan. Kembalikan (sesi_lolos, daftar_error)."""
    by_id = {t["id"]: t for t in student["tasks"]}
    valid, errors, taken, minutes = [], [], [], {}
    for s in sessions:
        tag = f"tugas {s.task_id} {s.date} {s.start_time}"
        t = by_id.get(s.task_id)
        if not t or t["progress"] >= 100:
            errors.append(f"{tag}: tugas tidak ada/sudah selesai")
            continue
        a, b = to_min(s.start_time), to_min(s.end_time)
        dur = b - a
        if dur < MIN_LEN or dur > MAX_LEN:
            errors.append(f"{tag}: durasi {dur} menit di luar {MIN_LEN}-{MAX_LEN}")
            continue
        if not any(sl["date"] == s.date and sl["start"] <= a and b <= sl["end"] for sl in free_slots):
            errors.append(f"{tag}: di luar slot kosong (bentrok sekolah/kegiatan/jam belajar)")
            continue
        end_dt = datetime.strptime(f"{s.date} {s.end_time}", "%Y-%m-%d %H:%M")
        if days_left(t, now) > 0 and end_dt > deadline_dt(t):
            errors.append(f"{tag}: melewati deadline")
            continue
        if any(d == s.date and a < y and x < b for d, x, y in taken):
            errors.append(f"{tag}: bertabrakan dengan sesi lain")
            continue
        need = remaining_minutes(t)
        if minutes.get(s.task_id, 0) + dur > need + TOLERANCE:
            errors.append(f"{tag}: melebihi kebutuhan waktu tugas")
            continue
        minutes[s.task_id] = minutes.get(s.task_id, 0) + dur
        taken.append((s.date, a, b))
        valid.append(s)
    return valid, errors
