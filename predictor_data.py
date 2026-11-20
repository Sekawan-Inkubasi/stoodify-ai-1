"""Sumber data silabus Kurikulum Merdeka untuk predictor.

Modul ini memisahkan pemuatan dataset, kamus alias mata pelajaran, normalisasi
kelas, dan pembacaan silabus dari alur prediksi di `predictor.py`.

Dataset runtime `DATA/kurikulum_merdeka.csv` dihasilkan oleh
`scripts/regen_dataset.py` dari workbook `Kurikulum_Merdeka_Gabungan_Sempurna.xlsx`
dan HANYA berisi:
- seluruh baris SD, SMP, dan SMA;
- baris SMK untuk mata pelajaran umum.

Materi kejuruan SMK sengaja tidak ada di runtime; prediksinya diarahkan ke LLM.
"""
import csv
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("stoodify.predictor")

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "DATA"
KURIKULUM_MERDEKA_PATH = DATA_DIR / "kurikulum_merdeka.csv"
SILABUS_AWAL_PATH = DATA_DIR / "silabus_awal.csv"

# Cache in-memory dataset agar pencarian silabus berkecepatan tinggi
_CACHED_SILABUS_KM: Optional[List[Dict[str, str]]] = None

# Peta alias nama mata pelajaran agar query siswa/backend yang bervariasi dapat dicocokkan ke nama baku
MAPEL_ALIASES: Dict[str, str] = {
    # Matematika
    "mtk": "Matematika",
    "matematika": "Matematika",
    "matematika wajib": "Matematika",
    "matematika minat": "Matematika Tingkat Lanjut",
    "matematika lanjut": "Matematika Tingkat Lanjut",
    "matematika tingkat lanjut": "Matematika Tingkat Lanjut",
    # Bahasa Indonesia
    "bahasa indonesia": "Bahasa Indonesia",
    "b. indonesia": "Bahasa Indonesia",
    "b.indo": "Bahasa Indonesia",
    "bindo": "Bahasa Indonesia",
    "bahasa & sastra indonesia tingkat lanjut": "Bahasa & Sastra Indonesia Tingkat Lanjut",
    "bahasa indonesia tingkat lanjut": "Bahasa & Sastra Indonesia Tingkat Lanjut",
    # Bahasa Inggris
    "bahasa inggris": "Bahasa Inggris",
    "b. inggris": "Bahasa Inggris",
    "b.inggris": "Bahasa Inggris",
    "binggris": "Bahasa Inggris",
    "english": "Bahasa Inggris",
    "bahasa & sastra inggris tingkat lanjut": "Bahasa & Sastra Inggris Tingkat Lanjut",
    "bahasa inggris tingkat lanjut": "Bahasa & Sastra Inggris Tingkat Lanjut",
    # MIPA & IPA
    "fisika": "Fisika",
    "kimia": "Kimia",
    "biologi": "Biologi",
    "ipa": "Ilmu Pengetahuan Alam (IPA)",
    "ipas": "Ilmu Pengetahuan Alam dan Sosial (IPAS)",
    "ilmu pengetahuan alam dan sosial": "Ilmu Pengetahuan Alam dan Sosial (IPAS)",
    "ilmu pengetahuan alam dan sosial (ipas)": "Ilmu Pengetahuan Alam dan Sosial (IPAS)",
    # IPS
    "ips": "Ilmu Pengetahuan Sosial (IPS)",
    "ekonomi": "Ekonomi",
    "geografi": "Geografi",
    "sosiologi": "Sosiologi",
    "sejarah": "Sejarah",
    "antropologi": "Antropologi",
    # PKn & Agama
    "pkn": "Pendidikan Pancasila",
    "ppkn": "Pendidikan Pancasila",
    "pancasila": "Pendidikan Pancasila",
    "pendidikan pancasila": "Pendidikan Pancasila",
    "pabp": "Pendidikan Agama dan Budi Pekerti",
    "pai": "Pendidikan Agama dan Budi Pekerti",
    "agama": "Pendidikan Agama dan Budi Pekerti",
    "pendidikan agama": "Pendidikan Agama dan Budi Pekerti",
    "pendidikan agama dan budi pekerti": "Pendidikan Agama dan Budi Pekerti",
    # PJOK & Seni
    "pjok": "Pendidikan Jasmani Olahraga dan Kesehatan (PJOK)",
    "penjas": "Pendidikan Jasmani Olahraga dan Kesehatan (PJOK)",
    "penjaskes": "Pendidikan Jasmani Olahraga dan Kesehatan (PJOK)",
    "pendidikan jasmani olahraga dan kesehatan": "Pendidikan Jasmani Olahraga dan Kesehatan (PJOK)",
    "pendidikan jasmani olahraga dan kesehatan (pjok)": "Pendidikan Jasmani Olahraga dan Kesehatan (PJOK)",
    "seni": "Seni dan Budaya",
    "seni budaya": "Seni dan Budaya",
    "seni dan budaya": "Seni dan Budaya",
    # Informatika (mapel umum SMA & SMK)
    "informatika": "Informatika",
    "tik": "Informatika",
    "ti": "Informatika",
    # Catatan: alias mapel kejuruan (PPLG, TJKT, PKK, PKL) sengaja TIDAK dipetakan
    # ke dataset karena materi kejuruan tidak ada di runtime. Query seperti itu
    # akan gagal cocok, menghasilkan silabus kosong, lalu diarahkan ke LLM.
}

