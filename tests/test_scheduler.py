import random
from datetime import datetime
from scheduler import fallback_schedule
from slots import to_min, DAYS
from data import STUDENT
from priority import deadline_dt
from tests.helpers import NOW, make_student, make_task, overlaps, session_hits_busy


def fmt_dt(date, hhmm):
    return datetime.strptime(f"{date} {hhmm}", "%Y-%m-%d %H:%M")


def check_invariants(student, now=NOW):
    res = fallback_schedule(student, now)
    sessions = res["sessions"]
    p = student["preferences"]
    by_id = {t["id"]: t for t in student["tasks"]}
    for s in sessions:
        # tidak di jam sekolah / kegiatan rutin
        assert not session_hits_busy(s, student), s
        # di dalam jam belajar
        assert to_min(s["start_time"]) >= to_min(p["start_time"])
        assert to_min(s["end_time"]) <= to_min(p["end_time"])
        # tidak melewati deadline (kecuali tugas yang memang sudah lewat)
        t = by_id[s["task_id"]]
        if deadline_dt(t) > now:
            assert fmt_dt(s["date"], s["end_time"]) <= deadline_dt(t), s
        # tidak sebelum waktu sekarang
        assert fmt_dt(s["date"], s["start_time"]) >= now.replace(second=0)
        # reason wajib ada
        assert s["reason"].strip()
        assert 0 <= s["target_progress"] <= 100
    # antar sesi tidak bertabrakan
    for i, a in enumerate(sessions):
        for b in sessions[i + 1:]:
            if a["date"] == b["date"]:
                assert not overlaps(to_min(a["start_time"]), to_min(a["end_time"]),
                                    to_min(b["start_time"]), to_min(b["end_time"]))
    # tugas selesai tidak dijadwalkan; total menit tidak jauh melebihi kebutuhan
    for t in student["tasks"]:
        got = sum(s["duration"] for s in sessions if s["task_id"] == t["id"])
        if t["progress"] >= 100:
            assert got == 0
        else:
            need = round(t["duration"] * (1 - t["progress"] / 100))
            assert got <= need + 15
    return res


def test_data_buatan_memenuhi_semua_aturan():
    check_invariants(STUDENT)


def test_target_progres_naik_per_tugas():
    res = fallback_schedule(STUDENT, NOW)
    for t in STUDENT["tasks"]:
        urut = [s["target_progress"] for s in res["sessions"] if s["task_id"] == t["id"]]
        assert urut == sorted(urut)


def test_peringatan_jika_waktu_tidak_cukup():
    st = make_student(tasks=[make_task(id=1, title="Raksasa", duration=2000,
                                       deadline="2026-10-06", type="ujian")])
    res = check_invariants(st)
    assert res["warnings"] and "Raksasa" in res["warnings"][0]


def test_tanpa_slot_tidak_ada_sesi_dan_ada_peringatan():
    penuh = [{"day": d, "start": "07:00", "end": "21:00", "title": "Penuh"}
             for d in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]]
    st = make_student(tasks=[make_task(id=1)], schedules=penuh)
    res = fallback_schedule(st, NOW)
    assert res["sessions"] == [] and res["warnings"]


def test_tugas_lewat_deadline_dijadwalkan_lebih_dulu():
    st = make_student(tasks=[
        make_task(id=1, deadline="2026-10-07", type="ujian", difficulty=5, duration=120),
        make_task(id=2, deadline="2026-10-03", difficulty=1, duration=30),  # sudah lewat
    ])
    res = fallback_schedule(st, NOW)
    assert res["sessions"][0]["task_id"] == 2


def test_tugas_prioritas_tinggi_dapat_slot_paling_awal():
    st = make_student(tasks=[
        make_task(id=1, deadline="2026-10-20", type="baca_materi", difficulty=1, duration=45),
        make_task(id=2, deadline="2026-10-06", type="ujian", difficulty=5, duration=45),
    ])
    res = fallback_schedule(st, NOW)
    assert res["sessions"][0]["task_id"] == 2


def test_hasil_sama_untuk_input_sama():
    assert fallback_schedule(STUDENT, NOW) == fallback_schedule(STUDENT, NOW)


def test_data_acak_berseed_memenuhi_semua_aturan():
    rnd = random.Random(2026)
    for n in range(150):
        schedules, activities = [], []
        for d in DAYS:
            if rnd.random() < 0.7:
                a = rnd.randint(6, 10) * 60
                schedules.append({"day": d, "start": f"{a // 60:02d}:00",
                                  "end": f"{(a + rnd.randint(4, 9) * 60) // 60 % 24:02d}:{rnd.choice(['00', '30'])}",
                                  "title": "Sekolah"})
            if rnd.random() < 0.5:
                h = rnd.randint(15, 19)
                activities.append({"day": d, "start": f"{h:02d}:00", "end": f"{h + 1:02d}:30", "title": "Ekskul"})
        # buang jadwal yang end-nya "wrap" melewati tengah malam / sebelum start
        schedules = [s for s in schedules if to_min(s["end"]) > to_min(s["start"])]
        tasks = [make_task(id=i, type=rnd.choice(["ujian", "proyek", "tugas", "baca_materi"]),
                           deadline=f"2026-10-{rnd.randint(3, 28):02d}",
                           difficulty=rnd.randint(1, 5), duration=rnd.randint(15, 400),
                           progress=rnd.choice([0, 0, 10, 30, 60, 90, 100]))
                 for i in range(1, rnd.randint(2, 10))]
        st = make_student(tasks=tasks, schedules=schedules, activities=activities,
                          session_duration=rnd.choice([30, 45, 60]))
        check_invariants(st)
