# Stoodify AI Engine (Unified AI Specialist 1 & 2)

Engine kecerdasan buatan terpadu Stoodify:
1. **AI Specialist 1 (Smart Study Scheduler & Workload Balancer)**: Menghitung skor prioritas tugas siswa, mencari slot waktu belajar luang (14 hari ke depan), lalu menyusun rekomendasi sesi belajar adaptif tanpa bentrok sekolah atau kegiatan rutin.
2. **AI Specialist 2 (Material & Topic Predictor)**: Menganalisis riwayat tugas lampau dan silabus Kurikulum Merdeka (RAG) untuk memprediksi materi/topik pembelajaran mendatang lengkap dengan prasyarat dan saran persiapan (*Curi Start*).
3. **Feedback Evaluator**: Menganalisis metrik akurasi feedback pengguna baik secara global maupun per mata pelajaran.

Jadwal dan prediksi materi diproses oleh **LLM OpenAI-compatible** (Groq, Google Gemini via OpenAI-endpoint, OpenAI, OpenRouter, Ollama) atau, jika AI offline/timeout/tanpa key, oleh **fallback deterministik**.

Repo ini menyediakan service HTTP untuk backend (FastAPI di `service.py`), halaman uji lokal (Flask di `app.py`), test suite otomatis (186 test cases), serta pipeline **CI/CD GitHub Actions** dengan script deploy otomatis berbasis release + symlink ke VPS Linux (lihat [`docs/CI_CD_DEPLOY.md`](./docs/CI_CD_DEPLOY.md)). Terhubung ke backend Go melalui endpoint `POST /schedule`, `POST /predict`, dan `POST /feedback` dengan autentikasi `Bearer <AI_API_KEY>`.

## Fitur

| Komponen | File | Fungsi |
|---|---|---|
| Priority Scoring | `priority.py` | Skor 0-100 per tugas dari deadline, kesulitan, durasi, jenis, late risk, dan progres |
| Time-Slot Finder | `slots.py` | Slot kosong = jam belajar − jadwal sekolah − kegiatan rutin |
| Fallback Scheduler | `scheduler.py` | Jadwal greedy tanpa AI, lengkap dengan teks alasan dan peringatan |
| AI Scheduler (LLM) | `llm.py` | Prompt, pemanggilan OpenAI-compatible API, batas timeout, cache, retry, dan model fallback |
| Material Predictor | `predictor.py` | Alur prediksi materi: retrieval silabus berfilter jenjang, pemanggilan LLM, dan fallback deterministik |
| Sumber Data Silabus | `predictor_data.py` | Pemuatan dataset, kamus alias mapel, normalisasi kelas, dan `baca_silabus()` |
| Prompt Prediktor | `predictor_prompts.py` | Dua varian prompt: silabus tersedia dan silabus tidak tersedia (mapel vokasi) |
| Regenerasi Dataset | `scripts/regen_dataset.py` | Hasilkan ulang CSV runtime dari workbook sumber, termasuk membuang baris vokasi SMK |
| Feedback Analytics | `feedback.py` | Evaluasi feedback ketepatan prediksi materi global dan per mata pelajaran |
| Validator | `validator.py` | Validasi JSON (Pydantic) dan aturan batas jadwal sebelum hasil AI disetujui |
| Halaman uji | `app.py`, `templates/index.html` | Antarmuka interaktif lokal untuk evaluasi skor, slot, dan jadwal |
| Dataset Silabus | `DATA/kurikulum_merdeka.csv` | Dataset runtime Kurikulum Merdeka: SMA dan mapel umum SMK (440 baris) |
| Dataset Cadangan | `DATA/silabus_awal.csv` | Silabus Fase F lama; hanya dibaca bila `kurikulum_merdeka.csv` tidak ada |
| Dataset dummy | `data.py` | 1 siswa, jadwal sekolah, kegiatan rutin, 8 tugas |

## Struktur folder

