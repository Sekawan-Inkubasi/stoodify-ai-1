# CI/CD — Pengujian Otomatis & Deployment `stoodify-ai-1`

Dokumen ini melengkapi [`DEPLOY_AI_1_VPS.md`](./DEPLOY_AI_1_VPS.md) (setup manual) dengan pipeline otomatis berbasis **GitHub Actions**.

Pipeline: `.github/workflows/ci-cd.yml`
Script deploy (dijalankan di VPS): `scripts/deploy_vps.sh`

---

## 1. Ringkasan Alur

```
push / PR ke main
      │
      ▼
[Job: test]  ubuntu-latest x Python {3.11, 3.12}
   ├─ pip install -r requirements.txt
   ├─ python -m compileall
   ├─ python -m pytest -v        (186 test, 100% offline)
   └─ bash -n scripts/deploy_vps.sh
      │  (hanya push ke main, tidak untuk PR)
      ▼
[Job: deploy]  environment: production
   ├─ git archive HEAD -> release.tar.gz
   ├─ SSH: upload arsip ke /tmp VPS
   └─ bash -s < scripts/deploy_vps.sh
          ├─ ekstrak ke releases/<sha>
          ├─ symlink shared/.env + shared/DATA/feedback_history.json
          ├─ pip install (hanya bila requirements.txt berubah)
          ├─ smoke test `import service`
          ├─ symlink current -> releases/<sha>
          ├─ systemctl restart stoodify-ai
          ├─ poll GET /health sampai {"status":"ok"}
          └─ gagal? rollback otomatis ke release sebelumnya
```

---

## 2. Layout Direktori di VPS (pola release + symlink)

Deploy manual lama memakai satu folder + `git pull`. Pipeline memakai layout yang bisa rollback:

```
$APP_ROOT/                       # contoh: /home/ubuntu/stoodify-ai-1
├── releases/
│   ├── 9f3c1a2.../              # kode immutable per commit
│   └── 1b77d90.../
├── shared/
│   ├── .env                     # rahasia, TIDAK pernah ditimpa deploy
│   ├── venv/                    # virtualenv bersama semua release
│   ├── DATA/feedback_history.json   # state runtime lintas deploy
│   └── requirements.sha256      # penanda cache pip
└── current -> releases/<sha-aktif>
```

Konsekuensi penting:

- `.env` hanya dibaca dari `shared/.env`; file `.env` di repo tidak pernah ikut terkirim (`git archive` hanya file tracked, `.env` di-`.gitignore`).
- `DATA/feedback_history.json` dipindah ke `shared/` sehingga akurasi historis tidak hilang saat deploy. File ini **di-track git**, jadi berhati-hatilah: perubahan runtime di VPS tidak akan dipush balik ke repo dan tidak menimpa data VPS saat deploy.
- Release lama dipangkas otomatis; default simpan 5 terbaru (`KEEP_RELEASES`).

---

## 3. Setup Sekali Jalan

### 3.1 Di VPS — user & direktori

```bash
# Sebagai user deploy (bukan root), misal `ubuntu`
mkdir -p ~/stoodify-ai-1/{releases,shared/DATA}

# .env produksi (sekali saja; deploy berikutnya tidak menyentuhnya)
cp /path/ke/.env.example ~/stoodify-ai-1/shared/.env
chmod 600 ~/stoodify-ai-1/shared/.env
nano ~/stoodify-ai-1/shared/.env     # isi AI_API_KEY, LLM_API_KEY, dst.

# virtualenv pertama (dibuat pipeline bila belum ada, ini opsional)
python3 -m venv ~/stoodify-ai-1/shared/venv
```

Bila VPS sudah memakai layout lama (`~/stoodify-ai-1/.env`), script memigrasikan `.env` ke `shared/.env` pada deploy pertama secara otomatis (salinan, file lama tidak dihapus).

### 3.2 Di VPS — systemd unit ikut layout baru

```ini
# /etc/systemd/system/stoodify-ai.service
[Unit]
Description=Stoodify AI-1 Engine Service (FastAPI)
After=network.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/stoodify-ai-1/current
EnvironmentFile=/home/ubuntu/stoodify-ai-1/shared/.env
ExecStart=/home/ubuntu/stoodify-ai-1/shared/venv/bin/uvicorn service:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now stoodify-ai
```

> `WorkingDirectory` menunjuk ke `current`. Uvicorn memuat `service.py` dari symlink tersebut, jadi setiap deploy hanya perlu mengganti symlink + restart.

### 3.3 Di VPS — izin sudo minimal untuk user deploy

User deploy butuh restart/journalctl tanpa password. Buat file sudoers khusus:

```bash
sudo visudo -f /etc/sudoers.d/stoodify-ai-deploy
```

```sudoers
ubuntu ALL=(root) NOPASSWD: /usr/bin/systemctl restart stoodify-ai, /usr/bin/systemctl status stoodify-ai, /usr/bin/journalctl -u stoodify-ai
```

Validasi: `sudo visudo -c`. Hapus baris `NOPASSWD` bila Anda lebih memilih memasukkan password (pipeline SSH non-interaktif akan gagal, jadi NOPASSWD diperlukan untuk CI).

### 3.4 Di VPS — SSH key khusus deploy

Buat keypair di mesin lokal/CI (jangan pakai key pribadi):

```bash
ssh-keygen -t ed25519 -C "github-actions-stoodify-ai-1" -f ./stoodify_ai_deploy -N ""
```

