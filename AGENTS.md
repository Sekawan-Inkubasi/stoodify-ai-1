# AGENTS.md — Panduan AI Agent untuk Codebase `stoodify-ai-1`

Dokumen ini adalah **Source of Truth** utama bagi AI Agent maupun developer yang bekerja pada repository `stoodify-ai-1`. Baca dokumen ini sebelum menganalisis atau mengubah kode agar **menghemat token dan context window**, memahami arsitektur sistem, serta mematuhi aturan penulisan file dan konvensi proyek.

---

## 1. Identitas & Gambaran Umum Project

- **Nama Project**: `stoodify-ai-1` (Stoodify AI Engine — Unified AI Specialist 1 & 2).
- **Peran Sistem**: Microservice kecerdasan buatan berbasis Python yang bertindak sebagai mesin inferensi, penjadwal adaptif, prediktor silabus materi, dan asisten belajar interaktif untuk ekosistem **Stoodify**.
- **Posisi dalam Ekosistem Stoodify**:
  ```
  [ stoodify-mobile / apk ]  (Client: React 19 / React Native Expo)
             │
             ▼ (HTTP REST / JWT)
    [ stoodify-backend ]      (Orchestrator: Go Gin + PostgreSQL)
             │
             ▼ (Internal HTTP: Bearer AI_API_KEY, loopback 127.0.0.1:8000)
    [ stoodify-ai-1 ]         (AI Engine: Python FastAPI / Uvicorn)
             │
             ▼ (HTTPS Outbound: OpenAI-compatible API)
  [ LLM Provider (Gemini / OpenAI / Groq / OpenRouter / Ollama) ]
  ```
- **Prinsip Utama**: **Bridge-Only Fail-Safe Architecture**. Backend Go mempercayakan seluruh keputusan penjadwalan dan prediksi ke AI Engine. Jika LLM eksternal mengalami timeout, kehabisan kuota, atau gangguan jaringan, AI Engine **otomatis beralih ke algoritma deterministik lokal (fallback)** dalam hitungan milidetik sehingga backend tidak pernah menerima error 500.

---

## 2. Kegunaan & Masalah yang Diselesaikan

1. **Smart Study Scheduling & Workload Balancing**: Mengatasi prokrastinasi dan *burnout* siswa dengan memprioritaskan tugas multi-faktor dan menyusun sesi belajar adaptif di slot waktu luang tanpa menabrak jam sekolah atau kegiatan rutin.
2. **Material & Topic Prediction ("Curi Start")**: Menganalisis riwayat tugas lampau dan mencocokkannya ke silabus Kurikulum Merdeka (RAG) untuk memprediksi topik belajar berikutnya lengkap dengan materi prasyarat dan saran persiapan sebelum diajarkan di kelas.
3. **Conversational Learning Assistant**: Asisten chat interaktif dengan persona ramah siswa Indonesia yang dapat mendeteksi intensi belajar (seperti meminta jadwal ulang atau sesi fokus Pomodoro).
4. **Continuous Feedback Evaluation**: Menyimpan dan menganalisis feedback akurasi pengguna untuk mengukur keandalan prediksi topik per mata pelajaran secara berkelanjutan.

---

## 3. Fitur yang Ada & Pemetaan Modul

