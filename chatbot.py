"""Modul Chatbot Asisten AI Stoodify (Spesialis Percakapan Interaktif).
Menggunakan model LLM OpenAI-compatible (DeepSeek / Gemini / OpenAI)
dengan persona asisten belajar untuk siswa SMP/SMA/SMK Indonesia.
"""
import json
import logging
import re
import time
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any, Callable, Dict, List, Optional

import httpx

from llm import (
    _call_with_timeout,
    _is_busy_error,
    _wants_no_json_mode,
    get_api_key,
    get_base_url,
    get_models,
    get_timeout,
)

log = logging.getLogger("stoodify")

ALLOWED_HISTORY_ROLES = ("user", "assistant")
MAX_HISTORY_TURNS = 6
RETRY_SLEEP_SECONDS = 1.0

SYSTEM_PROMPT = """Kamu adalah Stoodify AI, asisten belajar cerdas, ramah, dan interaktif untuk siswa SMP/SMA/SMK Indonesia.
Tugas dan Panduanmu:
1. Bantu siswa memahami materi pelajaran, konsep sulit, atau strategi pengerjaan tugas dengan penjelasan yang jelas, mudah dipahami, dan interaktif.
2. Berikan motivasi belajar, tips manajemen waktu, teknik fokus (seperti Pomodoro/Zen Focus), dan dukungan positif dalam bahasa Indonesia yang santun, hangat, dan suportif.
3. Gunakan informasi tugas atau jadwal belajar siswa (jika tersedia pada konteks) agar saran yang kamu berikan sangat personal dan kontekstual.
4. Identifikasi kebutuhan aksi siswa:
   - Jika siswa meminta/membutuhkan penyusunan atau penjadwalan ulang belajar adaptif: set action = "reschedule".
   - Jika siswa ingin mulai sesi fokus belajar sekarang atau butuh timer fokus: set action = "focus".
   - Jika pertanyaan siswa seputar materi umum, tanya jawab, atau diskusi: set action = null.
5. Format keluaran WAJIB berupa JSON valid dengan struktur persis berikut:
{"reply": "<teks jawaban ramah, interaktif, dan terstruktur (maksimal 2-3 paragraf ringkas)>", "action": "reschedule"|"focus"|null}
"""


def _build_context_str(context: Optional[Dict[str, Any]]) -> str:
    if not context:
        return ""
    lines = []
    name = context.get("student_name")
    if name:
        lines.append(f"Nama Siswa: {name}")
    grade = context.get("grade") or context.get("class_level")
    if grade:
        lines.append(f"Jenjang/Kelas: {grade}")
    school = context.get("school")
    if school:
        lines.append(f"Sekolah: {school}")
    tasks = context.get("active_tasks") or context.get("tasks") or []
    if tasks:
        task_items = []
        for t in tasks[:5]:
            title = t.get("title", "")
            deadline = t.get("deadline", "")
            if title:
                task_items.append(f"- {title}" + (f" (Deadline: {deadline})" if deadline else ""))
        if task_items:
            lines.append("Tugas Aktif Siswa:\n" + "\n".join(task_items))
    if not lines:
        return ""
    return "INFORMASI SISWA & TUGAS SAAT INI:\n" + "\n".join(lines)


def _sanitize_history(history: Optional[List[Dict[str, Any]]]) -> List[Dict[str, str]]:
    """Ambil maksimal 6 putaran terakhir dengan validasi role ketat (hanya user/assistant)."""
    if not history:
        return []
    sanitized: List[Dict[str, str]] = []
    for item in history[-MAX_HISTORY_TURNS:]:
        if not isinstance(item, dict):
            continue
        raw_role = item.get("role")
        if raw_role is not None:
            role_norm = str(raw_role).strip().lower()
            if role_norm not in ALLOWED_HISTORY_ROLES:
                # Tolak role selain user/assistant (mis. "system", "developer", "tool")
                # agar klien tidak dapat menyisipkan instruksi sistem melalui history.
                continue
            role = role_norm
        else:
            sender = str(item.get("sender") or "").strip().lower()
            role = "user" if sender == "user" else "assistant"

        content = str(item.get("content") or item.get("text") or "").strip()
        if content:
            sanitized.append({"role": role, "content": content})
    return sanitized


def _parse_chat_reply(raw_content: str, model: str) -> Dict[str, Any]:
    """Ekstrak JSON {reply, action} dari jawaban LLM; fallback ke teks mentah bila bukan JSON."""
    clean = (raw_content or "").strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", clean, flags=re.I).strip()
    try:
        parsed = json.loads(clean)
        if isinstance(parsed, dict):
            reply = str(parsed.get("reply") or raw_content).strip()
            action = parsed.get("action") if parsed.get("action") in ("reschedule", "focus") else None
            return {
                "reply": reply,
                "action": action,
                "model": model,
                "source": "llm",
            }
    except Exception:
        pass
    return {
        "reply": raw_content,
        "action": None,
        "model": model,
        "source": "llm",
    }


