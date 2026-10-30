# ANALISIS ARSITEKTUR DAN PERENCANAAN INTEGRASI FITUR AI DENGAN APLIKASI STOODIFY

Dokumen ini memuat hasil audit komprehensif terhadap lima repository dalam ekosistem Stoodify, perbandingan alternatif arsitektur, rekomendasi teknis definitif, peta jalan (roadmap) integrasi, analisis dampak perubahan, dokumentasi serah terima (handover) bagi pengembang backend dan AI-2, serta mitigasi risiko teknis.

---

## 1. Existing Architecture Analysis

Audit menyeluruh telah dilakukan terhadap source code, konfigurasi, dependency, dan dokumentasi pada kelima repository:

```
main-arch/
├── stoodify-ai-1/       (Python 3.11+, FastAPI, Flask, Pytest)
├── stoodify-ai-2/       (Python, Google GenAI SDK, prototype)
├── stoodify-backend/    (Go 1.27, Gin, GORM, PostgreSQL)
├── stoodify-mobile/     (TypeScript, React 19, Vite 8, Tailwind v4)
└── stoodify-apk/        (React Native 0.88, Expo SDK 58, WebView)
```

### 1.1 `stoodify-ai-1` (Smart Study Scheduler & Workload Balancer)
- **Teknologi & Runtime:** Python 3.11+, FastAPI (production service di `service.py`), Flask (halaman uji interaktif di `app.py`), Uvicorn, Pydantic, HTTPX, Pytest (100 test cases).
- **Tanggung Jawab:**
  1. Menghitung skor prioritas tugas (0 - 100) berdasarkan 5 parameter berbobot: deadline urgency (40%), difficulty (20%), estimated duration (15%), task importance (15%), dan late risk (10%), dengan penyesuaian diskon progres (`priority.py`).
  2. Menemukan slot waktu luang siswa dalam rentang 14 hari dengan mengurangkan jam sekolah dan kegiatan rutin dari jam belajar preferensi siswa (`slots.py`).
  3. Menyusun jadwal belajar cerdas via LLM OpenAI-compatible (OpenAI, Gemini, Groq, OpenRouter, Ollama) dengan timeout 10 detik, auto-retry, model fallback, dan in-memory cache TTL 10 menit (`llm.py`).
  4. Menyediakan algoritma fallback greedy non-AI deterministik ketika koneksi LLM gagal (`scheduler.py`).
  5. Menjembatani kontrak request/response backend Go melalui adapter (`adapter.py`) dan HTTP API berautentikasi Bearer Token (`service.py`).
- **Kesiapan Integrasi:** **Tinggi (Production Ready)**. Kontrak data dan validasi Pydantic sudah lengkap, test suite 100% lulus tanpa dependensi eksternal, dan Procfile untuk deployment container/PaaS sudah tersedia.

### 1.2 `stoodify-ai-2` (Material & Topic Predictor)
- **Teknologi & Runtime:** Python, Google GenAI SDK (`google.genai`), model `gemini-3.8-flash`.
- **Tanggung Jawab:**
  1. Menganalisis riwayat tugas sebelumnya pada suatu mata pelajaran untuk memprediksi materi/topik yang kemungkinan besar dipelajari pada minggu berikutnya.
  2. Mengacu pada data silabus acuan kurikulum nasional (`silabus_awal.csv` Kurikulum Merdeka Fase F Kelas 11 Matematika).
- **Kondisi Eksisting & Temuan Audit:**
  1. Berdasarkan commit history git (`0e3c838`), terdapat implementasi dasar `prompt_baseline_v1.py` yang memanggil Google GenAI dan menghasilkan output JSON:
     ```json
     {
       "prediksi": [
         {
           "topik": "Nama topik",
           "alasan": "Alasan singkat",
           "confidence": 0.75
         }
       ],
       "status": "success",
       "model_version": "baseline-v1"
     }
     ```
  2. Pada commit `20fb100`, file `prompt_baseline_v1.py` dikosongkan secara tidak sengaja oleh developer terkait.
  3. Belum memiliki HTTP web framework (belum ada FastAPI/Flask).
  4. Belum memiliki mekanisme autentikasi (Bearer token), rate limiting, error handling jaringan, maupun format kontrak yang selaras dengan `stoodify-backend`.
- **Kesiapan Integrasi:** **Rendah ke Sedang (Tahap Prototype/Eksperimen)**. Membutuhkan standardisasi service layer HTTP dan perataan kontrak data sebelum dapat dihubungkan ke backend.