| Modul File | Tanggung Jawab Utama | Deskripsi Fitur & Logika |
|---|---|---|
| `service.py` | API Entrypoint (FastAPI) | Endpoint HTTP production: `/schedule`, `/predict`, `/chat`, `/feedback`, `/feedback/per-mapel`, `/feedback/akurasi`, `/health`. Autentikasi Bearer Token via `hmac.compare_digest`. |
| `adapter.py` | Contract Translation | Mengonversi payload backend Go (RFC3339, WIB, snake_case, preference) ke struktur data internal engine, dan mengonversi sesi hasil ke format backend. Menangani `existing_sessions[].locked`. |
| `priority.py` | Priority Scoring Formula | Menghitung skor tugas (0–100) dari 5 parameter berbobot: Deadline (40%), Difficulty (20%), Duration (15%), Importance (15%), Late Risk (10%), dengan penyesuaian diskon progres `(1 - 0.85 * progress / 100)`. |
| `slots.py` | Free Time-Slot Finder | Mencari slot waktu belajar kosong dalam rentang horizon (default 14 hari) dengan mengurangkan jam sekolah, kegiatan rutin, dan sesi terkunci (`locked: true`) dari jam belajar preferensi siswa. |
| `scheduler.py` | Deterministic Fallback | Penjadwal greedy deterministik lokal tanpa AI. Menghormati jeda `break_duration` (default 10 mnt), batas `max_sessions_per_day` (default 4), dan maks 2 sesi per tugas/hari. Menghasilkan alasan pengerjaan berbasis fakta. |
| `llm.py` | Multi-LLM Orchestrator | Memanggil provider OpenAI-compatible (`/chat/completions`). Mendukung multi-model fallback, in-memory cache SHA256 (TTL 10 menit), auto-retry 429/503, dan timeout kontrol (`AI_TIMEOUT_SECONDS`). |
| `validator.py` | Output Verification | Validasi skema output LLM menggunakan Pydantic v2 (`LlmOutput`). Memastikan sesi berada dalam slot kosong, sebelum deadline, tidak bentrok, dan alokasi durasi wajar. Jika >50% sesi melanggar, otomatis jatuh ke fallback. |
| `predictor.py` | Material & Topic Predictor | Alur prediksi: retrieval silabus berfilter jenjang, panggilan LLM, fallback deterministik. Prediksi topik berikutnya memakai `No. Urut + 1` bila silabus tersedia. |
| `predictor_data.py` | Sumber Data Silabus | Pemuatan `DATA/kurikulum_merdeka.csv` (cache in-memory), `MAPEL_ALIASES`, `normalize_class_level()`, `resolve_jenjang()`, dan `baca_silabus()` berfilter jenjang/kelas/jalur/kurikulum. |
| `predictor_prompts.py` | Template Prompt Prediktor | Dua varian prompt: silabus tersedia (alur `No. Urut + 1`) dan silabus tidak tersedia (larangan mengarang rujukan kurikulum). |
| `scripts/regen_dataset.py` | Regenerasi Dataset | Menghasilkan ulang CSV runtime dari sheet `Materi` workbook sumber, memulihkan `Relevansi Jurusan/Karir`, dan membuang baris SMK kejuruan. |
| `scripts/deploy_vps.sh` | VPS Deployment Script | Skrip deployment berbasis release + symlink di VPS dengan zero-downtime, shared state (`.env`, `feedback_history.json`), smoke test, auto-rollback, dan pruning release lama. |
| `chatbot.py` | Study Assistant Chatbot | Chatbot interaktif ramah siswa SMP/SMA/SMK. Memanfaatkan riwayat chat (6 putaran terakhir) + konteks tugas aktif siswa, serta mengembalikan klasifikasi aksi (`reschedule`, `focus`, `null`). |
| `feedback.py` | Feedback Analytics Engine | Menyimpan riwayat akurasi ke `DATA/feedback_history.json` secara atomik (`.tmp -> replace`). Menghitung rasio akurasi batch dan historis per mata pelajaran untuk feedback loop prediktor. |
| `app.py` | Local Test Interface | Web dashboard lokal berbasis Flask untuk visualisasi interaktif skor tugas, slot kosong, dan perbandingan jadwal AI vs Fallback (`http://127.0.0.1:5000`). |
| `data.py` | Dummy Testing Dataset | Dataset dummy lokal (siswa, jadwal sekolah, kegiatan rutin, tugas) untuk keperluan pengujian offline dan demo Flask. |

---

## 4. Tech Stack & Environment

- **Bahasa & Runtime**: Python 3.11+ / Python 3.12 (Virtual Environment di `venv/`).
- **Web Service Framework**: 
  - **FastAPI** (`service.py`) untuk microservice production asynchronous.
  - **Uvicorn** sebagai ASGI web server.
  - **Flask** (`app.py`) untuk antarmuka pengujian lokal.
- **Validasi Data**: **Pydantic v2** (`BaseModel`, `Field`).
- **HTTP Client**: **HTTPX** (digunakan untuk panggilan API LLM eksternal).
- **Timezone Management**: `zoneinfo.ZoneInfo` (Asia/Jakarta) dengan fallback offset tetap `WIB (UTC+7)` dan `tzdata`.
- **Integrasi LLM**: Protokol REST OpenAI-compatible (`POST {base_url}/chat/completions`). Kompatibel dengan:
  - Google Gemini (via OpenAI-compatible endpoint).
  - OpenAI (GPT-4o, GPT-4o-mini).
  - Groq (Llama-3, Mixtral).
  - OpenRouter / DeepSeek / Ollama lokal.
