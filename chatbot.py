"""Modul Chatbot Asisten AI Stoodify (Spesialis Percakapan Interaktif).
Menggunakan model LLM OpenAI-compatible (DeepSeek / Gemini / OpenAI)
dengan persona asisten belajar untuk siswa SMP/SMA/SMK Indonesia.
"""
import json
import logging
import time
from typing import Any, Dict, List, Optional
import httpx

from llm import get_api_key, get_base_url, get_models, get_timeout

log = logging.getLogger("stoodify")

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


def ai_chat(
    message: str,
    history: Optional[List[Dict[str, Any]]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    api_key = get_api_key()
    if not api_key:
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

    # Tambahkan riwayat percakapan sebelumnya (maksimal 6 putaran terakhir)
    if history:
        for item in history[-6:]:
            role = item.get("role") or ("user" if item.get("sender") == "user" else "assistant")
            content = item.get("content") or item.get("text") or ""
            if content.strip():
                messages.append({"role": role, "content": content.strip()})

    # Tambahkan pesan terbaru dari siswa
    messages.append({"role": "user", "content": message.strip()})

    base_url = get_base_url()
    models = get_models()
    timeout = get_timeout()

    last_err = None
    for model in models:
        for attempt in range(2):
            try:
                body = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.5,
                    "response_format": {"type": "json_object"},
                }
                r = httpx.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=body,
                    timeout=timeout,
                )
                if r.status_code >= 400:
                    raise RuntimeError(f"{r.status_code} {r.text[:200]}")

                data = r.json()
                raw_content = data["choices"][0]["message"]["content"]
                if isinstance(raw_content, list):
                    raw_content = "".join(p.get("text", "") for p in raw_content if isinstance(p, dict))

                try:
                    parsed = json.loads(raw_content)
                    return {
                        "reply": parsed.get("reply", raw_content),
                        "action": parsed.get("action") if parsed.get("action") in ("reschedule", "focus") else None,
                        "model": model,
                        "source": "llm",
                    }
                except Exception:
                    return {
                        "reply": raw_content,
                        "action": None,
                        "model": model,
                        "source": "llm",
                    }
            except Exception as e:
                last_err = e
                if attempt == 0:
                    time.sleep(1.0)

    log.error("Gagal memanggil LLM chat: %s", last_err)
    return {
        "reply": "Maaf, saat ini asisten AI sedang mengalami kendala jaringan. Silakan coba kembali sesaat lagi.",
        "action": None,
        "source": "error",
    }