### 1.3 `stoodify-backend` (Core API & Data Store Orchestrator)
- **Teknologi & Runtime:** Go 1.27, Gin Web Framework, GORM ORM, PostgreSQL (driver `gorm.io/driver/postgres`), JWT (`golang-jwt/jwt/v5`), Docker & Docker Compose.
- **Tanggung Jawab:**
  1. Menyimpan dan mengelola data inti: Users, Preferences, Subjects, Schedules, Tasks, Subtasks, Activities, StudySessions, MaterialPredictions, Notifications, dan RefreshTokens (`migrations/migrations.go`).
  2. Autentikasi JWT ganda (Access Token 15 menit, Refresh Token 7 hari dengan single-use rotation).
  3. Background worker scheduler via goroutine (`workers.JalankanScheduler`) untuk mendeteksi tugas terlambat (status `late`) dan membuat notifikasi H-1 serta H-0.
  4. AI Bridge (`controllers/ai_controllers.go`):
     - `POST /api/ai/schedule-recommendations/generate`: Mengambil data tugas aktif dan preferensi siswa, memanggil `AI_SCHEDULER_URL`, lalu menyimpan hasil ke tabel `study_sessions`. Jika gagal atau timeout 15 detik, mengeksekusi `fallbackSlots` lokal.
     - `POST /api/ai/material-predictions/generate`: Mengambil 10 riwayat tugas terakhir untuk mata pelajaran tertentu, memanggil `AI_PREDICTOR_URL`, lalu menyimpan ke tabel `material_predictions`. Jika gagal, mengeksekusi `fallbackPrediction` lokal.
- **Kesiapan Integrasi & Celah Eksisting:**
  1. Arsitektur AI bridge di backend sudah mengadopsi pola pemanggilan HTTP terpisah dengan timeout 15 detik dan fallback rule-based lokal.
  2. **Kesenjangan Data AI-1:** Fungsi `panggilAIScheduler` di Go saat ini hanya mengirimkan `user_id`, `date`, `preferences`, dan `tasks`. Backend belum menyertakan `schedules` (jadwal sekolah), `activities` (kegiatan rutin), dan `existing_sessions` (sesi belajar yang sudah direncanakan). Akibatnya, `stoodify-ai-1` mengeluarkan warning dan tidak dapat memblokir jam sekolah secara akurat.
  3. **Ketidaksesuaian Kontrak AI-2:** Struct `hasilPrediksi` di Go mengharapkan respons JSON flat:
     ```json
     {
       "predicted_topic": "string",
       "confidence": 85.0,
       "reason": "string",
       "prerequisites": "string",
       "preparation_suggestion": "string"
     }
     ```
     Sedangkan baseline prompt `stoodify-ai-2` menghasilkan format array `prediksi: [{ topik, alasan, confidence }]`.

### 1.4 `stoodify-mobile` (Frontend Client)
- **Teknologi & Runtime:** React 19, TypeScript 6, Vite 8, Tailwind CSS v4, Lucide React.
- **Tanggung Jawab:**
  1. Antarmuka utama siswa untuk manajemen tugas, jadwal, kalender belajar, dan sesi AI.
  2. Komunikasi ke backend melalui HTTP Client terpusat (`src/services/apiClient.ts`) dengan otomatisasi header Authorization Bearer token dan token refresh.
  3. Domain services:
     - `studySessionService.ts`: Mengambil rekomendasi sesi belajar AI (`GET /api/ai/schedule-recommendations`), memicu penjadwalan ulang (`POST /api/ai/reschedule`), serta aksi terima/tolak sesi.
     - `predictionService.ts`: Mengambil prediksi materi per mata pelajaran (`GET /api/ai/material-predictions/:subjectId`), memicu prediksi baru (`POST /api/ai/material-predictions/generate`), dan mengirimkan umpan balik akurasi (`POST /api/ai/material-predictions/:id/feedback`).
  4. Komponen UI siap pakai: `AIPlanView.tsx` dan `MaterialPredictionModal.tsx`.
- **Kesiapan Integrasi:** **Sangat Tinggi**. UI dan client service sudah selesai diimplementasikan dan sepenuhnya sinkron dengan kontrak API `stoodify-backend`.

### 1.5 `stoodify-apk` (Android Mobile Wrapper)
- **Teknologi & Runtime:** React Native 0.88, Expo SDK 58, `react-native-webview` 14.0.1.
- **Tanggung Jawab:**
  1. Membungkus web application `stoodify-mobile` (URL production `https://stoodify-mobile-app.vercel.app` atau aset lokal `android/app/src/main/assets/web`) ke dalam binary APK Android (~9.7 MB).
  2. Menyediakan native shell: penanganan hardware back button Android via `BackHandler`, dialog izin kamera/audio, dan handling error offline.
- **Kesiapan Integrasi:** **Tinggi**. Tidak memerlukan perubahan logika internal untuk integrasi AI karena seluruh komunikasi jaringan ditangani di level web view (`stoodify-mobile`).

---

## 2. Integration Flow (Alur Komunikasi Antarservice)

Berikut adalah diagram alur data end-to-end integrasi fitur AI ke dalam ekosistem Stoodify:

```
+-----------------------------------------------------------------------------------+
|                            MOBILE CLIENT LAYER                                    |
|                                                                                   |
|  [ stoodify-apk ] (React Native Container / Android Native Shell)                 |
|         |                                                                         |
|         v (WebView Rendering)                                                     |
|  [ stoodify-mobile ] (React 19 + TypeScript PWA)                                  |
|         |                                                                         |
|         | 1. HTTP Request (JWT Bearer Token)                                      |
|         |    - POST /api/ai/schedule-recommendations/generate                     |
|         |    - POST /api/ai/material-predictions/generate                         |
|         |    - POST /api/ai/reschedule                                            |
+---------|-------------------------------------------------------------------------+
          |
          v
+-----------------------------------------------------------------------------------+
|                         BACKEND ORCHESTRATION LAYER                               |
|                                                                                   |
|  [ stoodify-backend ] (Go 1.27 + Gin Framework)                                  |
|         |                                                                         |
|         +---> [ PostgreSQL (Supabase / Docker) ]                                  |
|         |     - Fetch: Users, Preferences, Tasks, Schedules, Activities           |
|         |     - Store: StudySessions, MaterialPredictions                         |
|         |                                                                         |
|         | 2. Payload Preparation & Enrichment                                     |
|         +---------------------------------------+                                 |
|         |                                       |                                 |
|         | (HTTP POST + Bearer AI_API_KEY)       | (HTTP POST + Bearer AI_API_KEY) |
|         | Timeout: 15s                          | Timeout: 15s                    |
|         v                                       v                                 |
+------------------------------------+  +-------------------------------------------+
|          AI SERVICE 1              |  |               AI SERVICE 2                |
|                                    |  |                                           |
|  [ stoodify-ai-1 ] (FastAPI :8000) |  |  [ stoodify-ai-2 ] (FastAPI :8001)        |
|  - Endpoint: POST /schedule        |  |  - Endpoint: POST /predict                |
|  - Priority Formula (5 Weights)    |  |  - Curriculum Matching (silabus_awal.csv) |
|  - Time-Slot Finder                |  |  - Task History Sequence Analysis         |
|  - Multi-LLM Orchestrator          |  |  - Google GenAI (Gemini Flash)            |
|  - Rule-Based Greedy Fallback      |  |  - Heuristic Topic Fallback               |
+------------------------------------+  +-------------------------------------------+
          |                                       |
          | 3. Output Data Validation             | 3. Output Data Validation
          |    (Structured JSON Sessions)         |    (Predicted Topic + Metadata)
          +---------------------------------------+
          |
          v
   [ stoodify-backend ]
   - Validate Ownership of Tasks & Subjects
   - Persist to PostgreSQL (Transactions)
   - Fallback Execution if AI Unreachable (Circuit Breaker / Fallback Rule-Based)
          |
          v 4. Unified Response (JSON 200/201)
   [ stoodify-mobile ] -> Updated Calendar & Material Cards
```

### Rincian Alur Komunikasi:
1. **Inisiasi Klien:** Pengguna menekan tombol "Generate Jadwal" atau "Prediksi Materi" di antarmuka `stoodify-mobile`.
2. **Autentikasi & Pengambilan Konteks:** `stoodify-backend` memvalidasi JWT pengguna, lalu membaca seluruh konteks yang relevan dari PostgreSQL:
   - Untuk Jadwal: Data tugas aktif, preferensi belajar, jadwal pelajaran sekolah, kegiatan rutin, dan sesi belajar terjadwal yang sudah ada.
   - Untuk Prediksi Materi: Data mata pelajaran dan 10 riwayat tugas terakhir.
3. **Pendelegasian ke AI Service:** Backend membuat panggilan HTTP POST ke engine AI terkait dengan header `Authorization: Bearer <AI_API_KEY>`.
4. **Resiliensi & Fallback:**
   - Jika AI Engine merespons dalam batas waktu 15 detik: Hasil divalidasi dan disimpan ke database dengan tanda `ai_generated = true` (atau sumber `ai`).
   - Jika AI Engine gagal, timeout, atau menghasilkan format tidak valid: Backend secara otomatis menjalankan fallback internal (`fallbackSlots` atau `fallbackPrediction`) tanpa menghentikan alur aplikasi. Pengguna tetap menerima jadwal atau estimasi topik dengan catatan sumber `fallback rule-based`.

---

## 3. Architecture Comparison (Perbandingan Alternatif)

Tiga alternatif arsitektur dievaluasi secara mendalam berdasarkan parameter teknis dan operasional:

### Alternatif 1: Integrasi Langsung ke `stoodify-backend` (Internalized in Go)
Mengkonversi seluruh logika penjadwalan dan pemanggilan LLM langsung ke dalam kode Go di repositori `stoodify-backend`.

- **Kelebihan:**
  - Zero inter-service network latency: Pemrosesan terjadi dalam satu memori proses.
  - Sederhana dari sisi deployment: Hanya ada satu binary Go dan satu instance PostgreSQL.
  - Tidak memerlukan pengelolaan API key bersama (`AI_API_KEY`) antar server internal.
