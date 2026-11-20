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


def test_predict_tanpa_auth_ditolak(client):
    payload = {"subject": "Matematika", "difficulty": 4, "history": []}
    assert client.post("/predict", json=payload).status_code == 401


def test_predict_dengan_auth_sukses(client):
    payload = {
        "subject": "Matematika",
        "difficulty": 4,
        "history": [
            {"title": "PR Komposisi Fungsi", "material_name": "Komposisi Fungsi", "deadline": "2026-11-01"}
        ]
    }
    r = client.post("/predict", json=payload, headers=H)
    assert r.status_code == 200
    data = r.json()
    assert "predicted_topic" in data
    assert "confidence" in data
    assert "reason" in data
    assert "prerequisites" in data
    assert "preparation_suggestion" in data
    assert data["source"] in ("ai", "fallback")


def test_predict_tanpa_jenjang_kelas_10_12_default_sma(client):
    payload = {"subject": "Matematika", "difficulty": 4, "class_level": "11", "history": []}
    r = client.post("/predict", json=payload, headers=H)
    assert r.status_code == 200
    data = r.json()
    assert data["syllabus_reference"] == "available"
    assert data["predicted_topic"] == "Bilangan Kompleks"

    payload_smk = dict(payload, jenjang="SMK")
    data_smk = client.post("/predict", json=payload_smk, headers=H).json()
    assert data_smk["predicted_topic"] != data["predicted_topic"]


def test_predict_jenjang_smk_meneruskan_filter_smk(client):
    payload = {
        "subject": "Matematika",
        "difficulty": 4,
        "class_level": "11",
        "jenjang": "SMK",
        "history": [],
    }
    r = client.post("/predict", json=payload, headers=H)
    assert r.status_code == 200
    data = r.json()
    assert data["syllabus_reference"] == "available"
    assert data["predicted_topic"] == "Fungsi Komposisi dan Fungsi Invers"


def test_predict_mapel_vokasi_smk_silabus_unavailable(client):
    payload = {
        "subject": "Pengembangan Perangkat Lunak dan Gim (PPLG)",
        "difficulty": 4,
        "class_level": "11",
        "jenjang": "SMK",
        "history": [{"title": "Projek Web", "material_name": "Pemrograman Web Frontend"}],
    }
    r = client.post("/predict", json=payload, headers=H)
    assert r.status_code == 200
    data = r.json()
    assert data["syllabus_reference"] == "unavailable"
    assert data["source"] == "fallback"


@pytest.mark.parametrize("jenjang", ["SMA", "SMK", "SD", "SMP"])
def test_predict_jenjang_valid_diterima(client, jenjang):
    payload = {"subject": "Matematika", "difficulty": 3, "jenjang": jenjang}
    assert client.post("/predict", json=payload, headers=H).status_code == 200


@pytest.mark.parametrize("jenjang", ["sma", "kuliah", "MA", "", 10])
def test_predict_jenjang_tidak_valid_ditolak_422(client, jenjang):
    payload = {"subject": "Matematika", "difficulty": 3, "jenjang": jenjang}
    assert client.post("/predict", json=payload, headers=H).status_code == 422


def test_predict_jenjang_tidak_mengubah_bentuk_respons(client):
    payload = {"subject": "Matematika", "difficulty": 3, "jenjang": "SMK"}
    data = client.post("/predict", json=payload, headers=H).json()
    assert set(data) == {
        "predicted_topic", "confidence", "reason", "prerequisites",
        "preparation_suggestion", "syllabus_reference", "source", "latency_ms",
    }


def test_feedback_endpoint(client):
    payload = {
        "data_feedback": [
            {"subject": "Matematika", "user_feedback": "accurate"},
            {"subject": "Matematika", "user_feedback": "inaccurate"},
        ]
    }
    r = client.post("/feedback", json=payload, headers=H)
    assert r.status_code == 200
    res = r.json()
    assert res["total_feedback"] == 2
    assert res["akurasi_feedback"] == 50.0


