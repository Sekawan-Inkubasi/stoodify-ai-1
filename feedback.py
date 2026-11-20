"""Modul analisis, penyimpanan, dan evaluasi feedback akurasi prediksi materi Stoodify.

Feedback disimpan di DATA/feedback_history.json dengan format:
{
  "Matematika": {"benar": 10, "salah": 2},
  "Fisika":     {"benar": 3,  "salah": 1},
  ...
}
Akurasi historis ini diumpankan ke predictor.py agar prompt LLM dan fallback
memperhitungkan rekam jejak ketepatan prediksi per mata pelajaran.
"""
import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from predictor_data import MAPEL_ALIASES

log = logging.getLogger("stoodify.feedback")

BASE_DIR = Path(__file__).resolve().parent
FEEDBACK_HISTORY_PATH = Path(
    os.getenv("FEEDBACK_HISTORY_PATH", "").strip()
    or (BASE_DIR / "DATA" / "feedback_history.json")
)

# Kunci internal agar operasi read-modify-write antar thread tidak saling menimpa
_FILE_LOCK = threading.Lock()

# Label feedback yang diterima dari backend Go
_LABEL_BENAR = {"accurate", "correct", "benar", "tepat"}
_LABEL_SALAH = {"inaccurate", "incorrect", "salah", "tidak tepat"}


def _normalize_subject(subject: str) -> str:
    """Normalisasi nama mata pelajaran memakai kamus alias agar konsisten dengan predictor."""
    clean = str(subject or "").strip()
    if not clean:
        return ""
    return MAPEL_ALIASES.get(clean.lower(), clean)


# ---------------------------------------------------------------------------
# Penyimpanan & pembacaan riwayat
# ---------------------------------------------------------------------------

def _baca_riwayat_unlocked() -> Dict[str, Dict[str, int]]:
    """Baca DATA/feedback_history.json tanpa mengambil _FILE_LOCK."""
    try:
        if FEEDBACK_HISTORY_PATH.exists():
            with open(FEEDBACK_HISTORY_PATH, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception as e:
        log.warning("Gagal membaca feedback_history.json: %s", e)
    return {}


def _baca_riwayat() -> Dict[str, Dict[str, int]]:
    """Baca DATA/feedback_history.json secara thread-safe. Kembalikan dict kosong jika belum ada."""
    with _FILE_LOCK:
        return _baca_riwayat_unlocked()


def _tulis_riwayat_unlocked(data: Dict[str, Dict[str, int]]) -> None:
    """Tulis dict riwayat ke DATA/feedback_history.json secara atomik memakai file sementara unik."""
    tmp_path: Optional[str] = None
    try:
        FEEDBACK_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=FEEDBACK_HISTORY_PATH.parent,
            prefix=".feedback_",
            suffix=".tmp",
            delete=False,
        ) as f:
            tmp_path = f.name
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, FEEDBACK_HISTORY_PATH)
        tmp_path = None
    except Exception as e:
        log.error("Gagal menyimpan feedback_history.json: %s", e)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _tulis_riwayat(data: Dict[str, Dict[str, int]]) -> None:
    """Tulis dict riwayat ke DATA/feedback_history.json secara thread-safe & atomik."""
    with _FILE_LOCK:
        _tulis_riwayat_unlocked(data)


def simpan_feedback(data_feedback: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Simpan setiap item feedback ke riwayat per mata pelajaran secara thread-safe.

    Format item yang didukung (dari backend Go):
        {
          "subject": "Matematika",          # atau "mata_pelajaran"
          "user_feedback": "accurate",      # atau "feedback"
          "predicted_topic": "Fungsi Kuadrat"   # opsional, untuk log
        }

    Mengembalikan ringkasan jumlah yang berhasil disimpan.
    """
    with _FILE_LOCK:
        riwayat = _baca_riwayat_unlocked()
        disimpan = dilewati = 0

        for item in data_feedback:
            # Ambil & normalisasi nama mata pelajaran
            subject = item.get("subject") or item.get("mata_pelajaran") or ""
            if isinstance(subject, dict):
                subject = subject.get("name", "")
            subject = _normalize_subject(str(subject))
            if not subject:
                dilewati += 1
                continue

            # Ambil label feedback
            label = str(item.get("user_feedback") or item.get("feedback") or "").strip().lower()
            if label in _LABEL_BENAR:
                verdict = "benar"
            elif label in _LABEL_SALAH:
                verdict = "salah"
            else:
                dilewati += 1
                continue

            # Update riwayat
            if subject not in riwayat:
                riwayat[subject] = {"benar": 0, "salah": 0}
            riwayat[subject][verdict] = riwayat[subject].get(verdict, 0) + 1
            disimpan += 1

        if disimpan:
            _tulis_riwayat_unlocked(riwayat)

    return {"disimpan": disimpan, "dilewati": dilewati}


def baca_akurasi_per_mapel(
    subject: Optional[str] = None,
) -> Dict[str, Any]:
    """Baca akurasi historis dari riwayat feedback.

    Jika ``subject`` diberikan, kembalikan hanya akurasi mata pelajaran itu
    (dinormalisasi memakai kamus alias agar "MTK" dan "Matematika" konsisten).
    Jika tidak, kembalikan semua mata pelajaran.

    Format kembalian per mapel:
        {"benar": 10, "salah": 2, "total": 12, "akurasi": 83.33}
    """
    riwayat = _baca_riwayat()

    def _hitung(rec: Dict[str, int]) -> Dict[str, Any]:
        b = rec.get("benar", 0)
        s = rec.get("salah", 0)
        total = b + s
        return {
            "benar": b,
            "salah": s,
            "total": total,
            "akurasi": round(b / total * 100, 2) if total else None,
        }

    if subject:
        norm = _normalize_subject(subject)
        rec = riwayat.get(norm)
        if rec is None:
            # Kompatibilitas mundur jika file lama menyimpan key mentah sebelum normalisasi
            rec = riwayat.get(subject.strip(), {})
        return _hitung(rec)

    return {mapel: _hitung(rec) for mapel, rec in riwayat.items()}


# ---------------------------------------------------------------------------
# Analisis satu batch (tidak menyimpan ke disk)
# ---------------------------------------------------------------------------

def analisis_feedback(data_feedback: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analisis batch feedback tanpa menyimpan ke disk (endpoint /feedback lama)."""
    benar = 0
    salah = 0

    for item in data_feedback:
        label = str(
            item.get("user_feedback") or item.get("feedback") or ""
        ).strip().lower()

        if label in _LABEL_BENAR:
            benar += 1
        elif label in _LABEL_SALAH:
            salah += 1

    total = benar + salah
    akurasi = round((benar / total) * 100, 2) if total else 0.0

    return {
        "total_feedback": total,
        "prediksi_benar": benar,
        "prediksi_salah": salah,
        "akurasi_feedback": akurasi,
    }


def analisis_feedback_per_mapel(data_feedback: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Analisis batch feedback per mata pelajaran tanpa menyimpan ke disk."""
    hasil_per_mapel: Dict[str, List[Dict[str, Any]]] = {}

    for item in data_feedback:
        subject = item.get("subject") or item.get("mata_pelajaran") or "Tidak diketahui"
        if isinstance(subject, dict):
            subject = subject.get("name", "Tidak diketahui")
        subject = str(subject)

        if subject not in hasil_per_mapel:
            hasil_per_mapel[subject] = []
        hasil_per_mapel[subject].append(item)

    return {
        subject: analisis_feedback(fb_list)
        for subject, fb_list in hasil_per_mapel.items()
    }