# Jenjang yang dikenal endpoint /predict. Nilai di luar ini ditolak di batas API.
SUPPORTED_JENJANG = ("SD", "SMP", "SMA", "SMK")

# Default jenjang untuk payload lama yang belum mengirim field `jenjang` pada
# kelas 10-12: SMA, agar request lama tidak mencampur baris SMA dan SMK.
DEFAULT_JENJANG_SMA = "SMA"

ROMAN_TO_GRADE = {
    "I": "1", "II": "2", "III": "3", "IV": "4", "V": "5", "VI": "6",
    "VII": "7", "VIII": "8", "IX": "9", "X": "10", "XI": "11", "XII": "12", "XIII": "12"
}

GRADE_TO_ROMAN = {v: k for k, v in ROMAN_TO_GRADE.items() if k != "XIII"}

GRADE_TO_FASE = {
    "1": "A", "2": "A",
    "3": "B", "4": "B",
    "5": "C", "6": "C",
    "7": "D", "8": "D", "9": "D",
    "10": "E",
    "11": "F", "12": "F"
}


def normalize_class_level(class_str: str) -> Tuple[str, str]:
    """Menyelaraskan format kelas siswa menjadi tuple (grade_num, fase)."""
    if not class_str:
        return "", ""
    s = str(class_str).strip().upper()

    # Cek kata kunci Fase
    fase_match = re.search(r"\bFASE\s*([A-F])\b", s)
    if fase_match:
        f = fase_match.group(1)
        return ("10" if f == "E" else ""), f
    if s in ("A", "B", "C", "D", "E", "F"):
        return ("10" if s == "E" else ""), s

    # Cek angka 1-12
    num_match = re.search(r"\b(1[0-2]|[1-9])\b", s)
    if num_match:
        num = num_match.group(1)
        return num, GRADE_TO_FASE.get(num, "")

    # Cek romawi
    for r, num in sorted(ROMAN_TO_GRADE.items(), key=lambda x: len(x[0]), reverse=True):
        if re.search(r"\b" + re.escape(r) + r"\b", s):
            return num, GRADE_TO_FASE.get(num, "")

    return "", ""


def resolve_jenjang(class_str: str, jenjang: str = "") -> str:
    """Tentukan jenjang efektif untuk sebuah request.

    Aturan:
    - `jenjang` eksplisit selalu menang (sudah dinormalisasi ke huruf besar).
    - Tanpa `jenjang` pada kelas 10-12, default ke SMA agar payload lama
      tidak mencampur baris SMA dan SMK.
    - Kelas 1-9 diinferensikan dari angka kelas (SD/SMP) supaya filter tetap konsisten.
    - Selain itu kosong (tanpa filter jenjang, seperti perilaku sebelumnya).
    """
    explicit = (jenjang or "").strip().upper()
    if explicit:
        return explicit

    grade_num, _ = normalize_class_level(class_str)
    if grade_num in ("10", "11", "12"):
        return DEFAULT_JENJANG_SMA
    if grade_num in ("7", "8", "9"):
        return "SMP"
    if grade_num in ("1", "2", "3", "4", "5", "6"):
        return "SD"
    return DEFAULT_JENJANG_SMA


def _is_subject_match(sub_clean: str, mapel_item: str) -> bool:
    """Memeriksa kecocokan nama mata pelajaran secara ketat dan menggunakan kamus alias."""
    baku = MAPEL_ALIASES.get(sub_clean, sub_clean).lower()
    mapel_low = mapel_item.lower()

    # 1. Kecocokan persis dengan nama baku atau input bersih
    if mapel_low == baku or mapel_low == sub_clean:
        return True

    # 2. Kata input merupakan kata kunci utuh dalam nama mapel (mis. 'pancasila' dalam 'pendidikan pancasila')
    words = mapel_low.replace("(", " ").replace(")", " ").split()
    if sub_clean in words or baku in words:
        return True

    return False


def _load_raw_dataset() -> List[Dict[str, str]]:
    """Membaca dataset mentah silabus dengan caching in-memory."""
    global _CACHED_SILABUS_KM
    if _CACHED_SILABUS_KM is not None:
        return _CACHED_SILABUS_KM

    target_path = KURIKULUM_MERDEKA_PATH if KURIKULUM_MERDEKA_PATH.exists() else SILABUS_AWAL_PATH
    if not target_path.exists():
        log.warning("File dataset silabus tidak ditemukan di %s maupun %s", KURIKULUM_MERDEKA_PATH, SILABUS_AWAL_PATH)
        return []

    try:
        with open(target_path, "r", encoding="utf-8-sig", newline="") as f:
            _CACHED_SILABUS_KM = list(csv.DictReader(f))
            return _CACHED_SILABUS_KM
    except Exception as e:
        log.error("Gagal membaca file dataset silabus %s: %s", target_path, e)
        return []