def test_feedback_menyimpan_dan_akurasi_terbaca(client, tmp_path, monkeypatch):
    """POST /feedback lalu GET /feedback/akurasi harus mengembalikan data yang sesuai."""
    import feedback as fb_module
    monkeypatch.setattr(fb_module, "FEEDBACK_HISTORY_PATH", tmp_path / "fb.json")

    client.post("/feedback", json={"data_feedback": [
        {"subject": "Fisika", "user_feedback": "accurate"},
        {"subject": "Fisika", "user_feedback": "accurate"},
        {"subject": "Fisika", "user_feedback": "inaccurate"},
    ]}, headers=H)

    r = client.get("/feedback/akurasi", headers=H)
    assert r.status_code == 200
    hasil = r.json()
    assert "Fisika" in hasil
    assert hasil["Fisika"]["total"] == 3
    assert abs(hasil["Fisika"]["akurasi"] - 66.67) < 0.01


def test_feedback_akurasi_filter_subject(client, tmp_path, monkeypatch):
    """GET /feedback/akurasi?subject=Kimia hanya mengembalikan data Kimia."""
    import feedback as fb_module
    monkeypatch.setattr(fb_module, "FEEDBACK_HISTORY_PATH", tmp_path / "fb.json")

    client.post("/feedback", json={"data_feedback": [
        {"subject": "Kimia", "user_feedback": "accurate"},
        {"subject": "Biologi", "user_feedback": "inaccurate"},
    ]}, headers=H)

    r = client.get("/feedback/akurasi?subject=Kimia", headers=H)
    assert r.status_code == 200
    hasil = r.json()
    # Respons satu mapel: langsung dict, bukan nested
    assert hasil["total"] == 1
    assert hasil["akurasi"] == 100.0


def test_schedule_dengan_locked_session_tidak_ditimpa(client):
    p = contoh_payload(existing_sessions=[
        {
            "id": 99,
            "task_id": 1,
            "session_date": "2026-10-06",
            "start_time": "15:00",
            "duration": 60,
            "status": "planned",
            "locked": True,
        }
    ])
    r = client.post("/schedule", json=p, headers=H)
    assert r.status_code == 200
    sesi = r.json()["sessions"]
    # Tidak ada sesi baru yang tumpang tindih dengan 15:00-16:00 pada 2026-10-06
    for s in sesi:
        if s["recommended_date"] == "2026-10-06":
            assert not (s["start_time"] < "16:00" and s["end_time"] > "15:00")


def test_schedule_5x_idempoten_tanpa_kebocoran_state(client):
    p = contoh_payload()
    hasil_pertama = client.post("/schedule", json=p, headers=H).json()
    assert hasil_pertama["sessions"]
    for _ in range(4):
        ulang = client.post("/schedule", json=p, headers=H).json()
        assert len(ulang["sessions"]) == len(hasil_pertama["sessions"])
        assert [s["task_id"] for s in ulang["sessions"]] == [s["task_id"] for s in hasil_pertama["sessions"]]


def test_schedule_llm_429_kembali_200_fallback(client, monkeypatch):
    def throw_429(prompt):
        raise RuntimeError("429 Too Many Requests: quota exceeded")

    monkeypatch.setenv("LLM_API_KEY", "palsu")
    monkeypatch.setattr(llm, "call_llm", throw_429)

    r = client.post("/schedule", json=contoh_payload(), headers=H)
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "fallback"
    assert "429" in body["fallback_reason"]
    assert len(body["sessions"]) > 0


def test_schedule_respons_mengandung_horizon_days_default(client):
    """Response /schedule harus mengandung horizon_days (default 7)."""
    r = client.post("/schedule", json=contoh_payload(), headers=H)
    assert r.status_code == 200
    body = r.json()
    assert "horizon_days" in body
    assert body["horizon_days"] == 7


def test_schedule_days_dikembalikan_di_respons(client):
    """Jika payload mengandung days=3, respons horizon_days == 3."""
    p = contoh_payload()
    p["days"] = 3
    r = client.post("/schedule", json=p, headers=H)
    assert r.status_code == 200
    assert r.json()["horizon_days"] == 3


def test_schedule_days_lebih_dari_14_diklem(client):
    """days=99 diklem ke 14 dan dikembalikan di respons."""
    p = contoh_payload()
    p["days"] = 99
    r = client.post("/schedule", json=p, headers=H)
    assert r.status_code == 200
    assert r.json()["horizon_days"] == 14

