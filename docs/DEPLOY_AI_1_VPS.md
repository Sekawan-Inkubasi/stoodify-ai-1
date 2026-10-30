# PANDUAN DEPLOYMENT STOODIFY-AI-1 KE VPS (SINGLE VPS DENGAN BACKEND)

Panduan langkah-demi-langkah deployment service **`stoodify-ai-1`** (FastAPI) ke server VPS yang sama dengan `stoodify-backend` yang saat ini sudah berjalan.

---

## 1. Ringkasan Arsitektur Deployment

- **Lokasi Service:** Satu VPS bersama `stoodify-backend`.
- **IP & Port:** `127.0.0.1:8000` (Private Loopback, **TIDAK PERLU** dibuka ke publik/firewall).
- **Process Manager:** Systemd (otomatis jalan saat server reboot, auto-restart jika crash).
- **Protokol:** HTTP REST API internal via URL `http://127.0.0.1:8000/schedule`.

---

## 2. Persiapan di VPS

Masuk ke VPS via SSH:
```bash
ssh user@ip-vps-anda
```

### Langkah 1: Pastikan Python 3.10+ dan venv Terpasang
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
python3 --version
```

### Langkah 2: Buat Direktori Proyek & Clone Repository
Asumsikan proyek diletakkan di `/opt/stoodify-ai-1` atau di home directory `~/stoodify-ai-1`:

```bash
# Contoh di home directory user
cd ~
git clone https://github.com/Sekawan-Inkubasi/stoodify-ai-1.git
# atau clone sesuai URL repo Anda:
# git clone <URL_REPO_STOODIFY_AI_1> stoodify-ai-1

cd stoodify-ai-1
```

---

## 3. Konfigurasi Virtual Environment & Dependencies

### Langkah 1: Buat Virtual Environment Python
```bash
python3 -m venv venv
source venv/bin/activate
```

### Langkah 2: Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Langkah 3: Konfigurasi File `.env`
Salin template konfigurasi:
```bash
cp .env.example .env
nano .env
```

Isi konfigurasi sesuai kebutuhan:
```env
# Rahasia bersama (Wajib sama persis dengan AI_API_KEY di .env stoodify-backend)
AI_API_KEY=stoodify_secret_key_2026

# Provider LLM (Contoh menggunakan Google Gemini via endpoint OpenAI-compatible)
LLM_API_KEY=AIzaSy...token_gemini_anda
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
LLM_MODEL=gemini-2.0-flash,gemini-1.5-flash

# Batas tunggu LLM (detik)
AI_TIMEOUT_SECONDS=10
```
*Simpan file dengan menekan `Ctrl + O`, lalu `Enter`, lalu `Ctrl + X`.*

### Langkah 4: Uji Coba Cepat (Manual Test)
Jalankan service sementara untuk memastikan dependensi dan syntax berjalan:
```bash
uvicorn service:app --host 127.0.0.1 --port 8000
```
Buka terminal SSH kedua di VPS yang sama, lalu uji health check:
```bash
curl http://127.0.0.1:8000/health
# Respons harus: {"status":"ok"}
```
Jika sukses, hentikan uvicorn manual tadi dengan menekan `Ctrl + C` di terminal pertama.

---

## 4. Konfigurasi Background Service (Systemd)

Agar service AI-1 berjalan terus di latar belakang, hidup otomatis saat server reboot, dan restart jika terjadi error, buat systemd unit service.

### Langkah 1: Buat File Unit Systemd
```bash
sudo nano /etc/systemd/system/stoodify-ai.service
```

### Langkah 2: Tempel Konfigurasi Berikut
Sesuaikan `User`, `WorkingDirectory`, dan path virtual environment dengan user VPS Anda (misalnya user `ubuntu` atau `naufal`):

```ini
[Unit]
Description=Stoodify AI-1 Engine Service (FastAPI)
After=network.target

[Service]
Type=simple
# Ganti dengan user non-root VPS Anda
User=ubuntu
Group=ubuntu