def _post_chat_completion(
    base_url: str,
    api_key: str,
    model: str,
    messages: List[Dict[str, str]],
    json_mode: bool,
    timeout: float,
) -> str:
    """Satu panggilan POST {base_url}/chat/completions untuk chatbot."""
    body: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.5,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    r = httpx.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json=body,
        timeout=max(0.1, timeout),
    )
    if r.status_code >= 400:
        raise RuntimeError(f"{r.status_code} {r.text[:200]}")

    data = r.json()
    raw_content = data["choices"][0]["message"]["content"]
    if isinstance(raw_content, list):
        raw_content = "".join(p.get("text", "") for p in raw_content if isinstance(p, dict))
    return raw_content or ""


def _call_chat_models(
    messages: List[Dict[str, str]],
    base_url: str,
    api_key: str,
    models: List[str],
    total_timeout: float,
) -> Dict[str, Any]:
    """Panggil daftar model LLM dalam batas waktu total `total_timeout`.
    - Hanya retry pada error sibuk (429/5xx), tidak pada 4xx permanen (400/401/403).
    - Jika penyedia menolak `response_format`, ulangi tanpa JSON mode.
    """
    deadline = time.monotonic() + total_timeout
    last_err: Optional[Exception] = None

    def _run_model(model: str) -> str:
        rem = deadline - time.monotonic()
        if rem <= 0:
            raise TimeoutError(f"LLM chat melebihi batas waktu {total_timeout} detik")
        try:
            return _post_chat_completion(base_url, api_key, model, messages, True, rem)
        except Exception as e:
            if _wants_no_json_mode(e):
                rem2 = deadline - time.monotonic()
                if rem2 <= 0:
                    raise TimeoutError(f"LLM chat melebihi batas waktu {total_timeout} detik") from e
                return _post_chat_completion(base_url, api_key, model, messages, False, rem2)
            raise

    for model in models:
        for attempt in range(2):
            if deadline - time.monotonic() <= 0:
                raise TimeoutError(f"LLM chat melebihi batas waktu {total_timeout} detik")
            try:
                raw_content = _run_model(model)
                return _parse_chat_reply(raw_content, model)
            except Exception as e:
                last_err = e
                if not _is_busy_error(e):
                    raise
                if attempt == 0:
                    rem = deadline - time.monotonic()
                    sleep_for = min(RETRY_SLEEP_SECONDS, max(0.0, rem - 0.5))
                    if sleep_for > 0:
                        time.sleep(sleep_for)
                    elif rem <= 0:
                        raise TimeoutError(f"LLM chat melebihi batas waktu {total_timeout} detik") from e

    if last_err is not None:
        raise last_err
    raise RuntimeError("Tidak ada model LLM yang dikonfigurasi")


def ai_chat(
    message: str,
    history: Optional[List[Dict[str, Any]]] = None,
    context: Optional[Dict[str, Any]] = None,
    timeout: Optional[float] = None,
    call_fn: Optional[Callable[[List[Dict[str, str]]], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    api_key = get_api_key()
    if call_fn is None and not api_key:
        return {
            "reply": "Halo! Kunci API LLM belum diatur di server AI. Silakan periksa konfigurasi .env.",
            "action": None,
            "source": "fallback",
        }

    sys_text = SYSTEM_PROMPT
    ctx_str = _build_context_str(context)
    if ctx_str:
        sys_text += f"\n\n{ctx_str}"

    messages: List[Dict[str, str]] = [{"role": "system", "content": sys_text}]
    messages.extend(_sanitize_history(history))
    messages.append({"role": "user", "content": message.strip()})

    effective_timeout = get_timeout() if timeout is None else timeout

    if call_fn is not None:
        runner = call_fn
    else:
        base_url = get_base_url()
        models = get_models()
        runner = lambda msgs: _call_chat_models(msgs, base_url, api_key, models, effective_timeout)

    try:
        return _call_with_timeout(runner, messages, effective_timeout)
    except (FutureTimeout, TimeoutError) as e:
        log.warning("LLM chat timeout setelah %.1fs: %s", effective_timeout, e)
        return {
            "reply": "Maaf, respons asisten AI sedang lambat. Silakan coba kembali sesaat lagi.",
            "action": None,
            "source": "fallback",
        }
    except Exception as e:
        log.error("Gagal memanggil LLM chat: %s", e)
        return {
            "reply": "Maaf, saat ini asisten AI sedang mengalami kendala jaringan. Silakan coba kembali sesaat lagi.",
            "action": None,
            "source": "error",
        }
