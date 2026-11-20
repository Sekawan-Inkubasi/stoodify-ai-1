"""Modul Material & Topic Predictor untuk Stoodify AI Engine.
Menganalisis riwayat tugas siswa dan silabus resmi Kurikulum Merdeka
(910 topik materi SD, SMP, SMA, SMK) untuk memprediksi materi/topik
pembelajaran berikutnya secara akurat dan kontekstual.
"""
import csv
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from llm import _call_with_timeout, call_llm, get_api_key, get_timeout

log = logging.getLogger("stoodify.predictor")


def _baca_akurasi(subject: str) -> dict:
    """Lazy wrapper baca akurasi historis untuk menghindari circular import."""
    try:
        from feedback import baca_akurasi_per_mapel  # noqa: PLC0415
        return baca_akurasi_per_mapel(subject)
    except Exception:
        return {}

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
    # TIK / Vokasi SMK
    "informatika": "Informatika",
    "tik": "Informatika",
    "ti": "Informatika",
    "pplg": "Pengembangan Perangkat Lunak dan Gim (PPLG)",
    "rpl": "Pengembangan Perangkat Lunak dan Gim (PPLG)",
    "dasar pemrograman": "Pengembangan Perangkat Lunak dan Gim (PPLG)",
    "pemrograman": "Pengembangan Perangkat Lunak dan Gim (PPLG)",
    "rekayasa perangkat lunak": "Pengembangan Perangkat Lunak dan Gim (PPLG)",
    "pengembangan perangkat lunak dan gim": "Pengembangan Perangkat Lunak dan Gim (PPLG)",
    "pengembangan perangkat lunak dan gim (pplg)": "Pengembangan Perangkat Lunak dan Gim (PPLG)",
    "tjkt": "Teknik Jaringan Komputer dan Telekomunikasi (TJKT)",
    "tkj": "Teknik Jaringan Komputer dan Telekomunikasi (TJKT)",
    "teknik komputer dan jaringan": "Teknik Jaringan Komputer dan Telekomunikasi (TJKT)",
    "teknik jaringan komputer dan telekomunikasi": "Teknik Jaringan Komputer dan Telekomunikasi (TJKT)",
    "teknik jaringan komputer dan telekomunikasi (tjkt)": "Teknik Jaringan Komputer dan Telekomunikasi (TJKT)",
    "pkk": "Projek Kreatif dan Kewirausahaan",
    "kewirausahaan": "Projek Kreatif dan Kewirausahaan",
    "projek kreatif dan kewirausahaan": "Projek Kreatif dan Kewirausahaan",
    "pkl": "Praktik Kerja Lapangan (PKL)",
    "praktik kerja lapangan": "Praktik Kerja Lapangan (PKL)",
    "praktik kerja lapangan (pkl)": "Praktik Kerja Lapangan (PKL)",
}

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
    """
    raw_data = _load_raw_dataset()
    if not raw_data:
        return []

    sub_clean = subject.strip().lower()
    grade_num, fase = normalize_class_level(class_level)
    jenjang_clean = jenjang.strip().upper()
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


def normalisasi_riwayat(task_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Menyelaraskan field riwayat tugas siswa agar konsisten untuk prompt."""
    data = []
    for t in task_history:
        data.append({
            "nama_tugas": t.get("title") or t.get("task_name") or "",
            "materi": t.get("material_name") or t.get("topic") or "",
            "deskripsi": t.get("description") or "",
            "tanggal": str(t.get("deadline") or t.get("task_date") or ""),
            "jenis": t.get("type") or "",
            "kesulitan_tugas": t.get("difficulty") or 3,
            "status": t.get("status") or "pending",
            "progres": t.get("progress") or 0,
            "catatan": t.get("notes") or "",
        })
    data.sort(key=lambda x: x["tanggal"])
    return data