- **Kekurangan & Risiko:**
  - **Hilangnya Ekosistem AI Python:** Python adalah standar de facto AI/ML. Memindahkan prompt engineering, parsing silabus, validasi Pydantic, dan manipulasi data ke Go membatasi fleksibilitas integrasi library AI masa depan (seperti RAG, embeddings, LangChain, atau fine-tuning).
  - **Duplikasi & Pemborosan Upaya:** Logika `stoodify-ai-1` sudah matang dengan 100 test case pytest di Python. Menulis ulang algoritma greedy, scoring 5 parameter, dan slot calculator ke Go membutuhkan waktu signifikan dan rawan regresi.
  - **Bottleneck Kolaborasi Tim:** Developer backend harus menangani logika prompt AI yang sering berubah, sementara developer AI kehilangan kontrol langsung atas kode eksekusinya karena tidak memiliki akses commit ke repo backend.
  - **Coupling Tinggi:** Crash atau memory spike akibat pengolahan AI besar dapat mengganggu endpoint transaksional utama aplikasi (auth, CRUD tugas).

### Alternatif 2: AI sebagai Service Terpisah (Decoupled Microservice via REST API)
Mempertahankan fitur AI sebagai service independen berbasis Python yang mengekspos REST API privat, dikonsumsi oleh `stoodify-backend` sebagai gateway orchestrator.

- **Kelebihan:**
  - **Separation of Concerns:** Backend fokus pada transaksi bisnis, integritas data, relasi database, dan keamanan klien. AI Service fokus pada kalkulasi algoritma, optimasi prompt, dan integrasi provider LLM.
  - **Polyglot Architecture:** Memaksimalkan keunggulan Go untuk API berkinerja tinggi dan konkurensi, serta keunggulan Python untuk orkestrasi AI.
  - **Resiliensi & Isolasi Kegagalan:** Kegagalan atau perlambatan di sisi AI tidak mematikan server backend. Mekanisme timeout (15 detik) dan fallback lokal di Go menjamin ketersediaan sistem 100%.
  - **Kesesuaian dengan Batas Akses Tim:** Pengembang AI mengelola repositori Python secara otonom tanpa risiko merusak kode backend utama.
  - **Skalabilitas Independen:** Service AI yang bersifat compute-heavy dan IO-bound (menunggu respons LLM) dapat di-scale secara horizontal terpisah dari API backend.
- **Kekurangan & Risiko:**
  - Overhead jaringan internal (latensi HTTP antar service sekitar 20 - 100 ms).
  - Kebutuhan manajemen konfigurasi environment terdistribusi (`AI_SCHEDULER_URL`, `AI_PREDICTOR_URL`, `AI_API_KEY`).
  - Diperlukan orkestrasi deployment untuk beberapa service (misalnya Docker Compose di VPS atau multiple services di Railway/Render).

### Alternatif 3: Penggabungan `stoodify-ai-1` dan `stoodify-ai-2` Menjadi Satu Service Terpadu vs Tetap Terpisah

- **Opsi 3A: Digabung Menjadi Satu Service (`stoodify-ai-engine`)**
  - Menggabungkan kedua fitur AI ke dalam satu aplikasi FastAPI dengan rute `/api/v1/schedule` dan `/api/v1/predict`.
  - *Trade-off:* Efisien dalam penggunaan resource hosting (hanya 1 dyno/container Python aktif, mencegah masalah cold-start ganda pada free-tier), mengkonsolidasikan konfigurasi API key LLM (`GEMINI_API_KEY` / `LLM_API_KEY`) dan utilitas umum. Namun, membutuhkan repositori bersama dan koordinasi ketat karena ditangani oleh dua developer berbeda.
- **Opsi 3B: Tetap Dipisahkan Menjadi Dua Service Independen**
  - `stoodify-ai-1` berjalan di port 8000, `stoodify-ai-2` berjalan di port 8001.
  - *Trade-off:* Isolasi total antar fitur. Perubahan pada eksperimen silabus AI-2 tidak akan memengaruhi stabilitas AI-1 yang sudah siap produksi. Namun, memakan resource hosting ganda dan membutuhkan dua URL konfigurasi di backend (`AI_SCHEDULER_URL` dan `AI_PREDICTOR_URL`).

### Tabel Matriks Evaluasi Alternatif:

