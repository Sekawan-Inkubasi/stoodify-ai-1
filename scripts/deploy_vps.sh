#!/usr/bin/env bash
# Deploy stoodify-ai-1 di VPS memakai pola release + symlink.
#
# Dijalankan DI VPS oleh GitHub Actions (lihat .github/workflows/ci-cd.yml).
# Skema direktori:
#   $APP_ROOT/releases/<release-id>/      kode immutable per commit
#   $APP_ROOT/shared/.env                 rahasia, tidak pernah ditimpa deploy
#   $APP_ROOT/shared/venv/                virtualenv dipakai semua release
#   $APP_ROOT/shared/DATA/                state runtime (feedback_history.json)
#   $APP_ROOT/current -> releases/<id>    symlink aktif
#
# Rollback otomatis: bila service gagal sehat setelah restart, symlink
# dikembalikan ke release sebelumnya dan service direstart lagi.
#
# Exit code 0 hanya bila service aktif DAN /health merespons {"status":"ok"}.

set -Eeuo pipefail

APP_ROOT="${APP_ROOT:?APP_ROOT wajib diisi (contoh: /home/ubuntu/stoodify-ai-1)}"
RELEASE_ID="${RELEASE_ID:?RELEASE_ID wajib diisi (contoh: SHA commit)}"
TARBALL="${TARBALL:?TARBALL wajib diisi (path arsip rilis di VPS)}"
SERVICE_NAME="${SERVICE_NAME:-stoodify-ai}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8888/health}"
KEEP_RELEASES="${KEEP_RELEASES:-5}"
HEALTH_RETRIES="${HEALTH_RETRIES:-15}"
HEALTH_INTERVAL="${HEALTH_INTERVAL:-2}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

RELEASES_DIR="$APP_ROOT/releases"
SHARED_DIR="$APP_ROOT/shared"
SHARED_VENV="$SHARED_DIR/venv"
SHARED_ENV="$SHARED_DIR/.env"
SHARED_DATA="$SHARED_DIR/DATA"
RELEASE_DIR="$RELEASES_DIR/$RELEASE_ID"
CURRENT_LINK="$APP_ROOT/current"
STAGING_DIR="$RELEASES_DIR/.staging-$RELEASE_ID"
REQ_LOCK="$SHARED_DIR/requirements.sha256"

log() { printf '[deploy] %s\n' "$*" >&2; }
die() { printf '[deploy] ERROR: %s\n' "$*" >&2; exit 1; }

cleanup() {
  if [[ -d "$STAGING_DIR" ]]; then rm -rf "$STAGING_DIR"; fi
  if [[ -f "$TARBALL" ]]; then rm -f "$TARBALL"; fi
}
trap cleanup EXIT

# --- 1. Persiapan direktori & arsip -----------------------------------------
[[ -f "$TARBALL" ]] || die "arsip rilis tidak ditemukan: $TARBALL"
mkdir -p "$RELEASES_DIR" "$SHARED_DIR" "$SHARED_DATA"

# Migrasi sekali jalan dari layout lama (deploy manual di docs/DEPLOY_AI_1_VPS.md).
if [[ ! -f "$SHARED_ENV" && -f "$APP_ROOT/.env" ]]; then
  log "memigrasikan .env lama ke $SHARED_ENV"
  cp -p "$APP_ROOT/.env" "$SHARED_ENV"
fi
[[ -f "$SHARED_ENV" ]] || die \
  "file $SHARED_ENV belum ada. Buat dari .env.example dan isi AI_API_KEY sebelum deploy pertama."
chmod 600 "$SHARED_ENV"

if [[ ! -f "$SHARED_DATA/feedback_history.json" ]]; then
  printf '{}\n' > "$SHARED_DATA/feedback_history.json"
fi

if [[ -d "$RELEASE_DIR" ]]; then
  log "release $RELEASE_ID sudah ada, memakai ulang kode yang tersimpan"
  rm -rf "$STAGING_DIR"
else
  log "mengekstrak arsip ke staging"
  rm -rf "$STAGING_DIR"
  mkdir -p "$STAGING_DIR"
  tar -xzf "$TARBALL" -C "$STAGING_DIR" --strip-components=1
  [[ -f "$STAGING_DIR/service.py" ]] || die "arsip rilis tidak berisi service.py"
  chmod +x "$STAGING_DIR/scripts/deploy_vps.sh" 2>/dev/null || true
  mv "$STAGING_DIR" "$RELEASE_DIR"
fi