def cari_topik_berikutnya(
    subject: str,
    task_history: List[Dict[str, Any]],
    silabus: List[Dict[str, Any]],
    class_level: str = "",
) -> Dict[str, Any]:
    """Menentukan materi pembelajaran berikutnya berdasarkan urutan No. Urut + 1
    pada silabus Kurikulum Merdeka.
    """
    history = task_history or []

    # Skenario 1: Silabus Kurikulum Merdeka tersedia
    if silabus:
        if not history:
            # Belum ada tugas: mulai dari topik pertama dalam silabus (No. Urut 1)
            first_topic = silabus[0]
            topik_nama = first_topic["nama_topik"]
            sub_mat = first_topic.get("sub_materi", "")
            return {
                "predicted_topic": topik_nama,
                "confidence": 55.0,
                "reason": (
                    f"Belum ada riwayat tugas pada mata pelajaran {subject}. "
                    f"Memulai dari bab awal Kurikulum Merdeka: {topik_nama}."
                ),
                "prerequisites": f"Pengantar dan konsep dasar {subject}",
                "preparation_suggestion": (
                    f"Pelajari konsep dasar {topik_nama}"
                    + (f" ({sub_mat[:100]}...)" if len(sub_mat) > 100 else f" ({sub_mat})")
                    + " sebelum pembahasan dimulai di kelas."
                    if sub_mat else f"Siapkan buku teks dan pelajari silabus awal {topik_nama}."
                ),
                "syllabus_reference": "available",
                "source": "fallback",
            }

        # Ada riwayat: cari kecocokan tugas siswa terhadap silabus dengan pembobotan skor
        scored_matches: List[Tuple[int, Dict[str, Any]]] = []
        for t in history:
            text_tokens = [
                str(t.get("materi") or t.get("material_name") or t.get("topic") or "").lower().strip(),
                str(t.get("nama_tugas") or t.get("title") or "").lower().strip(),
                str(t.get("deskripsi") or "").lower().strip(),
            ]
            for s in silabus:
                nama_topik_low = s["nama_topik"].lower()
                sub_low = s["sub_materi"].lower()
                for tok in text_tokens:
                    if not tok:
                        continue
                    if tok == nama_topik_low:
                        scored_matches.append((3, s))
                        break
                    elif tok in nama_topik_low or nama_topik_low in tok:
                        scored_matches.append((2, s))
                        break
                    elif tok in sub_low:
                        scored_matches.append((1, s))
                        break

        # Tentukan topik saat ini (prioritaskan skor tertinggi lalu no_urut tertinggi)
        if scored_matches:
            scored_matches.sort(key=lambda x: (
                x[0],  # Skor kecocokan (3=persis, 2=substring, 1=sub_materi)
                int(x[1]["kelas"]) if str(x[1]["kelas"]).isdigit() else 0,
                x[1]["no_urut"]
            ))
            current_item = scored_matches[-1][1]
        else:
            current_item = silabus[0]

        cur_no = current_item["no_urut"]
        cur_track = current_item["jalur_disiplin"]
        cur_jenjang = current_item["jenjang"]

        # Alur Kurikulum Merdeka: Topik berikutnya = No. Urut + 1
        target_no = cur_no + 1
        next_candidates = [
            s for s in silabus
            if s["no_urut"] == target_no
            and (not cur_track or s["jalur_disiplin"] == cur_track)
            and (not cur_jenjang or s["jenjang"] == cur_jenjang)
        ]

        if next_candidates:
            next_topic = next_candidates[0]
            is_end = False
        else:
            # Cek apakah ada topik dengan No. Urut lebih tinggi yang belum dibahas
            higher_topics = [
                s for s in silabus
                if s["no_urut"] > cur_no
                and (not cur_track or s["jalur_disiplin"] == cur_track)
                and (not cur_jenjang or s["jenjang"] == cur_jenjang)
            ]
            if higher_topics:
                next_topic = higher_topics[0]
                is_end = False
            else:
                next_topic = current_item
                is_end = True

        topik_nama = next_topic["nama_topik"]
        sub_mat = next_topic.get("sub_materi", "")

        if is_end:
            return {
                "predicted_topic": f"Pendalaman & Evaluasi {topik_nama}",
                "confidence": 80.0,
                "reason": (
                    f"Siswa telah menyelesaikan materi silabus {subject} hingga bab akhir "
                    f"({topik_nama}). Sesi selanjutnya difokuskan pada pengayaan dan evaluasi akhir."
                ),
                "prerequisites": f"Materi {topik_nama} dan bab-bab sebelumnya",
                "preparation_suggestion": f"Lakukan review menyeluruh rangkuman {subject} dan latihan soal akhir semester.",
                "syllabus_reference": "available",
                "source": "fallback",
            }

        prereq = (
            f"{current_item['nama_topik']}"
            + (f" ({current_item['sub_materi'][:90]}...)" if len(current_item.get("sub_materi", "")) > 90 else f" ({current_item.get('sub_materi', '')})")
            if current_item != next_topic and current_item.get("sub_materi")
            else f"Materi {current_item['nama_topik']} sebelumnya"
        )

        prep = (
            f"Pelajari konsep dasar {topik_nama}: {sub_mat[:110]}... sebelum dibahas di kelas."
            if len(sub_mat) > 110
            else f"Pelajari konsep dasar {topik_nama}: {sub_mat} sebelum dibahas di kelas."
            if sub_mat else f"Pelajari ringkasan materi {topik_nama} sebelum materi dimulai di kelas."
        )

        confidence = 85.0 if len(scored_matches) >= 2 else (75.0 if scored_matches else 65.0)

        return {
            "predicted_topic": topik_nama,
            "confidence": confidence,
            "reason": (
                f"Berdasarkan alur silabus Kurikulum Merdeka {next_topic.get('jenjang', '')} "
                f"Kelas {next_topic.get('kelas', '')}, setelah menyelesaikan {current_item['nama_topik']}, "
                f"topik berikutnya pada No. Urut {next_topic['no_urut']} adalah {topik_nama}."
            ),
            "prerequisites": prereq,
            "preparation_suggestion": prep,
            "syllabus_reference": "available",
            "source": "fallback",
        }

    # Skenario 2: Tidak ada silabus, gunakan riwayat tugas terakhir
    if history:
        last_task = history[-1]
        title = last_task.get("nama_tugas") or last_task.get("title") or f"materi {subject}"
        topic = last_task.get("materi") or last_task.get("material_name") or last_task.get("topic") or title
        return {
            "predicted_topic": f"Lanjutan {topic}",
            "confidence": 45.0,
            "reason": f"Berdasarkan analisis {len(history)} tugas terakhir, melanjutkan pembahasan {topic}.",
            "prerequisites": f"Materi {topic} sebelumnya",
            "preparation_suggestion": f"Ulangi rangkuman dan latihan soal {topic} sebelum masuk ke bab lanjutan.",
            "syllabus_reference": "unavailable",
            "source": "fallback",
        }

    # Skenario 3: Riwayat kosong dan tidak ada silabus
    return {
        "predicted_topic": f"Materi Pengantar {subject}",
        "confidence": 35.0,
        "reason": f"Belum ada riwayat tugas pada mata pelajaran {subject} dan silabus tidak ditemukan.",
        "prerequisites": f"{subject} dasar",
        "preparation_suggestion": f"Siapkan catatan dan baca buku teks pengantar {subject}.",
        "syllabus_reference": "unavailable",
        "source": "fallback",
    }