- **Data Stores & Datasets**:
  - `DATA/kurikulum_merdeka.csv`: Dataset **runtime** (440 baris): SMA 337 + SMK 103 (hanya mapel umum). Dihasilkan `scripts/regen_dataset.py` dari workbook sumber. Baris **SD (325) dan SMP (101) dibuang** karena engine memprediksi siswa SMA/SMK; materi kejuruan SMK (PPLG, TJKT, PKK, PKL) juga **tidak** ada di runtime.
  - `DATA/kurikulum_merdeka.xlsx`: Salinan byte-identik workbook sumber; rujukan audit, tidak dibaca runtime.
  - `DATA/silabus_awal.csv`: Cadangan lama Fase F; hanya dibaca bila CSV utama tidak ada.
  - `DATA/feedback_history.json`: Penyimpanan rekam jejak akurasi materi berbasis file JSON atomik.
- **Testing**: **Pytest** (186 unit & integration test cases, 100% offline).

---

## 5. Langkah Kerja & Alur Sistem (System Flow)

### 5.1 Alur Endpoint `/schedule` (Smart Study Scheduler)
```
[POST /schedule] -> check_auth (Bearer AI_API_KEY)
       │
       ▼
[adapter.py] -> adapt_request()
  ├── Normalisasi timezone Asia/Jakarta (WIB)
  ├── Filter tugas selesai (done) dan ditunda (is_snoozed)
  ├── Normalisasi format hari (mon..sun) & jam (HH:MM)
  └── Evaluasi existing_sessions:
        ├── locked: true  -> masuk slot sibuk (activities) & mengurangi sisa menit
        └── locked: false -> abaikan (dapat dijadwalkan ulang)
       │
       ▼
[priority.py] -> Hitung skor prioritas (0-100) tiap tugas aktif
       │
       ▼
[slots.py] -> find_free_slots()
  └── Slot preferensi dikurangi jadwal sekolah, aktivitas rutin, & sesi locked
       │
       ▼
[llm.py] -> ai_schedule()
  ├── Cek in-memory cache (SHA256 hash payload)
  ├── Jika LLM aktif & timeout aman (AI_TIMEOUT_SECONDS, default 6s):
  │     ├── Panggil LLM dengan prompt terstruktur
  │     └── [validator.py] validasi sesi (slot bounds, deadline, bentrok)
  │           ├── Lolos -> pakai hasil AI (source: "llm")
  │           └── >50% gagal / error -> beralih ke fallback
  └── Jika LLM mati / error / timeout:
        └── [scheduler.py] jalankan greedy fallback (source: "fallback")
       │
       ▼
[adapter.py] -> to_backend_sessions() (format ISO / struct slotRekomendasi Go)
       │
       ▼
[JSON Response 200] -> {sessions, warnings, source, fallback_reason, latency_ms}
```

### 5.2 Alur Endpoint `/predict` (Material & Topic Predictor)
```
[POST /predict] -> check_auth (Bearer AI_API_KEY)
       │
       ▼
[service.py] -> PredictionPayload
  ├── Validasi `jenjang` ∈ {SD, SMP, SMA, SMK} (Literal) -> 422 bila nilai lain
  │     (SD/SMP diterima demi kompatibilitas, tetapi tanpa silabus runtime)
  └── Tanpa `jenjang` pada kelas 10-12 -> default SMA (backward compatible)
       │
       ▼
[predictor.py] -> predict_material()
  ├── normalisasi_riwayat() riwayat tugas siswa
  ├── resolve_jenjang() -> jenjang efektif (eksplisit; default SMA utk 10-12, dan utk kelas kosong)
  ├── [predictor_data.py] baca_silabus(subject, class_level, curriculum, jenjang)
  │     └── Dataset hanya SMA + mapel umum SMK; kelas SD/SMP -> hasil kosong
  │     ├── Normalisasi nama mapel via MAPEL_ALIASES
  │     ├── Filter ketat: jabatan mapel, jenjang, kelas/fase, jalur, kurikulum
  │     └── Hasil hanya berisi jenjang yang diminta (SMA dan SMK tidak dicampur)
  ├── Baca akurasi historis mapel via feedback.baca_akurasi_per_mapel()
  ├── Jika LLM aktif:
  │     ├── [predictor_prompts.py] build_prediction_prompt()
  │     │     ├── Silabus ada  -> alur `No. Urut + 1`, rujukan resmi
  │     │     └── Silabus kosong -> inferensi jujur, larangan mengarang bab
  │     ├── LLM berhasil -> source="ai"
  │     └── LLM gagal/timeout/JSON rusak -> fallback deterministik
  └── Silabus kosong (mis. mapel kejuruan SMK):
        └── Fallback generik: source="fallback", syllabus_reference="unavailable"
       │
       ▼
[JSON Response 200] -> {predicted_topic, confidence, reason, prerequisites,
                        preparation_suggestion, syllabus_reference, source}
```