Tambahkan public key ke VPS:

```bash
# sebagai user deploy di VPS
mkdir -p ~/.ssh && chmod 700 ~/.ssh
cat stoodify_ai_deploy.pub >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

Ambil host key VPS untuk pinning (lebih aman dari `ssh-keyscan` saat runtime):

```bash
ssh-keyscan -p 22 your.vps.host 2>/dev/null
```

---

## 4. Secrets & Variables di GitHub

`Settings → Secrets and variables → Actions`.

| Tipe | Nama | Wajib | Contoh / Default |
|---|---|---|---|
| Secret | `VPS_HOST` | ✅ | `103.119.237.30` |
| Secret | `VPS_USER` | ✅ | `root` |
| Secret | `VPS_SSH_KEY` | ✅ | isi **private** key SSH (baris penuh termasuk header/footer) |
| Secret | `VPS_KNOWN_HOSTS` | disarankan | output `ssh-keyscan -p 20220 103.119.237.30` |
| Variable | `APP_ROOT` | ✅ | `/root/stoodify-ai-1` |
| Variable | `VPS_PORT` | opsional | `20220` (default di workflow) |
| Variable | `SERVICE_NAME` | opsional | `stoodify-ai` (default) |
| Variable | `HEALTH_URL` | opsional | `http://127.0.0.1:8888/health` (default di workflow) |

Bila `VPS_KNOWN_HOSTS` kosong, pipeline menjalankan `ssh-keyscan` (rentan MITM pada jaringan tidak tepercaya; isi secret ini untuk produksi).

Aktifkan juga **branch protection** untuk `main`: wajib status check `pytest (Python 3.12)` lulus sebelum merge.

> `environment: production` pada job deploy memungkinkan *required reviewers* dan menahan secret hanya untuk environment tersebut.

---

## 5. Menjalankan & Memverifikasi

1. Push/merge ke `main` → job `test` jalan.
2. Bila hijau, job `deploy` jalan (hanya pada push ke `main`).
3. Ringkasan per commit muncul di *Step Summary* job deploy.
4. Verifikasi manual di VPS:

```bash
readlink -f ~/stoodify-ai-1/current        # harus berakhir releases/<sha-commit>
sudo systemctl status stoodify-ai
curl -s http://127.0.0.1:8000/health        # {"status":"ok"}
sudo journalctl -u stoodify-ai -n 50 --no-pager
```

`workflow_dispatch` juga tersedia untuk menjalankan pipeline manual dari tab Actions.

---

## 6. Rollback

**Otomatis** bila `/health` gagal setelah restart: script mengembalikan symlink `current` ke release sebelumnya lalu restart ulang, kemudian exit non-zero agar job deploy merah.

**Manual** ke commit tertentu:

```bash
cd ~/stoodify-ai-1
readlink -f current                   # simpan untuk kembali
ln -sfn releases/<sha-tujuan> current
sudo systemctl restart stoodify-ai
curl -s http://127.0.0.1:8000/health
```

Bila `releases/<sha-tujuan>` sudah terhapus oleh pruning, jalankan ulang pipeline pada commit itu (`Actions → CI/CD → Run workflow`, atau `git revert` lalu push).

---

## 7. Perilaku & Batasan yang Perlu Diketahui

- **Test offline**: `tests/conftest.py` menghapus variabel `LLM_*` sehingga suite tidak pernah memanggil LLM. Job `test` juga men-set variabel tersebut kosong sebagai sabuk pengaman ganda.
- **`DATA/feedback_history.json` di-track git**: karena repo menyimpan file ini, isi repo bisa berbeda dengan data runtime VPS. Deploy **tidak** menimpa file VPS (symlink ke `shared/`), tetapi commit baru yang mengubah file itu tidak berpengaruh di produksi.
- **pip cache berbasis hash** `requirements.txt`: perubahan versi tanpa mengubah file tidak terdeteksi. Pin versi di `requirements.txt` bila butuh reproducibility penuh.
- **`--workers 2`**: `/health` dicek per request sehingga 2 worker tidak masalah; state in-memory (cache LLM, cache dataset) terpisah per worker.
- **Tidak ada migrasi DB**: service stateless selain `DATA/feedback_history.json`.
- **Downtime**: `systemctl restart` singkat (detik). Rolling zero-downtime butuh dua unit systemd di port berbeda + Nginx — di luar cakupan pipeline ini.
- **Deploy hanya dari `main`**: PR tidak pernah menyentuh VPS.

---

## 8. Troubleshooting

| Gejala | Penyebab umum | Tindakan |
|---|---|---|
| `import service gagal` di deploy | dependensi kurang / syntax error di release | cek log job; release lama tetap aktif, perbaiki lalu push lagi |
| `AI_API_KEY belum diatur` dari `/health`? (tidak, health tanpa auth) | — | — |
| Deploy sukses tapi backend Go dapat 503 | `.env` VPS kosong `AI_API_KEY` | isi `shared/.env`, restart service |
| `Permission denied (publickey)` | public key belum ada di `authorized_keys` / salah user | ulangi langkah 3.4 |
| `sudo: a password is required` | sudoers belum dibuat | ulangi langkah 3.3 |
| Health gagal terus lalu rollback | port 8000 dipakai proses lain, atau `WorkingDirectory` salah | `sudo systemctl status stoodify-ai`, cek `current` symlink |
| Disk penuh | release lama menumpuk | turunkan `KEEP_RELEASES`, bersihkan `releases/` manual |
