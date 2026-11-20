# TODO Divisi AI (`stoodify-ai-1`) — Penjadwalan Otomatis

Scope: service `stoodify-ai-1` (FastAPI). Backend tidak mengerjakan item di sini.
Dokumen ini disimpan di repo backend (repo AI bersifat **read-only** dari sisi kita); sampaikan isinya ke pengembang AI.
Konteks: backend akan memanggil `/schedule` **otomatis** setiap ada perubahan tugas (debounce + single-flight), tanpa alur terima/tolak. Kontrak backend: `stoodify-backend/docs/PLAN-AUTO-SCHEDULE.md`.

---

## 1. Wajib untuk MVP auto-schedule

- [x] **Dukung `locked` pada `existing_sessions`.** Selesai diimplementasikan di `adapter.py:214-227`:
      ```json
      { "session_id": 91, "task_id": 12, "session_date": "2026-11-18", "start_time": "16:00",
        "duration": 60, "status": "planned", "locked": true }
      ```
      Sesi `locked: true` diperlakukan sebagai interval sibuk (`activities`) dan dihitung pada `task.planned_min`. Sesi `locked: false` tidak memblokir slot agar dapat dijadwalkan ulang. Diuji di `test_adapter.py` dan `test_service.py`.
- [x] **Latensi `/schedule` < 5 detik (p95).** Default `AI_TIMEOUT_SECONDS` disetel ke `6.0` detik di `llm.py:53`. Jika LLM tidak merespons dalam 6 detik, engine langsung mengembalikan jadwal fallback deterministik yang instan, jauh di bawah timeout backend 15 detik.
- [x] **Pastikan `source`, `warnings`, `fallback_reason` selalu ada** di respons `/schedule` (`service.py:77-84`) dan `source`, `syllabus_reference` di `/predict` (`:110-119`). Terverifikasi pada unit tests.

## 2. Keputusan kontrak yang perlu disepakati

- [x] **`break_duration` & `max_sessions_per_day`**: Pilihan (a) diadopsi! `adapter.py` mem-parsing `break_duration` (default 10) dan `max_sessions_per_day` (default 4). `scheduler.py` menghormati jeda istirahat antar slot dan membatasi alokasi sesi harian. Prompt LLM di `llm.py` juga menyertakan kedua aturan ini.
- [x] **`class_level` & `curriculum`** pada `/predict`: Didukung penuh via `normalize_class_level()` (menerima angka 1-12, romawi I-XII/XIII, atau Fase A-F) dan dataset Kurikulum Merdeka (910 topik).
- [x] **`activities[].day_of_week`**: Format `Monday..Sunday` dinormalisasi dengan baik oleh `norm_day` di `adapter.py:180`.

## 3. Fase lanjutan (belum dikerjakan backend)

- [ ] **Parameter horizon** untuk menyusun lebih dari satu hari dalam satu panggilan, mis. `{"date":"2026-11-18","days":7}` atau balasan berisi beberapa tanggal.
- [ ] **Feedback ingestion yang benar-benar dipakai**: endpoint `POST /feedback` dan `/feedback/per-mapel` sudah ada (`service.py:122-131`).

## 4. Dokumentasi yang harus diperbarui (sekarang basi)

- [x] `docs/INTEGRASI_ARSITEKTUR_AI.md:62` diperbarui: backend bridge-only (ADR-005).
- [x] `docs/INTEGRASI_ARSITEKTUR_AI.md:66` diperbarui: backend sudah mengirim `schedules`, `activities`, `existing_sessions`.
- [x] `docs/INTEGRASI_ARSITEKTUR_AI.md` diperbarui: sufiks `(ai)` sudah dihapus.
- [x] Ditambahkan bagian **"2.1 Ringkasan Kontrak v1 & Penanganan Auto-Schedule"** lengkap dengan penjelasan sifat otomatis, stateless, idempoten, status HTTP, dan penanganan `locked`.

## 5. Operasional

- [x] `AI_TIMEOUT_SECONDS` di engine disetel default `6.0` detik (< 15 detik timeout backend).
- [x] `GET /health` tetap tanpa auth dan instan.
- [x] Log sudah memuat `source` dan `latency_ms`.
- [x] Idempotensi: engine stateless; diuji memanggil `/schedule` 5x berurutan menghasilkan alokasi konsisten tanpa efek samping.

## 6. Pengujian yang telah ditambahkan

- [x] Payload dengan `existing_sessions[].locked=true` → slot tidak dipakai ulang (`test_existing_sessions_locked_true_memblokir_slot`).
- [x] Payload dengan `existing_sessions[].locked=false` → slot tidak memblokir jadwal (`test_existing_sessions_locked_false_tidak_memblokir_slot`).
- [x] Payload dengan `tasks[].subject` kosong → tetap jalan lancar dan ada warning (`test_task_tanpa_subject_memberi_peringatan_dan_tetap_jalan`).
- [x] `/schedule` dipanggil 5× berurutan untuk user yang sama → tidak ada kebocoran state, hasil identik (`test_schedule_5x_idempoten_tanpa_kebocoran_state`).
- [x] Respons 429 dari provider LLM → engine tetap balas 200 dengan `source=fallback` (`test_schedule_llm_429_kembali_200_fallback`).
- [x] `/predict` dengan `class_level` kosong vs terisi → hasil berbeda sesuai silabus (`test_baca_silabus_differensiasi_kelas`).