**Routing mapel tanpa silabus:** bila `baca_silabus()` mengembalikan hasil kosong
(mata pelajaran kejuruan SMK atau mapel di luar dataset), LLM **tetap dipanggil**
dengan riwayat tugas dan konteks yang diizinkan, tetapi prompt melarang klaim
rujukan kurikulum. Kegagalan provider tidak menghasilkan HTTP 500; fallback
deterministik mengembalikan `syllabus_reference: "unavailable"` dengan confidence
rendah. Nama lengkap siswa, catatan pribadi, dan deskripsi rahasia tetap tidak
dikirim ke LLM (lihat 6.4).

### 5.3 Alur Endpoint `/chat` (Conversational Assistant)
```
[POST /chat] -> check_auth
       │
       ▼
[chatbot.py] -> ai_chat()
  ├── Susun prompt persona asisten belajar siswa Indonesia
  ├── Suntikkan konteks siswa (nama, kelas, sekolah, tugas aktif)
  ├── Gabungkan 6 putaran riwayat percakapan terakhir
  ├── Panggil LLM dengan response_format JSON
  └── Klasifikasikan output:
        ├── action: "reschedule" (jika butuh susun ulang jadwal)
        ├── action: "focus" (jika butuh timer fokus Pomodoro)
        └── action: null (tanya jawab materi umum)
       │
       ▼
[JSON Response 200] -> {reply, action, model, source, latency_ms}
```

### 5.4 Alur Endpoint `/feedback` (Akurasi & Evaluasi)
```
[POST /feedback] & [POST /feedback/per-mapel]
       │
       ▼
[feedback.py] -> simpan_feedback()
  ├── Simpan vote ("accurate" -> benar, "inaccurate" -> salah) per mata pelajaran
  └── Tulis ke DATA/feedback_history.json secara atomik (.tmp -> replace)
       │
       ▼
Hitung metrik persentase akurasi -> [JSON Response 200]
```

---

## 6. Aturan Penulisan File & Standar Kode (Golden Rules)

Semua AI Agent yang mengedit atau membuat file di codebase ini **WAJIB** mematuhi aturan berikut:

### 6.1 Batas Ukuran File (File Length Budget)
- **Target Ideal**: Maksimal **~300 baris kode** per file.
- **Batas Toleransi Maksimum**: **~400 baris kode**.
- **Refactoring Requirement**:
  - Jika suatu file mendekati 400 baris, pecah modul menjadi sub-modul logis (misalnya memisahkan helper, parser, skema Pydantic, atau prompt template).
  - *Catatan Codebase*: Alur prediksi sudah dimodularisasi — `predictor.py` (396 baris) memuat alur prediksi dan fallback, `predictor_data.py` (327 baris) memuat dataset/alias/`baca_silabus()`, dan `predictor_prompts.py` (175 baris) memuat template prompt. Jangan menambah kamus alias atau parser dataset kembali ke `predictor.py`.

### 6.2 Fail-Safe & Non-Breaking Contract
- **Dilarang keras melempar unhandled exception (HTTP 500)** pada request penjadwalan atau prediksi karena kegagalan pihak ketiga (LLM/API eksternal).
- Setiap fungsi yang terhubung ke LLM eksternal **WAJIB** dibungkus blok try-except dan memiliki jalur **deterministic fallback**.
- `GET /health` harus selalu mengembalikan `{"status": "ok"}` tanpa autentikasi dan instan (< 1ms).

### 6.3 Statelessness & Idempotensi
- Engine bersifat *stateless* terhadap request user. Jangan menyimpan sesi user di variabel global memori.
- Panggilan `/schedule` berkali-kali dengan payload yang sama harus menghasilkan alokasi jadwal yang konsisten dan stabil.

### 6.4 Sanitasi Data & Privasi Siswa (Data Minimization)
- **Nama lengkap siswa, deskripsi rahasia tugas, dan catatan pribadi siswa DILARANG dikirim ke LLM publik**.
- Cukup kirim judul tugas, tipe tugas, tingkat kesulitan, estimasi durasi, deadline, dan progres.

### 6.5 Konvensi Kode Python
- Gunakan type annotations lengkap pada parameter fungsi dan return value (`typing`: `List`, `Dict`, `Optional`, `Tuple`, `Any`).
- Gunakan docstring bahasa Indonesia yang jelas di setiap fungsi publik.
- Gunakan logging standar (`logging.getLogger("stoodify")`), hindari penggunaan `print()` liar di kode service production.
- Pengecekan autentikasi Bearer wajib menggunakan timing-safe comparison (`hmac.compare_digest`).