```
stoodify-ai-1/
├── DATA/
│   ├── kurikulum_merdeka.csv  # Dataset runtime utama (RAG) — 440 baris
│   ├── kurikulum_merdeka.xlsx # Salinan byte-identik workbook sumber
│   └── silabus_awal.csv       # Cadangan lama (hanya bila CSV utama tidak ada)
├── data.py               # Dataset buatan + waktu acuan pengujian
├── priority.py           # Rumus skor prioritas tugas
├── slots.py              # Time-slot finder
├── scheduler.py          # Fallback greedy scheduler
├── predictor.py          # Alur prediksi materi (LLM + fallback)
├── predictor_data.py     # Dataset, alias mapel, baca_silabus()
├── predictor_prompts.py  # Template prompt LLM (silabus ada/tidak ada)
├── scripts/
│   ├── regen_dataset.py   # Regenerasi CSV runtime dari workbook sumber
│   └── deploy_vps.sh      # Script deployment otomatis ke VPS (release + symlink)
├── .github/
│   └── workflows/ci-cd.yml # GitHub Actions CI/CD (test + deploy)
├── feedback.py           # Evaluasi metrik feedback akurasi materi
├── adapter.py            # Adaptasi payload backend Go <-> struktur engine
├── service.py            # Service FastAPI (POST /schedule, /predict, /feedback)
├── validator.py          # Validasi output LLM dan aturan jadwal
├── llm.py                # Integrasi LLM (OpenAI-compatible)
├── app.py                # Flask (halaman uji)
├── tests/                # Test suite pytest (186 test cases, offline)
├── .env.example          # Contoh konfigurasi environment
├── pytest.ini
└── requirements.txt
```

## Menjalankan (Windows / PowerShell)

Butuh Python 3.11+.

```powershell
cd "C:\Website Kodingan\inkubasi\stoodify-ai"
pip install -r requirements.txt
python app.py
```

Buka `http://127.0.0.1:5000`. Tombol **Generate Jadwal (Fallback)** langsung bekerja tanpa konfigurasi apa pun.

### Mengaktifkan AI (LLM OpenAI-compatible)

Engine memakai format `POST {base_url}/chat/completions`, jadi penyedia apa pun yang OpenAI-compatible bisa dipakai. Cukup isi tiga hal:

1. Salin `.env.example` menjadi `.env`, lalu isi:

```
LLM_API_KEY=token_kamu
LLM_BASE_URL=https://alamat-api-penyedia/v1
LLM_MODEL=model-utama,model-cadangan
```

2. Jalankan ulang `python app.py`, lalu klik **Pakai AI (LLM)**.

Contoh `LLM_BASE_URL`: OpenAI `https://api.openai.com/v1`, Gemini `https://generativelanguage.googleapis.com/v1beta/openai`, Groq `https://api.groq.com/openai/v1`, OpenRouter `https://openrouter.ai/api/v1`, Ollama `http://localhost:11434/v1`.

Catatan:

- `LLM_MODEL` boleh berisi beberapa model dipisah koma. Model berikutnya dipakai jika model pertama sibuk (error 503/429).
- Nama lama `GEMINI_API_KEY` dan `GEMINI_MODEL` masih dikenali. Jika hanya `GEMINI_API_KEY` yang diisi, base URL otomatis ke endpoint Gemini.
- Untuk melihat model yang tersedia di penyedia kamu, jalankan `python cek_model.py`. Untuk diagnosis kecepatan dan kevalidan hasil, jalankan `python tes_llm.py`.
- Jika penyedia menolak `response_format` (JSON mode), engine otomatis mengulang tanpa JSON mode.
- File `.env` sudah masuk `.gitignore`. Jangan pernah meng-commit token.

## Cara kerja

### 1. Priority Score

Setiap tugas mendapat 5 komponen bernilai 0-1:

| Komponen | Bobot | Cara hitung |
|---|---|---|
| Deadline urgency | 40% | Skala 1-10 dari sisa hari (14 hari atau lebih = 1, lewat deadline = 10), lalu dibagi 10 |
| Difficulty | 20% | Kesulitan 1-5 dinormalisasi: (nilai − 1) / 4 |
| Duration | 15% | Estimasi menit / 240, maksimal 1 |
| Importance | 15% | Ujian 1.0, Proyek 0.9, Tugas 0.7, Baca materi 0.5 |
| Late risk | 10% | 1 jika progres < 20% **dan** deadline < 3 hari, selain itu 0 |

Skor akhir = jumlah komponen berbobot × (1 − 0,85 × progres/100) × 100.
Tugas dengan progres 100% tidak dihitung.

Label prioritas: **high** jika skor ≥ 55, **medium** jika ≥ 35, selain itu **low**.

### 2. Time-Slot Finder

