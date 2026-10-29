"""Diagnosis LLM: jalankan dari folder stoodify-ai ->  python tes_llm.py
Tes 1: panggilan kecil per model (cek key, base URL, nama model, dan kecepatan dasar).
Tes 2: prompt jadwal sungguhan dari contoh_payload.json (cek waktu dan kevalidan hasil)."""
import json
import time

from llm import build_prompt, chat, get_api_key, get_base_url, get_models, load_env
from adapter import adapt_request
from scheduler import fallback_schedule
from slots import find_free_slots
from validator import parse_llm_output, validate_sessions

load_env()
if not get_api_key():
    raise SystemExit("LLM_API_KEY belum ada di .env")

models = get_models()
print(f"base URL: {get_base_url()}\n")


def panggil(model, prompt, json_mode=True):
    t0 = time.time()
    try:
        return time.time() - t0, chat(model, prompt, json_mode, timeout=60), None
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