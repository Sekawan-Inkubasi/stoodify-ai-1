"""Daftar model yang tersedia di penyedia OpenAI-compatible kamu.
Jalankan: python cek_model.py   (membaca LLM_API_KEY dan LLM_BASE_URL dari .env)"""
import httpx

from llm import get_api_key, get_base_url, load_env

load_env()
if not get_api_key():
    raise SystemExit("LLM_API_KEY belum ada di .env")

r = httpx.get(get_base_url() + "/models",
              headers={"Authorization": f"Bearer {get_api_key()}"}, timeout=30)
if r.status_code >= 400:
    raise SystemExit(f"Gagal ({r.status_code}): {r.text[:200]}")
for m in r.json().get("data", []):
    print(str(m.get("id", "")).replace("models/", ""))
