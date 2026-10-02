"""Tes jalur AI dengan Gemini PALSU (tanpa internet/key). Memastikan validasi dan fallback bekerja."""
import json
import time
import pytest
import llm
from data import STUDENT
from llm import ai_schedule
from scheduler import fallback_schedule
from tests.helpers import NOW, session_hits_busy
from validator import parse_llm_output


@pytest.fixture(autouse=True)
def bersihkan_cache():
    llm._cache.clear()


def ai_json_valid():
    """Output 'Gemini' yang benar: pakai jadwal fallback sebagai contoh."""
    sesi = [{"task_id": s["task_id"], "date": s["date"], "start_time": s["start_time"],
             "end_time": s["end_time"], "target_progress": s["target_progress"],
             "reason": "Deadline dekat dan tugas ini cukup sulit."}
            for s in fallback_schedule(STUDENT, NOW)["sessions"]]
    return json.dumps({"sessions": sesi})


def test_output_valid_dipakai_dan_bersumber_gemini():
    r = ai_schedule(STUDENT, NOW, call_fn=lambda p: ai_json_valid())
    assert r["source"] == "gemini" and r["sessions"]
    assert all(s["source"] == "gemini" for s in r["sessions"])
    assert not any(session_hits_busy(s, STUDENT) for s in r["sessions"])


def test_json_dalam_code_fence_tetap_terbaca():
    r = ai_schedule(STUDENT, NOW, call_fn=lambda p: "```json\n" + ai_json_valid() + "\n```")
    assert r["source"] == "gemini"


def test_alias_recommended_date_diterima():
    teks = ai_json_valid().replace('"date"', '"recommended_date"')
    sesi, err = parse_llm_output(teks)
    assert sesi and not err


def test_json_rusak_jatuh_ke_fallback():
    r = ai_schedule(STUDENT, NOW, call_fn=lambda p: "maaf, ini jadwalnya: {sessions: [")
    assert r["source"] == "fallback" and "tidak valid" in r["fallback_reason"]
    assert r["sessions"]  # jadwal tetap ada


def test_sesi_di_jam_sekolah_ditolak_semua_lalu_fallback():
    # Senin 5 Okt, 08:00-08:45 = jam sekolah
    bad = json.dumps({"sessions": [{"task_id": 1, "date": "2026-10-05", "start_time": "08:00",
                                    "end_time": "08:45", "target_progress": 30, "reason": "Belajar pagi saja."}]})
    r = ai_schedule(STUDENT, NOW, call_fn=lambda p: bad)
    assert r["source"] == "fallback"


def test_sebagian_sesi_buruk_dibuang_sisanya_dipakai():
    data = json.loads(ai_json_valid())
    data["sessions"].append({"task_id": 1, "date": "2026-10-05", "start_time": "08:00",
                             "end_time": "08:45", "target_progress": 90, "reason": "Pagi hari saja."})
    r = ai_schedule(STUDENT, NOW, call_fn=lambda p: json.dumps(data))
    assert r["source"] == "gemini" and len(r["dropped"]) == 1
    assert not any(session_hits_busy(s, STUDENT) for s in r["sessions"])


def test_melewati_deadline_ditolak():
    # tugas 2 deadline 6 Okt; sesi 9 Okt (durasi 15 menit = tidak melebihi kebutuhan)
    bad = json.dumps({"sessions": [{"task_id": 2, "date": "2026-10-09", "start_time": "17:00",
                                    "end_time": "17:15", "target_progress": 100, "reason": "Sudah lewat deadline."}]})
    from validator import validate_sessions
    from slots import find_free_slots
    sesi, _ = parse_llm_output(bad)
    valid, errors = validate_sessions(sesi, STUDENT, NOW, find_free_slots(STUDENT, NOW))
    assert not valid and "melewati deadline" in errors[0]
    assert ai_schedule(STUDENT, NOW, call_fn=lambda p: bad)["source"] == "fallback"


def test_sesi_bertabrakan_ditolak():
    s = {"task_id": 1, "date": "2026-10-05", "start_time": "16:00", "end_time": "16:45",
         "target_progress": 30, "reason": "Deadline dekat sekali."}
    dup = dict(s, task_id=3)
    sesi, _ = parse_llm_output(json.dumps({"sessions": [s, dup]}))
    from validator import validate_sessions
    from slots import find_free_slots
    valid, errors = validate_sessions(sesi, STUDENT, NOW, find_free_slots(STUDENT, NOW))
    assert len(valid) == 1 and "bertabrakan" in errors[0]


def test_timeout_jatuh_ke_fallback():
    def lambat(p):
        time.sleep(1.5)
        return ai_json_valid()
    t0 = time.time()
    r = ai_schedule(STUDENT, NOW, call_fn=lambat, timeout=0.2)
    assert r["source"] == "fallback" and "tidak merespons" in r["fallback_reason"]
    assert time.time() - t0 < 1.0


def test_error_api_jatuh_ke_fallback():
    def error(p):
        raise RuntimeError("429 kuota habis")
    r = ai_schedule(STUDENT, NOW, call_fn=error)
    assert r["source"] == "fallback" and "429" in r["fallback_reason"]


def test_tanpa_api_key_tidak_memanggil_gemini(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    r = ai_schedule(STUDENT, NOW)
    assert r["source"] == "fallback" and "API_KEY" in r["fallback_reason"]


def test_cache_menghemat_panggilan():
    n = {"c": 0}
    def hitung(p):
        n["c"] += 1
        return ai_json_valid()
    ai_schedule(STUDENT, NOW, call_fn=hitung)
    ai_schedule(STUDENT, NOW, call_fn=hitung)
    assert n["c"] == 1


def test_prompt_memuat_slot_dan_tugas_tapi_tanpa_data_pribadi_lain():
    from slots import find_free_slots
    prompt = llm.build_prompt(STUDENT, NOW, fallback_schedule(STUDENT, NOW)["scores"],
                              find_free_slots(STUDENT, NOW))
    assert "SLOT KOSONG" in prompt and "Laporan Konfigurasi Jaringan" in prompt
    assert STUDENT["name"] not in prompt   # nama siswa tidak perlu dikirim ke LLM
