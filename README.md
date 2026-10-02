# Stoodify AI Engine

Engine kecerdasan inti Stoodify (bagian **AI Specialist 1**): menghitung prioritas tugas siswa, mencari slot waktu kosong, lalu menyusun jadwal sesi belajar harian. Jadwal bisa dibuat oleh **Gemini** atau, jika AI gagal, oleh **fallback rule-based** tanpa AI.

Repo ini berisi engine, halaman uji sederhana (Flask), dan test suite. Datanya masih dummy (`data.py`), belum terhubung ke backend atau database.

## Fitur

| Komponen | File | Fungsi |
|---|---|---|
| Priority Scoring | `priority.py` | Skor 0-100 per tugas dari deadline, kesulitan, durasi, jenis, late risk, dan progres |
| Time-Slot Finder | `slots.py` | Slot kosong = jam belajar − jadwal sekolah − kegiatan rutin |
| Fallback Scheduler | `scheduler.py` | Jadwal greedy tanpa AI, lengkap dengan teks alasan dan peringatan "waktu tidak cukup" |
| AI Scheduler (Gemini) | `llm.py` | Prompt, panggilan Gemini, batas 15 detik, cache, retry, dan pindah model |
| Validator | `validator.py` | Validasi JSON (Pydantic) dan aturan jadwal sebelum hasil AI dipakai |
| Halaman uji | `app.py`, `templates/index.html` | Satu halaman untuk melihat skor, slot, dan jadwal |
| Dataset dummy | `data.py` | 1 siswa, jadwal sekolah, kegiatan rutin, 8 tugas |

## Struktur folder

```
stoodify-ai/
├── data.py            # dataset buatan + waktu "sekarang" yang dikunci
├── priority.py        # rumus skor prioritas
├── slots.py           # time-slot finder
├── scheduler.py       # fallback greedy
├── validator.py       # validasi output LLM
├── llm.py             # integrasi Gemini
├── app.py             # Flask (halaman uji)
├── templates/
│   └── index.html
├── tests/             # pytest
├── .env.example       # contoh konfigurasi
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

### Mengaktifkan Gemini

1. Buat API key di https://aistudio.google.com/apikey
2. Salin `.env.example` menjadi `.env`, lalu isi:

```
GEMINI_API_KEY=key_kamu
GEMINI_MODEL=model-utama,model-cadangan
```

3. Jalankan ulang `python app.py`, lalu klik **Pakai AI (Gemini)**.

Catatan:

- `GEMINI_MODEL` boleh berisi beberapa model dipisah koma. Model berikutnya dipakai jika model pertama sibuk (error 503/429).
- Nama model Google sering berganti dan berbeda per akun. Untuk melihat model yang tersedia, buat `cek_model.py`:

```python
from llm import load_env, get_api_key
from google import genai

load_env()
client = genai.Client(api_key=get_api_key())
for m in client.models.list():
    if "generateContent" in (getattr(m, "supported_actions", None) or []):
        print(m.name.replace("models/", ""))
```

- Pilih model berlabel `flash` agar cepat. Model `preview` lebih sering kena "high demand".
- File `.env` sudah masuk `.gitignore`. Jangan pernah meng-commit API key.

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

**Gemini:** kode menghitung skor dan slot, lalu Gemini hanya menempatkan sesi ke slot kosong dan menulis `reason`. Hasilnya divalidasi sebelum dipakai.

### 4. Validasi dan fallback otomatis

Sesi dari Gemini ditolak jika:

- di luar slot kosong (bentrok sekolah, kegiatan, atau jam belajar),
- melewati deadline,
- bertabrakan dengan sesi lain,
- durasinya di luar 15-120 menit,
- total menitnya melebihi kebutuhan tugas.

Sesi buruk dibuang satu per satu. Jika lebih dari separuh sesi buruk, atau tidak ada yang lolos, seluruh hasil AI ditolak dan fallback dipakai. Fallback juga aktif otomatis jika:

- `GEMINI_API_KEY` belum diatur,
- Gemini tidak merespons dalam 15 detik,
- terjadi error API (kuota habis, jaringan, key salah),
- output bukan JSON yang valid.

Nama siswa tidak dikirim ke Gemini. Hasil AI yang sukses di-cache 10 menit untuk menghemat kuota.

## Mengubah bobot dan parameter

- **Bobot:** ubah `WEIGHTS` di `priority.py`, atau langsung lewat kolom bobot di halaman uji lalu klik Generate ulang. Bobot dinormalisasi otomatis, jadi total tidak harus tepat 1.
- **Parameter rumus** (di bagian atas `priority.py`): `IMPORTANCE`, `MAX_DAILY_MINUTES` (240), `HORIZON_DAYS` (14), `PROGRESS_REDUCTION` (0,85).
- **Ambang label:** angka 55 dan 35 di `score_task` (`priority.py`).
- **Penjadwalan:** `BREAK`, `MIN_SESSION`, `MAX_PER_TASK_PER_DAY` di `scheduler.py`; `MIN_SLOT` di `slots.py`.
- **Validasi AI:** `MIN_LEN`, `MAX_LEN`, `TOLERANCE` di `validator.py`; `TIMEOUT_SECONDS` dan `CACHE_TTL` di `llm.py`.
- **Data uji:** ubah `data.py`, lalu refresh halaman. Waktu "sekarang" (`NOW`) sengaja dikunci agar hasil selalu sama.

## Menguji

```powershell
python -m pytest -v
```

Ada 55 tes, tanpa internet dan tanpa API key (Gemini diganti tiruan):

| File | Isi |
|---|---|
| `tests/test_priority.py` | 17 skenario prioritas (deadline, kesulitan, progres, jenis tugas, late risk, bobot, dll.) |
| `tests/test_slots.py` | Slot tidak menabrak jadwal, batas jam, hari nonaktif, slot pendek |
| `tests/test_scheduler.py` | Aturan jadwal pada data buatan dan 150 siswa acak berseed |
| `tests/test_llm.py` | JSON rusak, sesi melanggar aturan, timeout, error API, retry 503, pindah model, cache |

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

## Batasan saat ini

- Data masih dummy, belum dari database.
- Belum ada integrasi ke endpoint `/ai/schedule-recommendations` di backend Golang. Halaman Flask hanya alat uji.
- Bobot dan ambang masih tebakan awal, belum dikalibrasi dengan data tugas siswa sungguhan.
- Adaptive reschedule (susun ulang saat sesi dilewati) belum ada.
- Panggilan ke Gemini asli bergantung pada kuota, ketersediaan model, dan koneksi internet.
- Metode greedy bisa membuat tugas berprioritas rendah kehabisan slot sebelum deadline-nya.

## Langkah berikutnya

1. Kalibrasi bobot dengan data tugas siswa nyata.
2. Menetapkan kontrak API (request/response) bersama Backend Dev.
3. Membungkus engine sebagai service (misalnya FastAPI) atau memportnya ke Go.
4. Uji end-to-end minimal 5 skenario sampai hasil tersimpan di database.