| Kriteria Evaluasi | Alternatif 1 (Monolit Go) | Alternatif 2 (Service Terpisah - 2 Port) | Alternatif 3 (Unified AI Engine Python) |
|---|---|---|---|
| **Kesesuaian Batas Akses Tim** | Buruk (Semua beban ke dev backend) | Sangat Baik (Sesuai kepemilikan repo) | Cukup (Butuh konsolidasi repo AI) |
| **Pemanfaatan Ekosistem AI** | Rendah (Library Go terbatas) | Sangat Tinggi (Ekosistem Python penuh) | Sangat Tinggi (Ekosistem Python penuh) |
| **Maintainability** | Rendah (Logika tercampur) | Tinggi (Tanggung jawab terisolasi) | Tinggi (Modul terpisah dalam 1 repo) |
| **Effort Implementasi** | Sangat Tinggi (Rewrite Python ke Go) | Rendah (Adapter & Service sudah ada) | Sedang (Refactor AI-2 ke dalam AI-1) |
| **Efisiensi Infrastruktur** | Sangat Tinggi (1 Container) | Sedang (3 Container: Go + AI1 + AI2) | Tinggi (2 Container: Go + Unified AI) |
| **Resiliensi Sistem** | Sedang (Risiko crash monolit) | Sangat Tinggi (Fallback di gateway) | Sangat Tinggi (Fallback di gateway) |

---

## 4. Recommended Architecture (Rekomendasi Arsitektur)

Berdasarkan kondisi existing codebase, batas kewenangan akses repositori, dan kesiapan masing-masing fitur, direkomendasikan pendekatan **Hybrid Service-Oriented Architecture bertahap**:

```
FASE 1 (Saat Ini - Integrasi Cepat & Stabil):
stoodify-backend  ---> [HTTP POST] ---> stoodify-ai-1 (FastAPI :8000, Siap Pakai)
                  ---> [Fallback]  ---> stoodify-ai-2 (Prototype Python / Backend Fallback)

FASE 2 (Pematangan AI-2 & Operasional Efisien):
stoodify-backend  ---> [HTTP POST] ---> Stoodify AI Engine Terpadu (FastAPI Modular)
                                        ├── /schedule (AI Specialist 1)
                                        └── /predict  (AI Specialist 2)
```

### Alasan Teknis Pemilihan:
1. **Menghormati Struktur Existing Tanpa Rewrite:** `stoodify-backend` sudah dirancang dari awal untuk memanggil service AI via HTTP (`AI_SCHEDULER_URL` dan `AI_PREDICTOR_URL`) lengkap dengan mekanisme fallback rule-based lokal. Tidak ada kebutuhan mendesak untuk mengubah pola arsitektur backend.
2. **Kesiapan Instan `stoodify-ai-1`:** Service FastAPI di `stoodify-ai-1/service.py` sudah memiliki adapter, schema mapper, validasi Pydantic, autentikasi Bearer, dan 100 test case. Fitur ini dapat langsung dideploy dan dihubungkan ke backend hari ini juga.
3. **Isolasi Risiko Tahap Pengembangan `stoodify-ai-2`:** `stoodify-ai-2` masih berupa baseline prototype yang belum memiliki layer HTTP dan test suite. Menjaga AI-2 tetap terpisah atau menggunakan fallback sementara di backend mencegah instabilitas pada fitur penjadwalan AI-1 yang sudah siap rilis.
4. **Pemisahan Kewenangan yang Tegas:**
   - Anda fokus menyempurnakan kontrak dan deployment `stoodify-ai-1` serta memastikan responsivitas UI di `stoodify-mobile` dan `stoodify-apk`.
   - Pengembang `stoodify-backend` hanya perlu melengkapi payload pengiriman data ke `stoodify-ai-1`.
   - Pengembang `stoodify-ai-2` membangun wrapper FastAPI berstandar sama untuk fitur prediksi materi.

---

## 5. Integration Roadmap (Peta Jalan Integrasi)

Implementasi integrasi dibagi menjadi 5 fase berurutan dengan kriteria dependensi yang ketat:

```
[ Fase 0: Persiapan Kontrak ]
              |
              v
[ Fase 1: Integrasi Penuh AI-1 & Backend ]
              |
              v
[ Fase 2: Standarisasi & Pembungkusan AI-2 ]
              |
              v
[ Fase 3: Integrasi End-to-End di Frontend & Mobile ]
              |
              v
[ Fase 4: Evaluasi, Konsolidasi, & Monitoring ]
```

### Fase 0: Finalisasi Kontrak Data & Spesifikasi Lingkungan
- **Aktivitas:** Menyepakati skema payload lengkap antara `stoodify-backend`, `stoodify-ai-1`, dan `stoodify-ai-2`.
- **Deliverables:** Dokumen spesifikasi kontrak API dan file contoh payload (`contoh_payload.json`).
- **Dependensi:** Tidak ada.

### Fase 1: Integrasi Penuh `stoodify-ai-1` dengan `stoodify-backend`
- **Tanggung Jawab Pengembang Backend:**
  1. Memperbarui `controllers/ai_controllers.go` pada fungsi `panggilAIScheduler` agar turut mengirimkan array `schedules`, `activities`, `existing_sessions`, `timezone`, dan `now`.
  2. Menyetel variabel environment `AI_SCHEDULER_URL` dan `AI_API_KEY` di server backend.