def fallback_prediction(
    subject: str,
    difficulty: Optional[int] = None,
    task_history: Optional[List[Dict[str, Any]]] = None,
    silabus: Optional[List[Dict[str, Any]]] = None,
    class_level: str = "",
) -> Dict[str, Any]:
    """Fallback deterministik ketika LLM offline, timeout, atau API key belum disetel.

    Confidence dasar disesuaikan dengan akurasi historis prediksi mata pelajaran yang sama:
    - Jika akurasi historis ≥ 70%  → confidence tidak dikurangi (terpercaya)
    - Jika akurasi historis < 50%  → confidence dikurangi 10 poin (perlu hati-hati)
    - Belum ada data               → confidence tidak disesuaikan
    """
    history = task_history or []
    sil = silabus if silabus is not None else baca_silabus(subject, class_level=class_level)
    hasil = cari_topik_berikutnya(subject, history, sil, class_level=class_level)

    # Sesuaikan confidence berdasarkan akurasi historis
    akurasi_info = _baca_akurasi(subject)
    akurasi_pct = akurasi_info.get("akurasi")
    if akurasi_pct is not None and "confidence" in hasil:
        if akurasi_pct < 50.0:
            hasil["confidence"] = max(0.0, hasil["confidence"] - 10.0)
        # Jika ≥ 70%, biarkan confidence apa adanya (sudah terpercaya)

    return hasil


