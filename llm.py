"""Langkah 6 - AI Study Scheduler dengan Gemini.
Kode menghitung skor & slot; Gemini hanya memilih penempatan sesi dan menulis alasan.
Apa pun yang gagal (tanpa key, timeout, JSON rusak, jadwal melanggar aturan) -> fallback."""
import hashlib
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import datetime

from scheduler import fallback_schedule
from slots import find_free_slots, fmt, to_min
from validator import parse_llm_output, validate_sessions, TOLERANCE

DEFAULT_MODEL = "gemini-3.5-flash"   # ganti lewat GEMINI_MODEL di .env
TIMEOUT_SECONDS = 15                 # batas PRD
CACHE_TTL = 600
_cache = {}

DAY_ID = {"mon": "Senin", "tue": "Selasa", "wed": "Rabu", "thu": "Kamis",
          "fri": "Jumat", "sat": "Sabtu", "sun": "Minggu"}


def load_env(path=".env"):
    """Pemuat .env sederhana (tanpa library tambahan)."""
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def get_api_key():
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


def build_prompt(student, now: datetime, scores, slots) -> str:
    by_id = {t["id"]: t for t in student["tasks"]}
    p = student["preferences"]
    task_lines = []
    for sc in scores:
        t = by_id[sc["task_id"]]
        need = round(t["duration"] * (1 - t["progress"] / 100))
        task_lines.append(
            f'- id={t["id"]} | {t["title"]} | jenis={t["type"]} | deadline={t["deadline"]} 23:59 '
            f'| kesulitan={t["difficulty"]}/5 | progres={t["progress"]}% '
            f'| sisa_menit={need} | skor={sc["score"]} ({sc["priority"]})')
    slot_lines = [f'- {s["date"]} ({DAY_ID[s["day"]]}) {fmt(s["start"])}-{fmt(s["end"])}' for s in slots]
    return f"""Kamu adalah asisten penjadwal belajar untuk siswa SMP/SMA/SMK Indonesia.
Sekarang: {now.strftime("%Y-%m-%d %H:%M")}.

TUGAS (sudah diurutkan dari prioritas tertinggi; skor sudah dihitung, jangan dihitung ulang):
{chr(10).join(task_lines)}

SLOT KOSONG (satu-satunya waktu yang boleh dipakai):
{chr(10).join(slot_lines)}

ATURAN WAJIB:
1. Setiap sesi harus berada SEPENUHNYA di dalam satu slot kosong di atas, pada tanggal yang sama.
2. Durasi sesi 15-{max(p["session_duration"], 45)} menit. Beri jeda minimal 10 menit antar sesi.
3. Sesi tidak boleh bertabrakan satu sama lain dan harus selesai sebelum deadline tugasnya
   (kecuali deadline sudah lewat: jadwalkan secepatnya).
4. Total menit semua sesi satu tugas tidak boleh melebihi sisa_menit-nya.
5. Tugas berskor tinggi dapat slot lebih awal. Maksimal 2 sesi per tugas per hari.
6. target_progress = perkiraan persen progres tugas SETELAH sesi itu selesai (0-100, naik dari sesi ke sesi).
7. reason: 1 kalimat bahasa Indonesia sederhana (maks 20 kata) yang menyebut alasan nyata
   (deadline, kesulitan, progres). Jangan memakai istilah teknis.

KELUARAN: hanya JSON, tanpa teks lain, dengan bentuk persis:
{{"sessions": [{{"task_id": 1, "date": "YYYY-MM-DD", "start_time": "HH:MM", "end_time": "HH:MM", "target_progress": 40, "reason": "..."}}]}}
"""


def call_gemini(prompt: str) -> str:
    """Panggil Gemini. Import di dalam fungsi agar engine tetap jalan tanpa SDK."""
    from google import genai
    from google.genai import types
    client = genai.Client(
        api_key=get_api_key(),
        http_options=types.HttpOptions(timeout=int(TIMEOUT_SECONDS * 1000)),
    )
    resp = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", DEFAULT_MODEL),
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.3),
    )
    return resp.text


