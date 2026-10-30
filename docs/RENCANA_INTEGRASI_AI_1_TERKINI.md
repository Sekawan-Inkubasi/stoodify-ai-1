# RENCANA INTEGRASI FITUR AI-1 (SMART SCHEDULER) DENGAN STOODIFY BACKEND

Dokumen ini memuat analisis perubahan codebase terkini pada `stoodify-backend` (berdasarkan `git log`), arsitektur komunikasi single VPS (localhost), detail perubahan teknis pada file backend, serta rencana eksekusi langkah-demi-langkah dari awal integrasi hingga verifikasi akhir.

---

## 1. Analisis Perubahan Terkini `stoodify-backend` (Audit Git Log)

Audit commit history (`git log`) pada `stoodify-backend` mengungkapkan perkembangan penting berikut:

1. **Commit `89f6338` (Dokumentasi Kontrak & Arsitektur):**
   - Ditambahkan `docs/AI_CONTRACT.md` yang menetapkan spesifikasi resmi integrasi AI:
     - Konteks wajib untuk AI Scheduler: `tasks` aktif, `schedules` (jadwal sekolah), `activities` (ekskul/les), dan `preferences` (`start_time`, `end_time`, `session_duration`, `break_duration`, `max_sessions_per_day`).
     - Timeout toleransi pemanggilan AI eksternal: fallback otomatis jika service AI timeout atau error.
     - Penanganan request kosong `{}` tanpa error EOF (asumsi hari ini).
   - Ditambahkan `docs/AGENTS.md` (aturan emas backend: data ownership filter `user_id = ?`, envelope response konsisten via `internal/response`, sanitasi raw DB error, dan verifikasi `go build ./...`).
2. **Commit `5f178af` (Toleransi Body JSON Kosong):**
   - Pada `controllers/ai_controllers.go:59`, ditambahkan pengecekan:
     ```go
     if err := konteks.ShouldBindJSON(&input); err != nil && err.Error() != "EOF" {
         response.ValidationError(konteks, err)
         return
     }
     ```
     Ini memungkinkan client mobile memanggil `POST /api/ai/schedule-recommendations/generate` dengan body kosong `{}` untuk generate jadwal hari ini.
3. **Commit `d4dd67d` & `743d9f0` (Curriculum & Syllabus Endpoints):**
   - Penambahan tabel `curriculum_topics` dan `user_topic_progress` untuk roadmap materi belajar (berkaitan erat dengan masa depan AI-2).
4. **Status Eksekusi di `controllers/ai_controllers.go` Saat Ini:**
   - Variabel URL yang dibaca adalah `AI_SCHEDULER_URL` (`os.Getenv("AI_SCHEDULER_URL")`).
   - Header autentikasi yang dikirim adalah `Authorization: Bearer <AI_API_KEY>` (`os.Getenv("AI_API_KEY")`).
   - Timeout request ke AI adalah 15 detik (`context.WithTimeout(ctx, 15*time.Second)`).
   - **Kesenjangan (GAP) yang Perlu Diperbaiki:** Fungsi `panggilAIScheduler` di Go baris 154-175 **belum menyertakan** `schedules`, `activities`, `existing_sessions`, `now`, dan `timezone` ke payload HTTP. Akibatnya engine Python `stoodify-ai-1` mengeluarkan warning dan berisiko menempatkan sesi belajar di jam sekolah atau kegiatan rutin siswa.

---

## 2. Arsitektur Komunikasi Single VPS (Localhost)

Backend Go dan AI-1 Python berjalan pada satu VPS yang sama.