def build_prediction_prompt(
    subject: str,
    difficulty: Optional[int],
    data_riwayat: List[Dict[str, Any]],
    silabus: List[Dict[str, Any]],
    class_level: str = "",
    curriculum: str = "",
) -> str:
    """Menyusun prompt analisis materi untuk model LLM dengan konteks silabus Kurikulum Merdeka."""
    ringkasan_silabus = [
        {
            "no_urut": s["no_urut"],
            "bab_unit": s["bab_unit"],
            "nama_topik": s["nama_topik"],
            "elemen_fokus": s["elemen_fokus"],
            "sub_materi": s["sub_materi"],
            "kelas": s["kelas"],
            "jenjang": s.get("jenjang", ""),
            "jalur_disiplin": s.get("jalur_disiplin", ""),
        }
        for s in silabus[:25]
    ]

    # Sertakan akurasi historis agar LLM tahu seberapa tepat prediksi sebelumnya
    akurasi_info = _baca_akurasi(subject)
    akurasi_total = akurasi_info.get("total", 0)
    akurasi_pct = akurasi_info.get("akurasi")
    if akurasi_total and akurasi_pct is not None:
        akurasi_teks = (
            f"CATATAN AKURASI HISTORIS ({subject}): "
            f"{akurasi_pct:.1f}% dari {akurasi_total} prediksi sebelumnya dinilai tepat oleh siswa. "
            f"{'Pertahankan pola prediksi saat ini.' if akurasi_pct >= 70 else 'Tingkatkan akurasi dengan mengikuti alur silabus lebih ketat.'}"
        )
    else:
        akurasi_teks = f"CATATAN AKURASI HISTORIS ({subject}): Belum ada data feedback dari siswa."

    return f"""Kamu adalah AI pendidikan Stoodify yang bertugas memprediksi materi
pembelajaran selanjutnya berdasarkan riwayat tugas siswa dan acuan silabus Kurikulum Merdeka.

MATA PELAJARAN:
{subject}

TINGKAT KESULITAN MATA PELAJARAN:
{difficulty if difficulty is not None else "Tidak tersedia"}

TINGKAT KELAS:
{class_level if class_level else "Kurikulum Merdeka"}

KURIKULUM:
{curriculum if curriculum else "Kurikulum Merdeka"}

{akurasi_teks}

RIWAYAT TUGAS SISWA ({len(data_riwayat)} tugas tercatat):
{json.dumps(data_riwayat, ensure_ascii=False, indent=2)}

DATA SILABUS KURIKULUM ({len(ringkasan_silabus)} topik acuan terurut):
{json.dumps(ringkasan_silabus, ensure_ascii=False, indent=2)}

PETUNJUK ANALISIS PEDAGOGIS:
1. Analisis judul, materi, deskripsi, jenis tugas, status, progres, dan catatan setiap tugas siswa.
2. Identifikasi topik/bab Kurikulum Merdeka terakhir yang telah dipelajari atau diselesaikan siswa.
3. Berdasarkan alur silabus Kurikulum Merdeka: materi pembelajaran selanjutnya adalah topik dengan No. Urut = No. Urut sekarang + 1 pada jenjang dan disiplin yang sama.
4. Manfaatkan kolom 'sub_materi' dari topik yang diprediksi untuk merumuskan saran persiapan belajar ("Curi Start") yang sangat konkret dan terarah.
5. Tentukan prasyarat (prerequisites) berdasarkan konsep bab sebelumnya yang diperlukan untuk memahami bab baru ini.
6. Berikan tingkat keyakinan (confidence):
   - Antara 0.85 - 0.95 jika alur tugas siswa runtut dan cocok persis dengan silabus.
   - Antara 0.60 - 0.75 jika riwayat tugas masih sedikit (1-2 tugas) atau bersifat inferensi.
   - Antara 0.40 - 0.55 jika riwayat tugas tidak spesifik.
7. Tuliskan alasan prediksi (reason) yang ringkas (1-2 kalimat) menjelaskan dasar akademis pemilihan materi tersebut.

Keluarkan HANYA format JSON valid tanpa markdown tambahan:
{{
    "predicted_topic": "nama materi yang diprediksi",
    "confidence": 0.88,
    "reason": "alasan analisis prediksi dalam 1-2 kalimat jelas",
    "prerequisites": "materi atau konsep dasar yang perlu dikuasai",
    "preparation_suggestion": "saran konkret langkah persiapan sebelum kelas berikutnya",
    "syllabus_reference": "available atau unavailable"
}}

Catatan: confidence harus berupa angka antara 0.0 sampai 1.0 (atau 0 sampai 100)."""


