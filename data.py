"""Langkah 1 - Dataset buatan sementara (meniru tabel PRD: user_preferences,
schedules, activities, tasks). Waktu 'sekarang' dibuat tetap agar hasil konsisten."""
from datetime import datetime

# Senin, 5 Oktober 2026 pukul 08:00
NOW = datetime(2026, 10, 5, 8, 0)

STUDENT = {
    "name": "Kukuh",
    "preferences": {
        "start_time": "15:00",
        "end_time": "21:00",
        "session_duration": 45,          # menit per sesi
        "active_days": ["mon", "tue", "wed", "thu", "fri", "sat"],
    },
    # Jadwal sekolah mingguan (tabel schedules)
    "schedules": [
        {"day": "mon", "start": "07:00", "end": "16:00", "title": "Sekolah"},
        {"day": "tue", "start": "07:00", "end": "15:30", "title": "Sekolah"},
        {"day": "wed", "start": "07:00", "end": "15:30", "title": "Sekolah"},
        {"day": "thu", "start": "07:00", "end": "16:00", "title": "Sekolah"},
        {"day": "fri", "start": "07:00", "end": "14:30", "title": "Sekolah"},
    ],
    # Kegiatan rutin (tabel activities)
    "activities": [
        {"day": "wed", "start": "16:00", "end": "17:30", "title": "Ekskul DKV"},
        {"day": "fri", "start": "15:00", "end": "16:30", "title": "Ekskul"},
        {"day": "sat", "start": "08:00", "end": "12:00", "title": "Kegiatan akhir pekan"},
        # istirahat & makan malam setiap hari
        *[{"day": d, "start": "18:00", "end": "19:00", "title": "Makan malam & istirahat"}
          for d in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]],
    ],
    # type: ujian | proyek | tugas | baca_materi
    # difficulty 1-5, duration = estimasi total menit, progress 0-100
    "tasks": [
        {"id": 1, "title": "Laporan Konfigurasi Jaringan", "subject": "Jaringan",
         "type": "proyek", "deadline": "2026-10-07", "difficulty": 4, "duration": 180, "progress": 10},
        {"id": 2, "title": "Latihan Soal Basis Data", "subject": "Basis Data",
         "type": "tugas", "deadline": "2026-10-06", "difficulty": 2, "duration": 45, "progress": 80},
        {"id": 3, "title": "Persiapan Ujian Matematika", "subject": "Matematika",
         "type": "ujian", "deadline": "2026-10-10", "difficulty": 5, "duration": 240, "progress": 0},
        {"id": 4, "title": "Baca Bab 3 Sistem Operasi", "subject": "Sistem Operasi",
         "type": "baca_materi", "deadline": "2026-10-20", "difficulty": 2, "duration": 40, "progress": 0},
        {"id": 5, "title": "Proyek Aplikasi Web Kelompok", "subject": "Pemrograman Web",
         "type": "proyek", "deadline": "2026-10-25", "difficulty": 4, "duration": 360, "progress": 15},
        {"id": 6, "title": "Esai Bahasa Indonesia", "subject": "B. Indonesia",
         "type": "tugas", "deadline": "2026-10-09", "difficulty": 3, "duration": 90, "progress": 30},
        {"id": 7, "title": "Tugas Desain Poster (DKV)", "subject": "DKV",
         "type": "tugas", "deadline": "2026-10-04", "difficulty": 3, "duration": 60, "progress": 40},
        {"id": 8, "title": "Rangkum Materi Bahasa Inggris", "subject": "B. Inggris",
         "type": "baca_materi", "deadline": "2026-10-12", "difficulty": 1, "duration": 30, "progress": 0},
    ],
}