Untuk tiap hari aktif (14 hari ke depan): ambil jam belajar siswa, kurangi jadwal sekolah dan kegiatan rutin di hari itu. Untuk hari ini, slot dimulai dari waktu sekarang (dibulatkan ke atas per 15 menit). Slot kurang dari 30 menit dibuang.

### 3. Penjadwalan

**Fallback (greedy):** tugas diurutkan dari skor tertinggi (tugas yang sudah lewat deadline didahulukan). Tiap tugas mengambil slot paling awal yang masih sebelum deadline-nya, maksimal 2 sesi per hari, dengan jeda 10 menit antar sesi. Jika waktu tidak cukup, muncul peringatan.

**LLM:** kode menghitung skor dan slot, lalu LLM hanya menempatkan sesi ke slot kosong dan menulis `reason`. Hasilnya divalidasi sebelum dipakai.

### 4. Validasi dan fallback otomatis

Sesi dari LLM ditolak jika:

- di luar slot kosong (bentrok sekolah, kegiatan, atau jam belajar),
- melewati deadline,
- bertabrakan dengan sesi lain,
- durasinya di luar 15-120 menit,
- total menitnya melebihi kebutuhan tugas.

Sesi buruk dibuang satu per satu. Jika lebih dari separuh sesi buruk, atau tidak ada yang lolos, seluruh hasil AI ditolak dan fallback dipakai. Fallback juga aktif otomatis jika:

- `LLM_API_KEY` belum diatur,
- LLM tidak merespons dalam 15 detik,
- terjadi error API (kuota habis, jaringan, key salah),
- output bukan JSON yang valid.

Nama siswa tidak dikirim ke LLM. Hasil AI yang sukses di-cache 10 menit untuk menghemat kuota.

## Mengubah bobot dan parameter

- **Bobot:** ubah `WEIGHTS` di `priority.py`, atau langsung lewat kolom bobot di halaman uji lalu klik Generate ulang. Bobot dinormalisasi otomatis, jadi total tidak harus tepat 1.
- **Parameter rumus** (di bagian atas `priority.py`): `IMPORTANCE`, `MAX_DAILY_MINUTES` (240), `HORIZON_DAYS` (14), `PROGRESS_REDUCTION` (0,85).
- **Ambang label:** angka 55 dan 35 di `score_task` (`priority.py`).
- **Penjadwalan:** `BREAK`, `MIN_SESSION`, `MAX_PER_TASK_PER_DAY` di `scheduler.py`; `MIN_SLOT` di `slots.py`.
- **Validasi AI:** `MIN_LEN`, `MAX_LEN`, `TOLERANCE` di `validator.py`; `AI_TIMEOUT_SECONDS` (.env) dan `CACHE_TTL` di `llm.py`.
- **Data uji:** ubah `data.py`, lalu refresh halaman. Waktu "sekarang" (`NOW`) sengaja dikunci agar hasil selalu sama.

## Menguji

```powershell
python -m pytest -v
```

Ada 206 tes, tanpa internet dan tanpa API key (LLM diganti tiruan):

| File | Isi |
|---|---|
| `tests/test_priority.py` | 17 skenario prioritas (deadline, kesulitan, progres, jenis tugas, late risk, bobot, dll.) |
| `tests/test_slots.py` | Slot tidak menabrak jadwal, batas jam, hari nonaktif, slot pendek |
| `tests/test_scheduler.py` | Aturan jadwal pada data buatan dan 150 siswa acak berseed |
| `tests/test_llm.py` | JSON rusak, sesi melanggar aturan, timeout, error API, retry 503, pindah model, cache & eviksi |
| `tests/test_adapter.py` | Pemetaan data backend: jenis tugas, hari, zona waktu, tugas selesai/ditunda, sesi lama, data opsional hilang |
| `tests/test_service.py` | Autentikasi bearer, format balasan, fallback, timeout, privasi prompt, field `jenjang` dan validasi 422 |
| `tests/test_predictor.py` | Filter jenjang, alias mapel, jalur vokasi tanpa silabus, batas panjang riwayat, fallback aman |
| `tests/test_chatbot.py` | Validasi role allowlist (anti role-injection), parsing action, timeout/fallback, retry 503 vs 4xx, endpoint `/chat` |
| `tests/test_feedback.py` | Akumulasi feedback, normalisasi alias mapel, concurrency safety, akurasi historis |
| `tests/test_dataset.py` | Header, jumlah baris 440, hanya SMA+SMK, batas mapel kejuruan SMK |