- **Tanggung Jawab Anda (`stoodify-ai-1`):**
  1. Menyiapkan environment deployment (Railway/Render/Docker) dengan variabel `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, dan `AI_API_KEY`.
  2. Memastikan endpoint `GET /health` dan `POST /schedule` merespons dalam < 10 detik.
- **Kriteria Penerimaan (Acceptance Criteria):**
  - Request `POST /api/ai/schedule-recommendations/generate` di backend menghasilkan respons `201 Created` dengan pesan `rekomendasi sesi belajar dibuat (ai)`.
  - Data sesi tersimpan di tabel `study_sessions` PostgreSQL dengan `ai_generated = true`.

### Fase 2: Standarisasi dan Pembungkusan Service `stoodify-ai-2`
- **Tanggung Jawab Pengembang `stoodify-ai-2`:**
  1. Memulihkan file `prompt_baseline_v1.py` dan menambahkan integrasi data `silabus_awal.csv`.
  2. Membungkus fungsi prediksi materi ke dalam HTTP service FastAPI (file `service.py`) dengan endpoint `POST /predict`.
  3. Mengimplementasikan autentikasi header `Authorization: Bearer <AI_API_KEY>`.
  4. Menyelaraskan format output JSON agar sesuai dengan struct `hasilPrediksi` di Go (`predicted_topic`, `confidence`, `reason`, `prerequisites`, `preparation_suggestion`).
- **Tanggung Jawab Pengembang Backend:**
  1. Menyesuaikan pemanggilan `AI_PREDICTOR_URL` di `controllers/ai_controllers.go` agar mengirimkan data pendukung kurikulum jika tersedia.
- **Kriteria Penerimaan:**
  - Endpoint `POST /api/ai/material-predictions/generate` berhasil memanggil service AI-2 dan menyimpan hasil prediksi ke tabel `material_predictions`.

### Fase 3: Verifikasi End-to-End di `stoodify-mobile` & `stoodify-apk`
- **Tanggung Jawab Anda (`stoodify-mobile` & `stoodify-apk`):**
  1. Menguji interaksi UI pada `AIPlanView.tsx`: tombol generate, terima sesi, tolak sesi, dan reschedule.
  2. Menguji interaksi UI pada `MaterialPredictionModal.tsx`: generate prediksi materi per mapel dan pengiriman umpan balik (feedback akurat/tidak akurat).
  3. Memastikan seluruh penanganan state (loading skeleton, empty state, error state) berjalan mulus di web mobile maupun dalam container APK Android.
- **Kriteria Penerimaan:**
  - Siswa dapat melihat sesi belajar AI di kalender dan prediksi materi di modal tanpa kendala rendering atau crash.

### Fase 4: Konsolidasi & Monitoring Produksi
- **Aktivitas Bersama:**
  1. Mengamati log latensi dan cold-start pada hosting free-tier.
  2. Meninjau opsi penggabungan AI-1 dan AI-2 ke dalam satu container tunggal jika biaya operasional hosting perlu ditekan.

---

## 6. Change Impact Analysis (Analisis Dampak Perubahan)

| Repository | Modul / Komponen Terkena Dampak | Deskripsi Perubahan yang Dibutuhkan | Tingkat Dampak | PIC / Tanggung Jawab |
|---|---|---|---|---|
| **`stoodify-backend`** | `controllers/ai_controllers.go` (`panggilAIScheduler`) | Menambahkan query dan passing data `schedules`, `activities`, `existing_sessions`, `timezone`, dan `now` ke payload AI-1 | **Sedang** | Developer Backend |
| **`stoodify-backend`** | `controllers/ai_controllers.go` (`panggilAIPredictor`) | Memastikan payload mengirim informasi kurikulum/kelas dan memetakan respons JSON AI-2 | **Kecil** | Developer Backend |
| **`stoodify-backend`** | `.env` / Konfigurasi Server | Menyetel nilai `AI_SCHEDULER_URL`, `AI_PREDICTOR_URL`, dan `AI_API_KEY` | **Kecil** | Developer Backend |
| **`stoodify-ai-2`** | Root directory | Membuat file `requirements.txt`, `service.py` (FastAPI), dan endpoint `POST /predict` | **Besar** | Developer AI-2 |
| **`stoodify-ai-2`** | `prompt_baseline_v1.py` | Mengembalikan implementasi prompt dan menambahkan penanganan silabus serta formatting output | **Besar** | Developer AI-2 |
| **`stoodify-ai-1`** | Deployment / Config | Menyiapkan instance server aktif (Uvicorn) dan sinkronisasi `AI_API_KEY` | **Kecil** | Anda (Pemilik Repo) |
| **`stoodify-mobile`** | `src/services/predictionService.ts` | Validasi parsing respons (sudah siap, verifikasi saat integrasi nyata) | **Sangat Kecil** | Anda (Pemilik Repo) |
| **`stoodify-apk`** | Tidak ada | Tidak ada perubahan kode (menggunakan WebView ke mobile web) | **Nol** | Anda (Pemilik Repo) |

---

## 7. Developer Handover Documentation (Dokumentasi Serah Terima Teknis)

Bagian ini dirancang khusus untuk diserahkan kepada developer yang bertanggung jawab atas `stoodify-backend` dan `stoodify-ai-2`.

---

### 7.1 PANDUAN UNTUK DEVELOPER `stoodify-backend`

Halo Tim Backend! Integrasi engine AI penjadwalan (`stoodify-ai-1`) dan prediksi materi (`stoodify-ai-2`) memerlukan sedikit penyesuaian pada file `controllers/ai_controllers.go`.

#### Masalah Saat Ini:
Pada fungsi `panggilAIScheduler`, payload yang dikirim ke `AI_SCHEDULER_URL` saat ini adalah:
```go
payload := gin.H{
    "user_id": userID,
    "date":    date.Format("2006-01-02"),
    "preferences": gin.H{ ... },
    "tasks": tasks,
}
```
Engine `stoodify-ai-1` memerlukan jadwal sekolah (`schedules`), kegiatan rutin (`activities`), dan sesi belajar yang sudah ada (`existing_sessions`) agar sesi belajar baru tidak bertabrakan dengan jadwal sekolah siswa.

#### Perubahan yang Diperlukan pada `controllers/ai_controllers.go`:

1. **Ambil Data Tambahan dari Database Sebelum Memanggil AI:**
```go
// 1. Ambil jadwal sekolah
var schedules []migrations.Schedule
ctrl.DB.WithContext(konteks.Request.Context()).
    Where("user_id = ?", user.ID).Find(&schedules)

