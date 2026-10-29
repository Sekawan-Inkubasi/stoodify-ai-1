import json
import os
from datetime import datetime

import pytest

from adapter import PayloadError, adapt_request, norm_day, parse_active_days, to_backend_sessions
from scheduler import fallback_schedule
from slots import find_free_slots, to_min
from tests.helpers import session_hits_busy
from tests.payloads import ROOT, contoh_payload


def adapt(**over):
    return adapt_request(contoh_payload(**over))


def by_id(student):
    return {t["id"]: t for t in student["tasks"]}


def test_jenis_tugas_backend_dipetakan_ke_engine():
    t = by_id(adapt()[0])
    assert (t[1]["type"], t[2]["type"], t[3]["type"], t[4]["type"]) == ("proyek", "tugas", "ujian", "baca_materi")


def test_deadline_utc_dikonversi_ke_wib():
    # 16:59 UTC = 23:59 WIB
    assert by_id(adapt()[0])[2]["deadline_at"] == datetime(2026, 10, 6, 23, 59)


def test_zona_waktu_tidak_dikenal_memakai_wib():
    student = adapt(timezone="Tidak/Ada")[0]
    assert by_id(student)[2]["deadline_at"] == datetime(2026, 10, 6, 23, 59)


def test_tugas_selesai_dan_ditunda_dikeluarkan():
    student, _, _, meta = adapt()
    assert set(by_id(student)) == {1, 2, 3, 4}
    assert meta["snoozed_skipped"] == 1


@pytest.mark.parametrize("nilai,hasil", [
    ("Monday", "mon"), ("senin", "mon"), (1, "mon"), ("3", "wed"),
    ("Jum'at", "fri"), ("Sunday", "sun"), ("0", "sun"), (7, "sun"), ("xyz", None), (None, None),
])
def test_nama_hari_berbagai_format(nilai, hasil):
    assert norm_day(nilai) == hasil


def test_active_days_angka_dan_nama():
    assert parse_active_days("1,2,3,4,5") == ["mon", "tue", "wed", "thu", "fri"]
    assert parse_active_days(["Senin", "rabu"]) == ["mon", "wed"]
    assert parse_active_days(None) == []


def test_sesi_planned_memblokir_slot_dan_mengurangi_kebutuhan():
    student, now, _, _ = adapt()
    assert by_id(student)[3]["planned_min"] == 45
    for s in find_free_slots(student, now):
        if s["date"] == "2026-10-06":
            assert not (s["start"] < to_min("16:45") and to_min("16:00") < s["end"])


def test_sesi_lampau_dan_non_planned_diabaikan():
    lama = {"task_id": 3, "session_date": "2026-10-04", "start_time": "16:00", "duration": 45, "status": "planned"}
    selesai = {"task_id": 3, "session_date": "2026-10-06", "start_time": "17:00", "duration": 45, "status": "completed"}
    student = adapt(existing_sessions=[lama, selesai])[0]
    assert by_id(student)[3]["planned_min"] == 0


def test_data_opsional_hilang_memberi_peringatan():
    _, _, warnings, _ = adapt(schedules=None, activities=None, existing_sessions=None)
    teks = " ".join(warnings)
    assert "jadwal sekolah" in teks and "kegiatan rutin" in teks and "sesi yang sudah ada" in teks


def test_kegiatan_harian_diperluas_ke_semua_hari():
    student = adapt()[0]
    assert sum(1 for a in student["activities"] if a.get("title") == "Makan malam") == 7


def test_kegiatan_tanpa_hari_dianggap_tiap_hari_dengan_peringatan():
    les = {"title": "Les", "start_time": "16:00", "end_time": "17:00"}
    student, _, warnings, _ = adapt(activities=[les])
    assert sum(1 for a in student["activities"] if a["title"] == "Les") == 7
    assert any("tidak punya hari" in w for w in warnings)


def test_kegiatan_sekali_hanya_memblokir_tanggalnya():
    rapat = {"title": "Rapat", "date": "2026-10-08T00:00:00Z", "start_time": "16:00", "end_time": "17:00"}
    student, now, _, _ = adapt(activities=[rapat], schedules=[])
    slots = find_free_slots(student, now)
    hari_h = [s for s in slots if s["date"] == "2026-10-08"]
    minggu_depan = [s for s in slots if s["date"] == "2026-10-15"]
    assert all(not (s["start"] < to_min("17:00") and to_min("16:00") < s["end"]) for s in hari_h)
    assert any(s["start"] <= to_min("16:00") and s["end"] >= to_min("17:00") for s in minggu_depan)


def test_kegiatan_bulanan_tanpa_tanggal_diabaikan():
    x = {"title": "Iuran", "start_time": "16:00", "end_time": "17:00", "recurrence": "monthly"}
    student, _, warnings, _ = adapt(activities=[x])
    assert not any(a["title"] == "Iuran" for a in student["activities"])
    assert any("bulanan" in w for w in warnings)


def test_tanggal_masa_depan_mulai_dari_awal_hari():
    assert adapt(date="2026-10-08")[1] == datetime(2026, 10, 8, 0, 0)


def test_tanggal_lampau_memakai_waktu_sekarang():
    assert adapt(date="2026-10-01")[1] == datetime(2026, 10, 5, 8, 0)


def test_date_tidak_valid_ditolak():
    with pytest.raises(PayloadError):
        adapt(date="05-10-2026")


def test_payload_bukan_objek_ditolak():
    with pytest.raises(PayloadError):
        adapt_request([])


def test_preferensi_kosong_memakai_default():
    student = adapt(preferences={})[0]
    p = student["preferences"]
    assert (p["start_time"], p["end_time"], p["session_duration"]) == ("15:00", "21:00", 60)


def test_jam_belajar_terbalik_memakai_default_dengan_peringatan():
    student, _, warnings, _ = adapt(preferences={"start_time": "21:00", "end_time": "15:00", "session_duration": 45})
    assert student["preferences"]["start_time"] == "15:00" and warnings


def test_format_output_sama_dengan_struct_backend():
    student, now, _, _ = adapt()
    out = to_backend_sessions(fallback_schedule(student, now)["sessions"])
    assert out
    wajib = {"task_id", "recommended_date", "start_time", "end_time", "duration",
             "target_progress", "priority", "reason"}
    assert all(set(s) == wajib for s in out)
    assert all(len(s["recommended_date"]) == 10 and s["duration"] > 0 for s in out)


def test_jadwal_dari_data_backend_tidak_bentrok():
    student, now, _, _ = adapt()
    sesi = fallback_schedule(student, now)["sessions"]
    assert sesi
    assert not any(session_hits_busy(s, student) for s in sesi)
    assert {s["task_id"] for s in sesi} <= {1, 2, 3, 4}
    # sesi planned milik backend (6 Okt 16:00-16:45) tidak ditimpa
    assert not any(s["date"] == "2026-10-06" and to_min(s["start_time"]) < to_min("16:45")
                   and to_min("16:00") < to_min(s["end_time"]) for s in sesi)


def test_contoh_payload_json_sinkron_dan_bisa_dipakai():
    with open(os.path.join(ROOT, "contoh_payload.json"), encoding="utf-8") as f:
        data = json.load(f)
    assert data == contoh_payload()
    assert adapt_request(data)[0]["tasks"]