Tes prioritas mengecek aturan (urutan dan logika), bukan angka persis, sehingga tidak ikut rusak saat bobot dikalibrasi.

## Endpoint halaman uji

| Endpoint | Fungsi |
|---|---|
| `GET /` | Halaman uji |
| `GET /api/data` | Data siswa, bobot, dan status API key |
| `POST /api/run` | Body `{"mode": "ai" atau "fallback", "weights": {...}}`. Mengembalikan skor, slot, sesi, peringatan, `source`, dan `fallback_reason` |

Bentuk satu sesi:

```json
{
  "task_id": 1,
  "title": "Laporan Konfigurasi Jaringan",
  "date": "2026-10-05",
  "start_time": "16:00",
  "end_time": "16:45",
  "duration": 45,
  "target_progress": 35,
  "priority": "high",
  "reason": "Deadline tinggal 2 hari, tingkat kesulitan tinggi.",
  "source": "fallback"
}
```

## Integrasi dengan backend (service FastAPI)

Backend Go memanggil engine lewat HTTP: `POST AI_SCHEDULER_URL` dengan header `Authorization: Bearer AI_API_KEY`.

```powershell
uvicorn service:app --port 8000
```

| Endpoint | Fungsi |
|---|---|
| `GET /health` | Cek status service (tanpa autentikasi) |
| `POST /schedule` | Penjadwalan cerdas belajar adaptif (`AI_SCHEDULER_URL`) |
| `POST /predict` | Prediksi materi Kurikulum Merdeka (`AI_PREDICTOR_URL`) |
| `POST /chat` | Asisten belajar interaktif dengan deteksi aksi (`reschedule`/`focus`) |
| `POST /feedback` | Simpan & evaluasi analitik feedback akurasi materi global |
| `POST /feedback/per-mapel` | Simpan & evaluasi analitik feedback akurasi per mata pelajaran |
| `GET /feedback/akurasi` | Baca akurasi historis prediksi dari `feedback_history.json` (opsional `?subject=`) |

Pengaturan di `.env` engine dan backend:

| Di mana | Variabel | Nilai |
|---|---|---|
| Engine | `AI_API_KEY` | Rahasia bersama (sama dengan di backend) |
| Engine | `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` | Token, alamat API, dan model LLM |
| Engine | `AI_TIMEOUT_SECONDS` | 10 (backend menunggu 15 detik) |
| Backend | `AI_SCHEDULER_URL` | `http://localhost:8000/schedule` (atau URL deploy) |
| Backend | `AI_PREDICTOR_URL` | `http://localhost:8000/predict` (atau URL deploy) |
| Backend | `AI_API_KEY` | Sama dengan di engine |

Yang dilakukan engine terhadap payload backend:

- Jenis tugas `exam/project/assignment/reading` dipetakan ke istilah engine, dan deadline RFC3339 dikonversi ke WIB.
- Tugas `done` dan `is_snoozed` tidak dijadwalkan.
- Sesi `planned` yang sudah ada dianggap jam sibuk dan mengurangi kebutuhan menit tugasnya.
- Kegiatan `daily` berlaku tiap hari. Kegiatan tanpa hari dianggap tiap hari (aman, tapi boros slot) dan diberi peringatan.
- Data opsional (`schedules`, `activities`, `existing_sessions`, `now`, `timezone`) yang tidak dikirim memunculkan `warnings`. Tanpa jadwal sekolah, sesi bisa bentrok.
- Field `description` dan `notes` tidak dikirim ke LLM.

Respons memakai nama field yang sama dengan struct `slotRekomendasi` di backend (`recommended_date`, dst.). Field `warnings`, `source`, `fallback_reason` baru terbaca setelah backend menambahkannya.

## Dataset silabus dan kontrak `/predict`

### File yang dibaca saat runtime

Prediktor hanya membaca **`DATA/kurikulum_merdeka.csv`** (UTF-8 BOM). File
`DATA/silabus_awal.csv` adalah cadangan lama yang dipakai hanya jika CSV utama
tidak ada. `DATA/kurikulum_merdeka.xlsx` adalah salinan byte-identik dari workbook
sumber dan **tidak dibaca saat runtime**; ia disimpan untuk audit.

### Hubungan CSV dengan workbook sumber

`DATA/kurikulum_merdeka.csv` dihasilkan oleh `scripts/regen_dataset.py` dari sheet
`Materi` pada `Kurikulum_Merdeka_Gabungan_Sempurna.xlsx` (di direktori proyek induk):

