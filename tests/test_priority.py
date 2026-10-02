"""Skenario Priority Score. Tes mengecek ATURAN (urutan/logika), bukan angka persis,
agar tidak rusak saat bobot dikalibrasi."""
import random
import pytest
from priority import score_task, score_all, WEIGHTS
from tests.helpers import NOW, make_task


def S(**kw):
    return score_task(make_task(**kw), NOW)["score"]


# --- 1-4: perbandingan dasar ---
def test_01_deadline_besok_mengalahkan_dua_minggu():
    assert S(deadline="2026-10-06") > S(deadline="2026-10-19")


def test_02_mudah_tapi_dekat_mengalahkan_sulit_tapi_jauh():
    dekat_mudah = S(deadline="2026-10-06", difficulty=1, duration=30)
    jauh_sulit = S(deadline="2026-10-18", difficulty=5, duration=240)
    assert dekat_mudah > jauh_sulit


def test_03_progres_80_lebih_rendah_dari_progres_0():
    assert S(progress=80) < S(progress=0)


def test_04_ujian_mengalahkan_baca_materi():
    assert S(type="ujian") > S(type="baca_materi")


# --- 5-6: late risk ---
def test_05_late_risk_aktif_jika_progres_kecil_dan_deadline_dekat():
    r = score_task(make_task(progress=10, deadline="2026-10-06"), NOW)
    assert r["parts"]["late_risk"] == 1.0


@pytest.mark.parametrize("kw", [
    {"progress": 10, "deadline": "2026-10-20"},   # deadline masih jauh
    {"progress": 25, "deadline": "2026-10-06"},   # progres sudah cukup
])
def test_06_late_risk_tidak_aktif(kw):
    assert score_task(make_task(**kw), NOW)["parts"]["late_risk"] == 0.0


# --- 7: deadline lewat ---
def test_07_deadline_lewat_urgensi_maksimum():
    r = score_task(make_task(deadline="2026-10-01"), NOW)
    assert r["parts"]["deadline"] == 1.0
    assert r["days_left"] < 0


# --- 8: banyak deadline di hari sama ---
def test_08_deadline_sama_ditentukan_jenis_dan_kesulitan():
    tasks = [
        make_task(id=1, type="baca_materi", difficulty=1, duration=30, deadline="2026-10-09"),
        make_task(id=2, type="ujian", difficulty=5, duration=180, deadline="2026-10-09"),
        make_task(id=3, type="tugas", difficulty=3, duration=60, deadline="2026-10-09"),
    ]
    urutan = [r["task_id"] for r in score_all(tasks, NOW)]
    assert urutan == [2, 3, 1]


# --- 9: tugas selesai tidak dihitung ---
def test_09_tugas_selesai_diabaikan():
    tasks = [make_task(id=1, progress=100), make_task(id=2, progress=0)]
    assert [r["task_id"] for r in score_all(tasks, NOW)] == [2]


# --- 10: skor naik saat deadline mendekat ---
def test_10_skor_naik_monoton_saat_deadline_mendekat():
    deadlines = ["2026-10-25", "2026-10-18", "2026-10-12", "2026-10-08", "2026-10-06"]
    skor = [S(deadline=d) for d in deadlines]
    assert skor == sorted(skor)
    assert len(set(skor)) == len(skor)


# --- 11: bobot bisa diubah ---
def test_11_bobot_kesulitan_saja_memenangkan_tugas_sulit():
    w = {k: 0.0 for k in WEIGHTS}
    w["difficulty"] = 1.0
    sulit = score_task(make_task(difficulty=5, deadline="2026-10-30"), NOW, w)["score"]
    mudah = score_task(make_task(difficulty=1, deadline="2026-10-06"), NOW, w)["score"]
    assert sulit > mudah


# --- 12: durasi ---
def test_12_durasi_panjang_lebih_urgen_dari_pendek():
    assert S(duration=240) > S(duration=20)


# --- 13: label ---
def test_13_label_prioritas_konsisten_dengan_skor():
    for kw in [{"deadline": "2026-10-06", "type": "ujian", "difficulty": 5, "duration": 240},
               {"deadline": "2026-10-25", "type": "baca_materi", "difficulty": 1, "duration": 20}]:
        r = score_task(make_task(**kw), NOW)
        expected = "high" if r["score"] >= 55 else "medium" if r["score"] >= 35 else "low"
        assert r["priority"] == expected
    assert score_task(make_task(deadline="2026-10-06", type="ujian", difficulty=5, duration=240), NOW)["priority"] == "high"
    assert score_task(make_task(deadline="2026-10-25", type="baca_materi", difficulty=1, duration=20), NOW)["priority"] == "low"


# --- 14: deterministik ---
def test_14_hasil_sama_untuk_input_sama():
    t = make_task(deadline="2026-10-08", difficulty=4, progress=15)
    assert score_task(t, NOW) == score_task(t, NOW)


# --- 15: batas skor pada data acak ---
def test_15_skor_selalu_0_sampai_100_pada_data_acak():
    rnd = random.Random(42)
    for i in range(300):
        t = make_task(id=i, type=rnd.choice(["ujian", "proyek", "tugas", "baca_materi"]),
                      deadline=f"2026-10-{rnd.randint(1, 30):02d}",
                      difficulty=rnd.randint(1, 5), duration=rnd.randint(10, 600),
                      progress=rnd.randint(0, 99))
        s = score_task(t, NOW)["score"]
        assert 0 <= s <= 100


# --- 16: progres makin besar, skor makin kecil ---
def test_16_skor_turun_monoton_saat_progres_naik():
    skor = [S(progress=p) for p in (0, 20, 40, 60, 80)]
    assert skor == sorted(skor, reverse=True)


# --- 17: proyek di atas tugas biasa ---
def test_17_proyek_lebih_penting_dari_tugas_biasa():
    assert S(type="proyek") > S(type="tugas")
