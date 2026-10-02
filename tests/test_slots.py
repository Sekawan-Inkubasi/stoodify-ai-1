from datetime import datetime
import pytest
from slots import find_free_slots, subtract, to_min, MIN_SLOT
from data import STUDENT
from tests.helpers import NOW, make_student, overlaps, day_key


def test_slot_tidak_menabrak_sekolah_atau_kegiatan():
    for s in find_free_slots(STUDENT, NOW):
        k = day_key(s["date"])
        for item in STUDENT["schedules"] + STUDENT["activities"]:
            if item["day"] == k:
                assert not overlaps(s["start"], s["end"], to_min(item["start"]), to_min(item["end"]))


def test_slot_di_dalam_jam_belajar():
    p = STUDENT["preferences"]
    for s in find_free_slots(STUDENT, NOW):
        assert s["start"] >= to_min(p["start_time"]) and s["end"] <= to_min(p["end_time"])


def test_hari_nonaktif_tidak_ada_slot():
    # 11 Okt 2026 = Minggu, tidak ada di active_days
    assert all(s["date"] != "2026-10-11" for s in find_free_slots(STUDENT, NOW))


def test_hari_penuh_tidak_ada_slot():
    st = make_student(schedules=[{"day": "mon", "start": "07:00", "end": "21:00", "title": "Penuh"}])
    assert all(s["date"] != "2026-10-05" for s in find_free_slots(st, NOW, days_ahead=1))


def test_slot_tepat_di_batas_kegiatan():
    # kegiatan berakhir 16:00 -> slot boleh mulai tepat 16:00
    st = make_student(activities=[{"day": "mon", "start": "15:00", "end": "16:00", "title": "Ekskul"}])
    slots = find_free_slots(st, NOW, days_ahead=1)
    assert slots[0]["start"] == to_min("16:00")


def test_hari_ini_dipotong_dari_waktu_sekarang():
    now = datetime(2026, 10, 5, 17, 10)
    slots = find_free_slots(make_student(), now, days_ahead=1)
    assert slots[0]["start"] == to_min("17:15")  # dibulatkan ke atas 15 menit


def test_slot_terlalu_pendek_dibuang():
    st = make_student(activities=[{"day": "mon", "start": "15:20", "end": "21:00", "title": "Padat"}])
    # sisa 15:00-15:20 = 20 menit < MIN_SLOT
    assert find_free_slots(st, NOW, days_ahead=1) == []
    assert MIN_SLOT > 20


@pytest.mark.parametrize("window,busy,expected", [
    ((900, 1260), [], [(900, 1260)]),
    ((900, 1260), [(960, 1020)], [(900, 960), (1020, 1260)]),
    ((900, 1260), [(800, 1000)], [(1000, 1260)]),
    ((900, 1260), [(900, 1260)], []),
])
def test_subtract(window, busy, expected):
    assert subtract(window, busy) == expected