```bash
venv/bin/python scripts/regen_dataset.py --check   # bandingkan tanpa menulis
venv/bin/python scripts/regen_dataset.py           # tulis ulang CSV + mirror XLSX
```

### Cakupan runtime

| Kelompok | Baris | Keterangan |
|---|---:|---|
| SMA | 337 | Kelas 10–12, 19 mapel |
| SMK (mapel umum) | 103 | Kelas 10–12, 10 mapel umum |
| **Total** | **440** | |

Stoodify memprediksi siswa SMA dan SMK. Baris **SD dan SMP tidak dimasukkan** ke
dataset runtime: jenjang itu tidak memakai alur prediksi materi ini. Bila request
datang dengan kelas SD/SMP, prediktor tetap merespons tanpa error tetapi menandai
`syllabus_reference: "unavailable"` (prediksi dari riwayat tugas/LLM saja).

Mata pelajaran umum SMK yang tersedia: Pendidikan Agama dan Budi Pekerti,
Pendidikan Pancasila, Bahasa Indonesia, Matematika, Bahasa Inggris, Sejarah,
Seni dan Budaya, PJOK, Informatika, dan IPAS.

**Batas cakupan kejuruan:** materi kejuruan SMK (PPLG, TJKT, Projek Kreatif dan
Kewirausahaan, PKL) **tidak ada** di dataset karena hanya mewakili sebagian kecil
program keahlian di Indonesia. Untuk mapel seperti itu, endpoint tetap mengembalikan
prediksi dari LLM berdasarkan riwayat tugas, dengan `syllabus_reference: "unavailable"`.
Dataset ini **bukan** klaim silabus lengkap seluruh jurusan SMK.

### Kontrak `/predict`

Field baru yang opsional: **`jenjang`** dengan nilai `"SD"`, `"SMP"`, `"SMA"`, `"SMK"`.

- Nilai lain (termasuk `"sma"` huruf kecil, `"MA"`, `"kuliah"`, atau angka) ditolak
  dengan **HTTP 422**.
- Bila `jenjang` kosong pada kelas 10–12, sistem memakai default **SMA** agar request
  lama tetap kompatibel dan tidak mencampur silabus SMA dan SMK.
- Kelas 1–9 tetap diterima demi kompatibilitas, tetapi tidak punya silabus runtime:
  hasilnya `syllabus_reference: "unavailable"`. SMP bukan target pengguna aplikasi.
- Bila `class_level` **dan** `jenjang` sama-sama kosong, sistem memakai default SMA
  sehingga silabus SMA dan SMK tidak pernah tercampur dalam satu hasil.
- **Klien/backend yang memprediksi siswa SMK wajib mengirim `jenjang: "SMK"`.**
- Bentuk respons tidak berubah.

Contoh request SMK:

```json
{
  "subject": "Matematika",
  "difficulty": 4,
  "class_level": "11",
  "jenjang": "SMK",
  "history": []
}
```

Penjelasan lengkap beserta contoh SMA dan mapel vokasi ada di
[`docs/to-do-dataset.md`](./docs/to-do-dataset.md).

## Batasan saat ini

- Data masih dummy, belum dari database.
- Service sudah siap, tetapi belum diuji end-to-end dengan backend asli dan LLM asli. Backend juga perlu menambahkan `schedules`, `activities` (dengan hari), dan `existing_sessions` ke payload.
- Free tier hosting bisa tertidur (cold start) lebih dari 15 detik, sehingga backend memakai fallback-nya sendiri. Jaga tetap hangat lewat ping `/health`.
- Belum ada rate limit per user di engine.
- Bobot dan ambang masih tebakan awal, belum dikalibrasi dengan data tugas siswa sungguhan.
- Adaptive reschedule (susun ulang saat sesi dilewati) belum ada.
- Panggilan ke LLM asli bergantung pada kuota, ketersediaan model, dan koneksi internet.
- Metode greedy bisa membuat tugas berprioritas rendah kehabisan slot sebelum deadline-nya.

## Langkah berikutnya

1. Kalibrasi bobot dengan data tugas siswa nyata.
2. Backend menambah data payload (jadwal sekolah, kegiatan, sesi lama).
3. Deploy service dan isi `AI_SCHEDULER_URL`.
4. Uji end-to-end minimal 5 skenario sampai hasil tersimpan di database.