```
+-----------------------------------------------------------------------------------+
|                                  SERVER VPS                                       |
|                                                                                   |
|  [ Client: Web Mobile & APK ]                                                     |
|         |                                                                         |
|         | HTTP (Port 80/443 via Nginx/Reverse Proxy)                              |
|         v                                                                         |
|  +-----------------------------------------------------------------------------+  |
|  |                        STOODIFY BACKEND (Port 8080)                         |  |
|  |                        Binary: Go 1.27 + Gin Framework                      |  |
|  |                        - Auth JWT, CRUD Task, Schedule, Activity            |  |
|  |                        - Background Worker (Late & Notification)            |  |
|  |                        - AI Controller (Bridge Orchestrator)                |  |
|  +-----------------------------------------------------------------------------+  |
|         |                                                                         |
|         | HTTP POST Internal (Loopback 127.0.0.1:8000/schedule)                   |
|         | Header: Authorization: Bearer <AI_API_KEY>                              |
|         | Latensi: < 5ms (Tanpa Bandwidth Internet)                               |
|         v                                                                         |
|  +-----------------------------------------------------------------------------+  |
|  |                       STOODIFY AI-1 ENGINE (Port 8000)                      |  |
|  |                       Process: Python 3.11+ (FastAPI + Uvicorn)             |  |
|  |                       - Bind: 127.0.0.1:8000 (Tertutup dari Publik)         |  |
|  |                       - Priority Formula (5 Weighted Components)            |  |
|  |                       - Free-Slot Finder (14 Hari Horizon)                  |  |
|  |                       - Multi-LLM Orchestrator (OpenAI/Gemini/Groq/Ollama)  |  |
|  |                       - In-Memory Cache (TTL 10 Menit)                      |  |
|  |                       - Fallback Greedy Deterministik Tanpa AI              |  |
|  +-----------------------------------------------------------------------------+  |
|         |                                                                         |
|         | HTTPS Outbound (Hanya AI-1 yang panggil LLM eksternal)                  |
|         v                                                                         |
|  [ LLM Provider API: OpenAI / Gemini / Groq / OpenRouter ]                        |
+-----------------------------------------------------------------------------------+
```

---

## 3. Konfigurasi Environment (`.env`)

### 3.1 File `stoodify-backend/.env`
```env
# Server
PORT=8080
JWT_SECRET=rahasia-jwt-32-karakter-atau-lebih

# Database PostgreSQL
POSTGRES_URL=postgresql://postgres:stoodify_password@127.0.0.1:5432/stoodify?sslmode=disable

# AI Bridge (Single VPS Localhost)
AI_SCHEDULER_URL=http://127.0.0.1:8000/schedule
AI_PREDICTOR_URL=
AI_API_KEY=stoodify_secret_key_2026
AI_FALLBACK_ENABLED=true
```

### 3.2 File `stoodify-ai-1/.env`
```env
# Secret bersama dengan Backend
AI_API_KEY=stoodify_secret_key_2026

# Provider LLM
LLM_API_KEY=token_api_llm_anda
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
LLM_MODEL=gemini-2.0-flash,gemini-1.5-flash

# Batas waktu tunggu AI internal (detik)
AI_TIMEOUT_SECONDS=10
```

---

## 4. Rincian Perubahan Kode Backend (`controllers/ai_controllers.go`)

### Masalah pada Kode Lama:
Fungsi `panggilAIScheduler` hanya menerima dan mengirim `tasks` dan `pref`. Tidak ada data jadwal sekolah, kegiatan rutin, atau sesi lama yang diteruskan.

### Solusi Kode Baru:

1. **Ubah Signature `panggilAIScheduler`:**
```go
func (ctrl *AIController) panggilAIScheduler(
	konteks *gin.Context,
	userID uint,
	date time.Time,
	tasks []migrations.Task,
	pref migrations.UserPreference,
	schedules []migrations.Schedule,
	activities []migrations.Activity,
	existingSessions []migrations.StudySession,
) ([]slotRekomendasi, string)
```

2. **Perkaya Payload JSON di `panggilAIScheduler`:**
```go
payload := gin.H{
	"user_id":   userID,
	"date":      date.Format("2006-01-02"),
	"now":       time.Now().Format(time.RFC3339),
	"timezone":  "Asia/Jakarta",
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

3. **Query Data Tambahan di `GenerateSchedule` (Mematuhi Data Ownership Rule `user_id = ?`):**
```go
// 1. Ambil jadwal sekolah
var schedules []migrations.Schedule
ctrl.DB.WithContext(konteks.Request.Context()).
	Where("user_id = ?", user.ID).Find(&schedules)

// 2. Ambil kegiatan rutin
var activities []migrations.Activity
ctrl.DB.WithContext(konteks.Request.Context()).
	Where("user_id = ?", user.ID).Find(&activities)

// 3. Ambil sesi belajar yang sudah terencana mulai hari ini ke depan
var existingSessions []migrations.StudySession
ctrl.DB.WithContext(konteks.Request.Context()).
	Where("user_id = ? AND session_date >= ? AND status = ?",
		user.ID, targetDate.Format("2006-01-02"), migrations.SessionPlanned).
	Find(&existingSessions)
```

---

## 5. Rencana Tahapan Eksekusi (Step-by-Step Roadmap)

```
[ Langkah 1: Pengujian & Kesiapan Service AI-1 ]
                     |
                     v
[ Langkah 2: Modifikasi Kode Go di stoodify-backend ]
                     |
                     v
[ Langkah 3: Verifikasi Kompilasi & Unit Testing Go ]
                     |
                     v