// 2. Ambil kegiatan rutin
var activities []migrations.Activity
ctrl.DB.WithContext(konteks.Request.Context()).
    Where("user_id = ?", user.ID).Find(&activities)

// 3. Ambil sesi belajar yang sudah direncanakan mulai hari ini ke depan
var existingSessions []migrations.StudySession
ctrl.DB.WithContext(konteks.Request.Context()).
    Where("user_id = ? AND session_date >= ? AND status = ?", 
        user.ID, targetDate.Format("2006-01-02"), migrations.SessionPlanned).
    Find(&existingSessions)
```

2. **Perbarui Payload pada `panggilAIScheduler`:**
```go
payload := gin.H{
    "user_id": userID,
    "date":    date.Format("2006-01-02"),
    "now":     time.Now().Format(time.RFC3339),
    "timezone": "Asia/Jakarta",
    "preferences": gin.H{
        "start_time":       pref.StartTime,
        "end_time":         pref.EndTime,
        "session_duration": pref.SessionDuration,
        "active_days":      pref.ActiveDays,
    },
    "tasks":             tasks,
    "schedules":         schedules,
    "activities":        activities,
    "existing_sessions": existingSessions,
}
```

3. **Pengaturan Environment Variables di Backend (`.env`):**
```env
# URL service AI-1 (sesuaikan dengan host/port deploy)
AI_SCHEDULER_URL=http://localhost:8000/schedule

# URL service AI-2 (sesuaikan dengan host/port deploy)
AI_PREDICTOR_URL=http://localhost:8001/predict

# Secret key bersama (harus sama persis dengan AI_API_KEY di engine AI)
AI_API_KEY=kunci_rahasia_bersama_stoodify_ai_2026

