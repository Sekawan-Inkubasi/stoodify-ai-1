"""Diagnosis Gemini: jalankan dari folder stoodify-ai ->  python tes_gemini.py
Tes 1: panggilan kecil per model (cek key, nama model, dan kecepatan dasar).
Tes 2: prompt jadwal sungguhan dari contoh_payload.json (cek waktu dan kevalidan hasil)."""
import json
import os
import time

from llm import DEFAULT_MODEL, build_prompt, get_api_key, load_env
from adapter import adapt_request
from scheduler import fallback_schedule
from slots import find_free_slots
from validator import parse_llm_output, validate_sessions

load_env()
if not get_api_key():
    raise SystemExit("GEMINI_API_KEY belum ada di .env")

from google import genai
from google.genai import types

client = genai.Client(api_key=get_api_key(), http_options=types.HttpOptions(timeout=60000))
models = [m.strip() for m in os.getenv("GEMINI_MODEL", DEFAULT_MODEL).split(",") if m.strip()]


def panggil(model, prompt, json_mode=True):
    cfg = {"temperature": 0.3}
    if json_mode:
        cfg["response_mime_type"] = "application/json"
    t0 = time.time()
    try:
        r = client.models.generate_content(model=model, contents=prompt,
                                           config=types.GenerateContentConfig(**cfg))
        return time.time() - t0, r.text, None
    except Exception as e:
        return time.time() - t0, None, f"{type(e).__name__}: {str(e)[:220]}"


print("=== TES 1: panggilan kecil ===")
for m in models:
    dt, text, err = panggil(m, 'Balas hanya JSON: {"ok": true}')
    print(f"{m}: " + (f"OK {dt:.1f} dtk -> {text.strip()[:60]}" if text else f"GAGAL {dt:.1f} dtk -> {err}"))

print("\n=== TES 2: prompt jadwal sungguhan ===")
with open("contoh_payload.json", encoding="utf-8") as f:
    payload = json.load(f)
student, now, _, _ = adapt_request(payload)
slots = find_free_slots(student, now)[:60]
prompt = build_prompt(student, now, fallback_schedule(student, now)["scores"], slots)
print(f"panjang prompt: {len(prompt)} karakter")
for m in models:
    dt, text, err = panggil(m, prompt)
    if not text:
        print(f"{m}: GAGAL {dt:.1f} dtk -> {err}")
        continue
    try:
        sesi, err_struktur = parse_llm_output(text)
        valid, err_aturan = validate_sessions(sesi, student, now, slots)
        print(f"{m}: {dt:.1f} dtk | sesi {len(sesi)} | lolos aturan {len(valid)} | ditolak {len(err_struktur) + len(err_aturan)}")
        for e in (err_struktur + err_aturan)[:3]:
            print("   -", e)
        if valid:
            print("   contoh alasan:", valid[0].reason)
    except ValueError as e:
        print(f"{m}: {dt:.1f} dtk | output bukan JSON valid: {e}")