def _normalize_row(r: Dict[str, str]) -> Dict[str, Any]:
    """Menstandarkan satu baris data silabus menjadi format kamus seragam."""
    if "Nama Topik" in r:
        # Format resmi kurikulum_merdeka.csv
        nama_topik = r.get("Nama Topik", "").strip()
        no_urut_raw = r.get("No. Urut", "0").strip()
        no_urut = int(no_urut_raw) if no_urut_raw.isdigit() else 0
        return {
            "id": r.get("ID", "").strip(),
            "jenjang": r.get("Jenjang", "").strip(),
            "kelas": r.get("Kelas", "").strip(),
            "fase": r.get("Fase", "").strip(),
            "mata_pelajaran": r.get("Mata Pelajaran", "").strip(),
            "status_mapel": r.get("Status Mapel", "").strip(),
            "jalur_disiplin": r.get("Jalur / Disiplin", "").strip(),
            "urutan_materi": str(no_urut),
            "no_urut": no_urut,
            "bab_unit": r.get("Bab / Unit", "").strip(),
            "nama_topik": nama_topik,
            "materi": nama_topik,  # Kompatibilitas mundur
            "elemen_fokus": r.get("Elemen / Fokus", "").strip(),
            "sub_materi": r.get("Sub-Materi", "").strip(),
            "relevansi_jurusan": r.get("Relevansi Jurusan/Karir", "").strip(),
            "kurikulum": "Kurikulum Merdeka",
            "prasyarat": "",
        }
    else:
        # Format awal silabus_awal.csv (cadangan)
        materi = r.get("materi", "").strip()
        no_raw = r.get("urutan_materi", "0").strip()
        no_urut = int(no_raw) if no_raw.isdigit() else 0
        kelas_raw = r.get("kelas", "").strip()
        num, fase = normalize_class_level(kelas_raw)
        return {
            "id": str(no_urut),
            "jenjang": "SMA" if num in ("10", "11", "12") else "",
            "kelas": num or kelas_raw,
            "fase": fase,
            "mata_pelajaran": r.get("mata_pelajaran", "").strip(),
            "status_mapel": "Wajib",
            "jalur_disiplin": "",
            "urutan_materi": str(no_urut),
            "no_urut": no_urut,
            "bab_unit": f"Bab {no_urut}",
            "nama_topik": materi,
            "materi": materi,
            "elemen_fokus": "",
            "sub_materi": "",
            "relevansi_jurusan": "",
            "kurikulum": r.get("kurikulum", "Kurikulum Merdeka").strip(),
            "prasyarat": r.get("prasyarat", "").strip(),
        }


def baca_silabus(
    subject: str,
    class_level: str = "",
    curriculum: str = "",
    jenjang: str = "",
    jalur_disiplin: str = "",
) -> List[Dict[str, Any]]:
    """Membaca dan memfilter silabus Kurikulum Merdeka berdasarkan
    mata pelajaran, kelas/fase, jenjang, jalur disiplin, dan kurikulum.

    Bila `jenjang` kosong dan `class_level` berada pada kelas 10-12, jenjang
    default SMA dipakai agar baris SMA dan SMK tidak pernah tercampur untuk
    request lama tanpa field `jenjang`.
    """
    raw_data = _load_raw_dataset()
    if not raw_data:
        return []

    sub_clean = subject.strip().lower()
    grade_num, fase = normalize_class_level(class_level)
    jenjang_clean = resolve_jenjang(class_level, jenjang)
    jalur_clean = jalur_disiplin.strip().lower()

    hasil: List[Dict[str, Any]] = []

    for item_raw in raw_data:
        item = _normalize_row(item_raw)
        mapel_item = item["mata_pelajaran"].strip()

        # 1. Pencocokan mata pelajaran yang aman dan ketat
        if not _is_subject_match(sub_clean, mapel_item):
            continue

        # 2. Filter Jenjang (jika diberikan)
        if jenjang_clean and item["jenjang"].upper() != jenjang_clean:
            continue

        # 3. Filter Kelas / Fase (jika diberikan)
        if grade_num:
            if item["kelas"] != grade_num:
                continue
        elif fase:
            if item["fase"].upper() != fase.upper():
                continue

        # 4. Filter Jalur / Disiplin (jika diberikan)
        if jalur_clean and item["jalur_disiplin"].lower() != jalur_clean:
            continue

        # 5. Filter Kurikulum (default Kurikulum Merdeka)
        if curriculum:
            cur_clean = curriculum.strip().lower()
            if cur_clean != "kurikulum merdeka" and item["kurikulum"].lower() != cur_clean:
                continue

        hasil.append(item)

    # Urutkan berdasarkan kelas lalu No. Urut topik
    def sort_key(x: Dict[str, Any]) -> Tuple[int, int]:
        kls = int(x["kelas"]) if str(x["kelas"]).isdigit() else 99
        return (kls, x["no_urut"])

    hasil.sort(key=sort_key)
    return hasil