### 6.6 Standar Testing Pytest
- Semua penambahan atau perbaikan fitur **WAJIB** disertai unit test di dalam folder `tests/`.
- Test suite **DILARANG bergantung pada koneksi internet atau LLM API key asli**. Gunakan monkeypatch/mock untuk mensimulasikan respons provider LLM.
- Jalankan verifikasi test sebelum menyelesaikan tugas:
  ```bash
  venv/bin/pytest -v
  ```
  Seluruh 186 test cases (atau lebih) harus berstatus **PASSED**.

---

## 7. Catatan Dokumentasi Teknis Lainnya yang Tersedia

Repository ini memiliki dokumentasi arsitektur dan operasional mendalam di folder `docs/`:

1. **[`docs/INTEGRASI_ARSITEKTUR_AI.md`](./docs/INTEGRASI_ARSITEKTUR_AI.md)**:
   - Audit arsitektur 5 repositori ekosistem Stoodify (`stoodify-ai-1`, `stoodify-ai-2`, `stoodify-backend`, `stoodify-mobile`, `stoodify-apk`).
   - Kontrak data resmi v1, ringkasan ADR (Architectural Decision Records), dan mitigasi latensi.
2. **[`docs/RENCANA_INTEGRASI_AI_1_TERKINI.md`](./docs/RENCANA_INTEGRASI_AI_1_TERKINI.md)**:
   - Audit commit git backend Go, skema arsitektur single VPS (komunikasi loopback 127.0.0.1:8000), dan detail perubahan struct `ai_controllers.go`.
3. **[`docs/DEPLOY_AI_1_VPS.md`](./docs/DEPLOY_AI_1_VPS.md)**:
   - Panduan deployment production di VPS Linux Ubuntu/Debian menggunakan Systemd service unit (`stoodify-ai-1.service`) dan Uvicorn.
4. **[`docs/CI_CD_DEPLOY.md`](./docs/CI_CD_DEPLOY.md)**:
   - Panduan CI/CD otomatis via GitHub Actions (`.github/workflows/ci-cd.yml`) & script deploy VPS (`scripts/deploy_vps.sh`) dengan skema release symlink dan auto-rollback.
5. **[`docs/TODO_AI_AUTO_SCHEDULE.md`](./docs/TODO_AI_AUTO_SCHEDULE.md)**:
   - Status checklist MVP auto-scheduling, penanganan `existing_sessions[].locked`, target latensi p95 < 5 detik, dan pengujian idempotensi.
6. **[`contoh_payload.json`](./contoh_payload.json)**:
   - Payload JSON acuan dari backend Go untuk pengujian manual endpoint `/schedule`.

---

## 8. Panduan Menjalankan Perintah (Quick Commands)

Gunakan virtual environment yang sudah tersedia di direktori `venv/`:

```bash
# 1. Menjalankan seluruh test suite otomatis (186 tests)
venv/bin/pytest -v

# 2. Menjalankan production HTTP service (FastAPI di port 8000)
venv/bin/uvicorn service:app --host 127.0.0.1 --port 8000 --reload

# 3. Menjalankan dashboard web pengujian lokal (Flask di port 5000)
venv/bin/python app.py

# 4. Melakukan health check service
curl http://127.0.0.1:8000/health
# Respons: {"status": "ok"}

# 5. Uji coba diagnosis koneksi LLM
venv/bin/python tes_llm.py
```

---

## 9. Ringkasan Variabel Lingkungan (`.env`)

| Variabel | Sifat | Deskripsi & Contoh Nilai |
|---|---|---|
| `AI_API_KEY` | **Wajib (Prod)** | Secret token bersama antara backend Go dan AI Engine (Bearer token). |
| `LLM_API_KEY` | Opsional | API key provider LLM (Gemini / OpenAI / Groq). Jika kosong, otomatis 100% fallback deterministik. |
| `LLM_BASE_URL` | Opsional | Base URL API OpenAI-compatible (contoh: `https://generativelanguage.googleapis.com/v1beta/openai` atau `https://api.openai.com/v1`). |
| `LLM_MODEL` | Opsional | Nama model utama dan cadangan (contoh: `gemini-2.0-flash,gemini-1.5-flash` atau `gpt-4o-mini`). |
| `AI_TIMEOUT_SECONDS`| Opsional | Timeout pemanggilan LLM (default `6.0` detik). Menjamin engine merespons jauh di bawah batas 15 detik backend. |
| `ALLOW_NO_AUTH` | Dev Only | Set `true` hanya untuk pengujian lokal tanpa menyertakan `AI_API_KEY`. **Dilarang di production!** |