# Path absolut folder stoodify-ai-1
WorkingDirectory=/home/ubuntu/stoodify-ai-1

# Path uvicorn di dalam venv
ExecStart=/home/ubuntu/stoodify-ai-1/venv/bin/uvicorn service:app --host 127.0.0.1 --port 8000 --workers 2

# Auto-restart jika service crash
Restart=always
RestartSec=5

# Batas log environment
EnvironmentFile=/home/ubuntu/stoodify-ai-1/.env

[Install]
WantedBy=multi-user.target
```
*Simpan file dengan `Ctrl + O`, `Enter`, lalu `Ctrl + X`.*

### Langkah 3: Aktifkan dan Jalankan Service
```bash
# Reload daemon systemd
sudo systemctl daemon-reload

# Aktifkan auto-start saat VPS boot
sudo systemctl enable stoodify-ai

# Jalankan service sekarang
sudo systemctl start stoodify-ai

# Periksa status service
sudo systemctl status stoodify-ai
```
Pastikan statusnya berwarna hijau: `Active: active (running)`.

---

## 5. Hubungkan `stoodify-backend` yang Sedang Berjalan

Karena backend Go Anda sudah berjalan di VPS tersebut, Anda hanya perlu menyambungkannya:

### Langkah 1: Edit File `.env` Backend
Buka file `.env` di folder backend Anda:
```bash
nano /path/ke/stoodify-backend/.env
```

Pastikan variabel berikut terisi:
```env
AI_SCHEDULER_URL=http://127.0.0.1:8000/schedule
AI_API_KEY=stoodify_secret_key_2026
AI_FALLBACK_ENABLED=true
```
*(Nilai `AI_API_KEY` harus sama persis dengan yang ada di `.env` milik `stoodify-ai-1`)*.

### Langkah 2: Restart Service Backend Anda
Tergantung cara Anda menjalankan backend di VPS:

- **Jika Backend via Systemd:**
  ```bash
  sudo systemctl restart stoodify-backend
  ```
- **Jika Backend via Docker Compose:**
  ```bash
  cd /path/ke/stoodify-backend
  # Jika backend berjalan di Docker container dan memanggil host VPS:
  # Ubah AI_SCHEDULER_URL=http://host.docker.internal:8000/schedule
  # atau gunakan IP gateway docker (biasanya 172.17.0.1:8000)
  docker compose restart app
  ```
- **Jika Backend via PM2 / Screen / Tmux:**
  Restart proses backend agar membaca perubahan `.env`.

---

## 6. Verifikasi Integrasi End-to-End

### Uji 1: Cek Log Service AI-1
Untuk melihat log pemanggilan AI secara real-time:
```bash
sudo journalctl -u stoodify-ai -f
```

### Uji 2: Panggil API Backend dari Komputer Lokal / Postman
Lakukan request ke backend yang sedang berjalan di VPS:
```bash
POST https://api.domain-anda.com/api/ai/schedule-recommendations/generate
Header: Authorization: Bearer <TOKEN_LOGIN_SISWA>
Body: {}
```

**Kriteria Sukses:**
1. Respons backend HTTP `201 Created`.
2. Pesan respons: `rekomendasi sesi belajar dibuat (ai)` atau `(fallback rule-based)`.
3. Pada log systemd AI (`journalctl -u stoodify-ai -f`), muncul baris:
   ```
   INFO schedule user=... tasks=... sessions=... source=ai ms=...
   ```

---

## 7. Perintah Pemeliharaan Berguna

| Kebutuhan | Perintah di VPS |
|---|---|
| Cek status service | `sudo systemctl status stoodify-ai` |
| Restart service | `sudo systemctl restart stoodify-ai` |
| Hentikan service | `sudo systemctl stop stoodify-ai` |
| Lihat log real-time | `sudo journalctl -u stoodify-ai -f` |
| Update kode terbaru | `cd ~/stoodify-ai-1 && git pull && sudo systemctl restart stoodify-ai` |