# Tetap aktifkan fallback jika AI sewaktu-waktu timeout
AI_FALLBACK_ENABLED=true
```

---

### 7.2 PANDUAN UNTUK DEVELOPER `stoodify-ai-2`

Halo Tim AI Specialist 2! Untuk mengintegrasikan fitur prediksi topik materi pelajaran ke backend Stoodify, repositori `stoodify-ai-2` perlu dilengkapi dengan HTTP service wrapper standar berbasis FastAPI.

#### Spesifikasi Kontrak yang Diharapkan Backend:

1. **Endpoint API:**
   - **Method:** `POST`
   - **Path:** `/predict`
   - **Header:** `Authorization: Bearer <AI_API_KEY>`
   - **Content-Type:** `application/json`

2. **Format Request Body (Dikirim dari Backend Go):**
```json
{
  "subject": "Matematika",
  "difficulty": 4,
  "history": [
    {
      "id": 1,
      "title": "PR Translasi dan Refleksi Fungsi",
      "description": "Latihan soal kuadrat",
      "type": "assignment",
      "deadline": "2026-10-05T23:59:00+07:00",
      "difficulty": 4,
      "progress": 100,
      "status": "done"
    }
  ]
}
```

3. **Format Response Body (Wajib Dikembalikan ke Backend Go):**
Backend mengharapkan response JSON dengan status HTTP `200 OK` dan struktur objek sebagai berikut:
```json
{
  "predicted_topic": "Transformasi Geometri: Rotasi dan Dilatasi",
  "confidence": 85.0,
  "reason": "Siswa telah menyelesaikan materi translasi dan refleksi, topik berikutnya pada silabus Fase F adalah rotasi matriks.",
  "prerequisites": "Matriks dasar dan koordinat kartesius",
  "preparation_suggestion": "Pelajari kembali tabel perkalian matriks 2x2 dan sudut istimewa trigonometri."
}
```

#### Langkah Pengerjaan yang Diperlukan di Repo `stoodify-ai-2`:
1. Buat file `requirements.txt`:
   ```
   fastapi>=0.110.0
   uvicorn>=0.28.0
   google-genai>=0.1.0
   pydantic>=2.0.0
   python-dotenv>=1.0.0
   ```
2. Buat file `service.py` yang membaca variabel `GEMINI_API_KEY` dan `AI_API_KEY` dari `.env`, memvalidasi header Bearer token, menjalankan prompt prediksi yang memadukan riwayat tugas dengan `silabus_awal.csv`, dan mengembalikan format JSON di atas.
3. Sediakan endpoint health check `GET /health` yang mengembalikan `{"status": "ok"}`.
4. Buat `Procfile` untuk kemudahan deployment:
   ```
   web: uvicorn service:app --host 0.0.0.0 --port ${PORT:-8001}
   ```

---

## 8. Risk Analysis & Mitigation (Analisis Risiko & Mitigasi)

| Kategori Risiko | Deskripsi Risiko | Dampak | Probabilitas | Rencana Mitigasi Teknis |
|---|---|---|---|---|
| **Latensi & Timeout LLM** | Panggilan LLM (Gemini/OpenAI) membutuhkan waktu > 15 detik saat traffic tinggi. | Pengguna menunggu lama atau mengalami timeout request. | Sedang | Backend sudah memiliki hard-timeout 15 detik (`context.WithTimeout`). Jika lewat, backend otomatis menyajikan fallback lokal (`fallbackSlots` atau `fallbackPrediction`). Di level AI-1, timeout dibatasi 10 detik dan hasil sukses di-cache selama 10 menit. |
| **Cold Start Hosting Free Tier** | Deployment di PaaS gratis (Render/Railway free) tertidur setelah idle, butuh 30 - 50 detik untuk bangun. | Request pertama siswa gagal karena backend timeout 15 detik. | Tinggi | 1. Gunakan scheduler cron job eksternal (misal: UptimeRobot atau GitHub Actions) untuk melakukan ping berkala ke `GET /health` setiap 5 menit agar instance tetap hangat.<br>2. Manfaatkan fallback rule-based lokal backend agar aplikasi tetap berfungsi saat cold start terjadi. |
| **Limit Kuota / Error Provider AI** | API key LLM kehabisan kuota (HTTP 429) atau server provider bermasalah (HTTP 503). | Fitur AI tidak dapat memberikan analisis berbasis bahasa alami. | Sedang | `stoodify-ai-1` sudah dilengkapi multi-model fallback (variabel `LLM_MODEL=model-utama,model-cadangan`) dan auto-fallback greedy tanpa AI (`scheduler.py`). Pengembang AI-2 wajib menerapkan pola serupa. |
| **Schema Drift & Inkonsistensi Kontrak** | Perubahan nama field pada struct Go atau Pydantic Python tanpa koordinasi. | Error unprocessable entity (HTTP 422) atau data tidak terpetakan. | Sedang | 1. Dokumentasikan kontrak API di `contoh_payload.json` sebagai rujukan baku.<br>2. Jalankan test suite adapter (`test_adapter.py`) di CI/CD sebelum setiap merge. |
| **Keamanan & Privasi Data Siswa** | Data sensitif siswa (nama, catatan pribadi, email) terkirim ke server pihak ketiga LLM. | Pelanggaran privasi data pengguna. | Rendah | `adapter.py` pada `stoodify-ai-1` telah memfilter field: nama siswa dianonimkan menjadi "Siswa", serta field `description` dan `notes` pribadi tugas **tidak dikirim** ke prompt LLM. |

---

## 9. Kesimpulan & Rekomendasi Eksekusi

1. **Keputusan Arsitektur:** Pertahankan fitur AI sebagai **service independen berbasis Python** yang berkomunikasi via HTTP REST API privat dengan `stoodify-backend`. Jangan menyatukan kode AI ke dalam monolit Go karena akan merusak ekosistem AI dan memperlambat iterasi.
2. **Langkah Segera (Immediate Action):**
   - Jalankan **Fase 1**: deploy `stoodify-ai-1` dan serahkan panduan sub-bab 7.1 kepada developer `stoodify-backend` untuk melengkapi payload `schedules`, `activities`, dan `existing_sessions`.
   - Serahkan panduan sub-bab 7.2 kepada developer `stoodify-ai-2` agar prototype prediksi materi dapat dibungkus menjadi service FastAPI yang kompatibel.
3. **Frontend & Mobile Status:** `stoodify-mobile` dan `stoodify-apk` sudah berada pada kondisi siap produksi dan tidak memerlukan perombakan arsitektural.