# --- 2. Sambungkan state bersama ke release ---------------------------------
log "menyambungkan shared/.env dan state DATA"
ln -sfn "$SHARED_ENV" "$RELEASE_DIR/.env"
mkdir -p "$RELEASE_DIR/DATA"
ln -sfn "$SHARED_DATA/feedback_history.json" "$RELEASE_DIR/DATA/feedback_history.json"

# --- 3. Virtualenv bersama + dependensi -------------------------------------
if [[ ! -x "$SHARED_VENV/bin/python" ]]; then
  log "membuat virtualenv di $SHARED_VENV"
  "$PYTHON_BIN" -m venv "$SHARED_VENV"
fi

REQ_HASH="$(sha256sum "$RELEASE_DIR/requirements.txt" | awk '{print $1}')"
PREV_HASH="$(cat "$REQ_LOCK" 2>/dev/null || true)"
if [[ "$REQ_HASH" != "$PREV_HASH" ]]; then
  log "requirements.txt berubah, memasang dependensi"
  "$SHARED_VENV/bin/python" -m pip install --quiet --upgrade pip
  "$SHARED_VENV/bin/python" -m pip install --quiet -r "$RELEASE_DIR/requirements.txt"
  printf '%s\n' "$REQ_HASH" > "$REQ_LOCK"
else
  log "requirements.txt tidak berubah, melewati pip install"
fi

# --- 4. Smoke test import (gagal cepat sebelum service disentuh) ------------
log "smoke test import service"
if ! ( cd "$RELEASE_DIR" && "$SHARED_VENV/bin/python" -c \
        'import service; assert service.app is not None' ); then
  die "import service gagal pada release $RELEASE_ID; release lama tidak diubah"
fi

# --- 5. Aktivasi release ----------------------------------------------------
PREVIOUS_TARGET=""
if [[ -L "$CURRENT_LINK" ]]; then
  PREVIOUS_TARGET="$(readlink -f "$CURRENT_LINK" || true)"
fi

restart_service() {
  sudo systemctl restart "$SERVICE_NAME"
}

wait_healthy() {
  local i
  for ((i = 1; i <= HEALTH_RETRIES; i++)); do
    if ! systemctl is-active --quiet "$SERVICE_NAME"; then
      log "percobaan $i/$HEALTH_RETRIES: service belum aktif"
    elif curl -fsS --max-time 5 "$HEALTH_URL" 2>/dev/null | grep -q '"status"'; then
      return 0
    else
      log "percobaan $i/$HEALTH_RETRIES: health belum OK"
    fi
    sleep "$HEALTH_INTERVAL"
  done
  return 1
}

log "mengaktifkan release $RELEASE_ID"
ln -sfn "$RELEASE_DIR" "$CURRENT_LINK"

log "merestart $SERVICE_NAME"
restart_service

if wait_healthy; then
  log "SUKSES: release $RELEASE_ID sehat di $HEALTH_URL"
else
  log "GAGAL: release $RELEASE_ID tidak sehat"
  if [[ -n "$PREVIOUS_TARGET" && -d "$PREVIOUS_TARGET" && "$PREVIOUS_TARGET" != "$RELEASE_DIR" ]]; then
    log "rollback ke $PREVIOUS_TARGET"
    ln -sfn "$PREVIOUS_TARGET" "$CURRENT_LINK"
    restart_service || true
    if wait_healthy; then
      log "rollback berhasil; service kembali ke release sebelumnya"
    else
      log "rollback selesai tetapi service tetap tidak sehat; periksa log"
    fi
  else
    log "tidak ada release sebelumnya untuk rollback"
  fi
  log "50 baris log terakhir:"
  sudo journalctl -u "$SERVICE_NAME" -n 50 --no-pager >&2 || true
  exit 1
fi

# --- 6. Prune release lama --------------------------------------------------
log "membersihkan release lama (menyimpan $KEEP_RELEASES terbaru)"
CURRENT_REAL="$(readlink -f "$CURRENT_LINK")"
mapfile -t OLD_RELEASES < <(
  ls -1dt "$RELEASES_DIR"/*/ 2>/dev/null \
    | sed 's:/$::' \
    | grep -v -F -x "$CURRENT_REAL" \
    | tail -n +"$KEEP_RELEASES" || true
)
for dir in "${OLD_RELEASES[@]:-}"; do
  [[ -n "$dir" && -d "$dir" ]] || continue
  log "hapus $dir"
  rm -rf "$dir"
done

log "deploy selesai: $RELEASE_ID"
