"""Langkah 6 - AI Study Scheduler dengan LLM apa pun yang OpenAI-compatible.
Kode menghitung skor & slot; LLM hanya memilih penempatan sesi dan menulis alasan.
Apa pun yang gagal (tanpa key, timeout, JSON rusak, jadwal melanggar aturan) -> fallback.

Konfigurasi lewat .env: LLM_API_KEY, LLM_BASE_URL, LLM_MODEL (lihat .env.example)."""
import hashlib
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import datetime

import httpx

from priority import deadline_dt, remaining_minutes
from scheduler import fallback_schedule
from slots import find_free_slots, fmt, to_min
from validator import parse_llm_output, validate_sessions, TOLERANCE

DEFAULT_MODEL = "gpt-4o-mini"        # ganti lewat LLM_MODEL di .env
DEFAULT_BASE_URL = "https://api.openai.com/v1"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"  # endpoint OpenAI-compatible milik Gemini
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


def _env(*names, default=None):
    """Nilai env pertama yang terisi dari daftar nama (nama lama GEMINI_* tetap dikenali)."""
    for n in names:
        v = os.getenv(n)
        if v and v.strip():
            return v.strip()
    return default


def get_timeout() -> float:
    """Batas waktu total pemanggilan LLM. Backend menunggu 15 detik, jadi default 10 detik
    agar jadwal fallback masih sempat dikirim balik."""
    try:
        return float(os.getenv("AI_TIMEOUT_SECONDS", "10"))
    except ValueError:
        return 10.0


def get_api_key():
    return _env("LLM_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY")


def get_base_url() -> str:
    """Alamat API OpenAI-compatible, tanpa '/chat/completions' di belakangnya."""
    url = _env("LLM_BASE_URL", "OPENAI_BASE_URL")
    if not url:
        # Kompatibilitas lama: kalau hanya key Gemini yang ada, pakai endpoint Gemini.
        only_gemini = not _env("LLM_API_KEY", "OPENAI_API_KEY") and _env("GEMINI_API_KEY", "GOOGLE_API_KEY")
        url = GEMINI_BASE_URL if only_gemini else DEFAULT_BASE_URL
    return url.rstrip("/")


def get_models() -> list:
    """Satu atau beberapa model dipisah koma. Model berikutnya dipakai jika yang pertama sibuk."""
    raw = _env("LLM_MODEL", "GEMINI_MODEL", default=DEFAULT_MODEL)
    return [m.strip() for m in raw.split(",") if m.strip()]


def build_prompt(student, now: datetime, scores, slots) -> str:
    by_id = {t["id"]: t for t in student["tasks"]}
    p = student["preferences"]
    task_lines = []
    for sc in scores:
        t = by_id[sc["task_id"]]
        need = remaining_minutes(t)
        if need <= 0:
            continue
        task_lines.append(
            f'- id={t["id"]} | {t["title"]} | jenis={t["type"]} | deadline={deadline_dt(t).strftime("%Y-%m-%d %H:%M")} '
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


def _is_busy_error(e: Exception) -> bool:
    t = str(e).lower()
    return any(x in t for x in ("429", "502", "503", "504", "unavailable", "high demand",
                                "overloaded", "rate limit", "resource_exhausted"))


def _wants_no_json_mode(e: Exception) -> bool:
    t = str(e).lower()
    return any(x in t for x in ("response_format", "json_object", "json mode"))


def chat(model: str, prompt: str, json_mode: bool = True, timeout: float = None) -> str:
    """Satu panggilan POST {base_url}/chat/completions (format OpenAI). Mengembalikan teks jawaban."""
    body = {"model": model, "temperature": 0.3,
            "messages": [{"role": "user", "content": prompt}]}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    r = httpx.post(
        get_base_url() + "/chat/completions",
        headers={"Authorization": f"Bearer {get_api_key()}"},
        json=body,
        timeout=get_timeout() if timeout is None else timeout,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"{r.status_code} {r.text[:200]}")
    content = r.json()["choices"][0]["message"]["content"]
    if isinstance(content, list):   # sebagian penyedia mengirim potongan teks berbentuk list
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return content or ""


def call_llm(prompt: str) -> str:
    """Panggil LLM OpenAI-compatible.
    - JSON mode dicoba dulu; jika penyedia menolaknya, ulangi tanpa JSON mode.
    - Jika server sibuk (503/429): coba lagi sekali, lalu pindah ke model berikutnya.
      LLM_MODEL boleh berisi beberapa model dipisah koma, contoh: model-a,model-b"""
    def run_model(model: str) -> str:
        try:
            return chat(model, prompt, True)
        except Exception as e:
            if _wants_no_json_mode(e):
                return chat(model, prompt, False)
            raise

    last = None
    for model in get_models():
        for attempt in range(2):
            try:
                return run_model(model)
            except Exception as e:
                last = e
                if not _is_busy_error(e):
                    raise
                if attempt == 0:
                    time.sleep(1.5)
    raise last


def _call_with_timeout(fn, prompt, timeout):
    ex = ThreadPoolExecutor(max_workers=1)
    fut = ex.submit(fn, prompt)
    try:
        return fut.result(timeout=timeout)
    finally:
        ex.shutdown(wait=False, cancel_futures=True)


def ai_schedule(student, now: datetime, weights=None, call_fn=None,
                timeout=None, use_cache=True) -> dict:
    timeout = get_timeout() if timeout is None else timeout
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
            return use_fallback("LLM_API_KEY belum diatur di file .env")
        call = call_llm

    prompt = build_prompt(student, now, scores, slots)
    key = hashlib.sha256((get_base_url() + "|" + ",".join(get_models()) + "|" + prompt).encode()).hexdigest()
    cached = _cache.get(key) if use_cache else None
    try:
        if cached and time.time() - cached[0] < CACHE_TTL:
            text = cached[1]
        else:
            text = _call_with_timeout(call, prompt, timeout)
    except FutureTimeout:
        return use_fallback(f"LLM tidak merespons dalam {timeout} detik")
    except Exception as e:  # kuota habis, jaringan, key salah, dll.
        return use_fallback(f"LLM error: {type(e).__name__}: {str(e)[:120]}")

    try:
        parsed, parse_errors = parse_llm_output(text)
    except ValueError as e:
        return use_fallback(f"Output LLM tidak valid: {e}")
    valid, rule_errors = validate_sessions(parsed, student, now, slots)
    errors = parse_errors + rule_errors
    total = len(parsed) + len(parse_errors)
    if not valid or len(errors) > total / 2:
        return use_fallback("Terlalu banyak sesi dari LLM yang melanggar aturan: " + "; ".join(errors[:3]))

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
            "reason": s.reason.strip(), "source": "ai",
        })
    sessions.sort(key=lambda x: (x["date"], x["start_time"]))

    warnings = []
    for sc in scores:
        t = by_id[sc["task_id"]]
        need = remaining_minutes(t)
        got = sum(x["duration"] for x in sessions if x["task_id"] == t["id"])
        if need - got >= TOLERANCE:
            warnings.append(f'Waktu untuk "{t["title"]}" kurang sekitar {need - got} menit dari jadwal AI.')
    return {"scores": scores, "sessions": sessions, "warnings": warnings,
            "source": "ai", "fallback_reason": None, "dropped": errors,
            "model": ",".join(get_models()),
            "latency_ms": int((time.time() - t0) * 1000)}