def predict_material(
    subject: str,
    difficulty: Optional[int] = None,
    task_history: Optional[List[Dict[str, Any]]] = None,
    class_level: str = "",
    curriculum: str = "",
    timeout: Optional[float] = None,
    call_fn: Any = None,
) -> Dict[str, Any]:
    """Fungsi utama prediksi materi yang menggabungkan RAG silabus Kurikulum Merdeka, LLM, dan fallback."""
    raw_history = task_history or []
    data_riwayat = normalisasi_riwayat(raw_history)
    silabus = baca_silabus(subject, class_level=class_level, curriculum=curriculum)

    call = call_fn
    if call is None:
        if not get_api_key():
            log.info("LLM_API_KEY tidak ditemukan, beralih ke fallback deterministik Kurikulum Merdeka.")
            return fallback_prediction(subject, difficulty, raw_history, silabus, class_level=class_level)
        call = call_llm

    effective_timeout = get_timeout() if timeout is None else timeout
    prompt = build_prediction_prompt(
        subject=subject,
        difficulty=difficulty,
        data_riwayat=data_riwayat,
        silabus=silabus,
        class_level=class_level,
        curriculum=curriculum,
    )

    try:
        raw_output = _call_with_timeout(call, prompt, effective_timeout)
    except Exception as e:
        log.warning("Panggilan LLM prediksi materi gagal: %s. Menggunakan fallback Kurikulum Merdeka.", e)
        return fallback_prediction(subject, difficulty, raw_history, silabus, class_level=class_level)

    # Parsing output JSON LLM
    try:
        clean_text = raw_output.strip()
        if "```" in clean_text:
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", clean_text, re.DOTALL)
            if match:
                clean_text = match.group(1)
            else:
                clean_text = clean_text.replace("```json", "").replace("```", "").strip()

        hasil = json.loads(clean_text)
        if not isinstance(hasil, dict):
            raise ValueError("Respons LLM bukan dictionary.")

        predicted_topic = str(hasil.get("predicted_topic", "")).strip()
        if not predicted_topic:
            raise ValueError("Respons LLM tidak memiliki predicted_topic.")

        # Parsing confidence
        confidence = float(hasil.get("confidence", 0.0))
        if 0.0 <= confidence <= 1.0:
            confidence = round(confidence * 100, 2)
        else:
            confidence = round(min(max(confidence, 0.0), 100.0), 2)

        # Parsing prerequisites
        prereqs = hasil.get("prerequisites", "")
        if isinstance(prereqs, list):
            prereqs_str = ", ".join(str(p).strip() for p in prereqs if p)
        else:
            prereqs_str = str(prereqs).strip()

        prep = str(hasil.get("preparation_suggestion", "")).strip()
        reason = str(hasil.get("reason", "")).strip()

        return {
            "predicted_topic": predicted_topic,
            "confidence": confidence,
            "reason": reason or f"Prediksi berdasarkan silabus dan riwayat {len(data_riwayat)} tugas {subject}.",
            "prerequisites": prereqs_str or f"Konsep dasar {subject}",
            "preparation_suggestion": prep or f"Pelajari bab {predicted_topic} sebelum kelas dimulai.",
            "syllabus_reference": "available" if silabus else "unavailable",
            "source": "ai",
        }
    except Exception as e:
        log.warning("Gagal mem-parsing output LLM (%s): %s. Menggunakan fallback Kurikulum Merdeka.", e, raw_output[:120])
        return fallback_prediction(subject, difficulty, raw_history, silabus, class_level=class_level)