def _call_with_timeout(fn, prompt, timeout):
    ex = ThreadPoolExecutor(max_workers=1)
    fut = ex.submit(fn, prompt)
    try:
        return fut.result(timeout=timeout)
    finally:
        ex.shutdown(wait=False, cancel_futures=True)


def ai_schedule(student, now: datetime, weights=None, call_fn=None,
                timeout=TIMEOUT_SECONDS, use_cache=True) -> dict:
    t0 = time.time()
    base = fallback_schedule(student, now, weights)   # skor + jadwal cadangan (murah)
    base.update(dropped=[], model=None)

    def use_fallback(reason):
        out = dict(base)
        out.update(source="fallback", fallback_reason=reason,
                   latency_ms=int((time.time() - t0) * 1000))
        return out

    scores = base["scores"]
    last_deadline = max((s["deadline"] for s in scores if s["days_left"] > 0), default=None)
    slots = [s for s in find_free_slots(student, now)
             if last_deadline is None or s["date"] <= last_deadline][:60]
    if not scores or not slots:
        return use_fallback("tidak ada tugas atau slot kosong, AI tidak dipanggil")

    call = call_fn
    if call is None:
        if not get_api_key():
            return use_fallback("GEMINI_API_KEY belum diatur di file .env")
        call = call_gemini

    prompt = build_prompt(student, now, scores, slots)
    key = hashlib.sha256(prompt.encode()).hexdigest()
    cached = _cache.get(key) if use_cache else None
    try:
        if cached and time.time() - cached[0] < CACHE_TTL:
            text = cached[1]
        else:
            text = _call_with_timeout(call, prompt, timeout)
    except FutureTimeout:
        return use_fallback(f"Gemini tidak merespons dalam {timeout} detik")
    except Exception as e:  # kuota habis, jaringan, key salah, dll.
        return use_fallback(f"Gemini error: {type(e).__name__}: {str(e)[:120]}")

    try:
        parsed, parse_errors = parse_llm_output(text)
    except ValueError as e:
        return use_fallback(f"Output Gemini tidak valid: {e}")
    valid, rule_errors = validate_sessions(parsed, student, now, slots)
    errors = parse_errors + rule_errors
    total = len(parsed) + len(parse_errors)
    if not valid or len(errors) > total / 2:
        return use_fallback("Terlalu banyak sesi Gemini yang melanggar aturan: " + "; ".join(errors[:3]))

    if use_cache:
        _cache[key] = (time.time(), text)

    by_id = {t["id"]: t for t in student["tasks"]}
    prio = {s["task_id"]: s["priority"] for s in scores}
    sessions = []
    for s in valid:
        sessions.append({
            "task_id": s.task_id, "title": by_id[s.task_id]["title"],
            "subject": by_id[s.task_id].get("subject", ""), "date": s.date,
            "start_time": s.start_time, "end_time": s.end_time,
            "duration": to_min(s.end_time) - to_min(s.start_time),
            "target_progress": s.target_progress, "priority": prio[s.task_id],
            "reason": s.reason.strip(), "source": "gemini",
        })
    sessions.sort(key=lambda x: (x["date"], x["start_time"]))

    warnings = []
    for sc in scores:
        t = by_id[sc["task_id"]]
        need = round(t["duration"] * (1 - t["progress"] / 100))
        got = sum(x["duration"] for x in sessions if x["task_id"] == t["id"])
        if need - got >= TOLERANCE:
            warnings.append(f'Waktu untuk "{t["title"]}" kurang sekitar {need - got} menit dari jadwal AI.')
    return {"scores": scores, "sessions": sessions, "warnings": warnings,
            "source": "gemini", "fallback_reason": None, "dropped": errors,
            "model": os.getenv("GEMINI_MODEL", DEFAULT_MODEL),
            "latency_ms": int((time.time() - t0) * 1000)}