[ Langkah 4: Uji Integrasi Antarservice (Localhost) ]
                     |
                     v
[ Langkah 5: Pengujian End-to-End di Frontend Mobile & APK ]
```

### Langkah 1: Pengujian & Kesiapan Service AI-1
- **Lokasi:** `stoodify-ai-1/`
- **Aksi:**
  1. Buat file `.env` di `stoodify-ai-1/` berisi `AI_API_KEY` dan kredensial LLM.
  2. Jalankan test suite pytest:
     ```bash
     pytest -v
     ```
     Pastikan 100 test case lulus.
  3. Jalankan service di background port 8000:
     ```bash
     uvicorn service:app --host 127.0.0.1 --port 8000
     ```
  4. Verifikasi health check:
     ```bash
     curl http://127.0.0.1:8000/health
     # Respons: {"status":"ok"}
     ```

### Langkah 2: Modifikasi Kode Go di `stoodify-backend`
- **Lokasi:** `stoodify-backend/controllers/ai_controllers.go`
- **Aksi:**
  1. Perbarui fungsi `GenerateSchedule` untuk mengambil data `schedules`, `activities`, dan `existingSessions` milik user yang sedang login.
  2. Perbarui fungsi `panggilAIScheduler` untuk menyusun payload lengkap sesuai spesifikasi `AI_CONTRACT.md` dan `adapter.py`.
  3. Pastikan penanganan error tetap menggunakan envelope `response.ServerError` dan tidak membocorkan raw error database.

### Langkah 3: Verifikasi Kompilasi & Unit Testing Go
- **Lokasi:** `stoodify-backend/`
- **Aksi:**
  1. Jalankan build check:
     ```bash
     go build ./...
     ```
  2. Jalankan go vet:
     ```bash
     go vet ./...
     ```
  3. Pastikan tidak ada compile error atau lint violation.

### Langkah 4: Uji Integrasi Antarservice (Localhost)
- **Aksi:**
  1. Pastikan PostgreSQL lokal/Supabase aktif.
  2. Jalankan `stoodify-backend` di port 8080 dengan `.env` terkonfigurasi `AI_SCHEDULER_URL=http://127.0.0.1:8000/schedule`.
  3. Login akun siswa untuk mendapatkan `access_token`.
  4. Panggil endpoint rekomendasi jadwal:
     ```bash
     curl -X POST http://127.0.0.1:8080/api/ai/schedule-recommendations/generate \
       -H "Authorization: Bearer <TOKEN>" \
       -H "Content-Type: application/json" \
       -d '{"date":"2026-10-31"}'
     ```
  5. **Kriteria Sukses:**
     - Status HTTP: `201 Created`
     - Pesan: `rekomendasi sesi belajar dibuat (ai)` (atau `(fallback rule-based)` jika token LLM tidak diisi).
     - Data sesi tersimpan di PostgreSQL tabel `study_sessions` dengan field `ai_generated = true`.
     - Log Uvicorn di `stoodify-ai-1` mencatat request masuk tanpa warning `Backend tidak mengirim jadwal sekolah...`.

### Langkah 5: Pengujian End-to-End di Frontend Mobile & APK
- **Lokasi:** `stoodify-mobile/` & `stoodify-apk/`
- **Aksi:**
  1. Buka aplikasi di halaman **Rencana Belajar AI** (`AIPlanView.tsx`).
  2. Klik tombol generate atau auto-generate jadwal harian.
  3. Verifikasi:
     - Kartu sesi belajar muncul lengkap dengan nama tugas, mata pelajaran, jam rekomendasi, durasi, dan alasan (`reason`).
     - Aksi "Terima Rekomendasi" (Accept) mempertahankan status `planned` di kalender.
     - Aksi "Tolak Rekomendasi" (Reject) menandai status menjadi `skipped`.
     - Tombol "Jadwalkan Ulang" (Reschedule) memicu endpoint `POST /api/ai/reschedule`.

---

## 6. Penanganan Transisi ke Fitur AI-2 (Masa Depan)

1. `AI_PREDICTOR_URL` di file `.env` backend dibiarkan kosong selama AI-2 dalam tahap pengembangan.
2. Ketika kosong, backend secara aman mengeksekusi `fallbackPrediction` lokal tanpa error.
3. Setelah developer AI-2 merampungkan service FastAPI di port `8001`, Anda cukup mengisi:
   ```env
   AI_PREDICTOR_URL=http://127.0.0.1:8001/predict
   ```
4. Tidak diperlukan perubahan arsitektur tambahan.
