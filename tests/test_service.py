import json
import time

import pytest
from fastapi.testclient import TestClient

import llm
import service
from adapter import adapt_request
from scheduler import fallback_schedule
from tests.helpers import session_hits_busy
from tests.payloads import contoh_payload

BACKEND_KEYS = {"task_id", "recommended_date", "start_time", "end_time", "duration",
                "target_progress", "priority", "reason"}
H = {"Authorization": "Bearer rahasia"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "rahasia")
    monkeypatch.delenv("ALLOW_NO_AUTH", raising=False)
    llm._cache.clear()
    return TestClient(service.app)


def json_llm_dari_fallback(payload):
    student, now, _, _ = adapt_request(payload)
    sesi = [{"task_id": s["task_id"], "date": s["date"], "start_time": s["start_time"],
             "end_time": s["end_time"], "target_progress": s["target_progress"],
             "reason": "Deadline dekat dan tugas ini cukup sulit."}
            for s in fallback_schedule(student, now)["sessions"]]
    return json.dumps({"sessions": sesi})


def test_health_tanpa_auth(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_tanpa_header_ditolak(client):
    assert client.post("/schedule", json=contoh_payload()).status_code == 401


def test_key_salah_ditolak(client):
    r = client.post("/schedule", json=contoh_payload(), headers={"Authorization": "Bearer salah"})
    assert r.status_code == 401


def test_key_server_belum_diatur_ditolak(client, monkeypatch):
    monkeypatch.delenv("AI_API_KEY", raising=False)
    assert client.post("/schedule", json=contoh_payload(), headers=H).status_code == 503


def test_mode_lokal_tanpa_auth_hanya_jika_diizinkan(client, monkeypatch):
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.setenv("ALLOW_NO_AUTH", "true")
    assert client.post("/schedule", json=contoh_payload()).status_code == 200


def test_body_bukan_json(client):
    r = client.post("/schedule", content="bukan json", headers=H)
    assert r.status_code == 400


def test_date_salah_422(client):
    assert client.post("/schedule", json=contoh_payload(date="besok"), headers=H).status_code == 422


def test_tanpa_tugas_aktif_balasan_kosong_tapi_sah(client):
    r = client.post("/schedule", json=contoh_payload(tasks=[]), headers=H)
    assert r.status_code == 200 and r.json()["sessions"] == []


def test_tanpa_key_llm_memakai_fallback_dengan_format_backend(client):
    body = client.post("/schedule", json=contoh_payload(), headers=H).json()
    assert body["source"] == "fallback" and "LLM_API_KEY" in body["fallback_reason"]
    assert body["sessions"] and all(set(s) == BACKEND_KEYS for s in body["sessions"])


def test_sesi_balasan_tidak_bentrok_dengan_jadwal(client):
    payload = contoh_payload()
    sesi = client.post("/schedule", json=payload, headers=H).json()["sessions"]
    student, _, _, _ = adapt_request(payload)
    cek = [{"date": s["recommended_date"], "start_time": s["start_time"], "end_time": s["end_time"]} for s in sesi]
    assert cek and not any(session_hits_busy(s, student) for s in cek)


def test_llm_palsu_dipakai_jika_valid(client, monkeypatch):
    payload = contoh_payload()
    monkeypatch.setenv("LLM_API_KEY", "palsu")
    monkeypatch.setattr(llm, "call_llm", lambda prompt: json_llm_dari_fallback(payload))
    body = client.post("/schedule", json=payload, headers=H).json()
    assert body["source"] == "ai" and body["sessions"]


def test_llm_lambat_dijawab_fallback_sebelum_batas_backend(client, monkeypatch):
    def lambat(prompt):
        time.sleep(2)
        return "{}"
    monkeypatch.setenv("LLM_API_KEY", "palsu")
    monkeypatch.setenv("AI_TIMEOUT_SECONDS", "0.3")
    monkeypatch.setattr(llm, "call_llm", lambat)
    t0 = time.time()
    body = client.post("/schedule", json=contoh_payload(), headers=H).json()
    assert body["source"] == "fallback" and "tidak merespons" in body["fallback_reason"]
    assert time.time() - t0 < 1.5 and body["sessions"]


def test_prompt_llm_tidak_memuat_catatan_pribadi(client, monkeypatch):
    dikirim = []
    payload = contoh_payload()

    def tangkap(prompt):
        dikirim.append(prompt)
        return json_llm_dari_fallback(payload)

    monkeypatch.setenv("LLM_API_KEY", "palsu")
    monkeypatch.setattr(llm, "call_llm", tangkap)
    client.post("/schedule", json=payload, headers=H)
    assert dikirim
    assert "catatan pribadi" not in dikirim[0] and "created_at" not in dikirim[0]
    assert "Laporan Konfigurasi Jaringan" in dikirim[0]


def test_tugas_ditunda_dan_selesai_tidak_dijadwalkan(client):
    sesi = client.post("/schedule", json=contoh_payload(), headers=H).json()["sessions"]
    assert {s["task_id"] for s in sesi}.isdisjoint({5, 6})
