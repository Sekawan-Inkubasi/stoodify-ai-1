"""Penyusun prompt prediksi materi untuk LLM.

Dipisahkan dari `predictor.py` agar alur prediksi tetap ringkas dan prompt dapat
diuji terpisah. Prompt membedakan dua kondisi:

- silabus tersedia: LLM diminta mengikuti alur No. Urut + 1 dari silabus;
- silabus tidak tersedia (mis. mapel kejuruan SMK): LLM hanya boleh
  menyimpulkan dari riwayat tugas dan konteks, tanpa mengaku punya rujukan
  kurikulum.
"""
import json
from typing import Any, Dict, List, Optional

SILABUS_AVAILABLE_PROMPT = """Kamu adalah AI pendidikan Stoodify yang bertugas memprediksi materi
pembelajaran selanjutnya berdasarkan riwayat tugas siswa dan acuan silabus Kurikulum Merdeka.

MATA PELAJARAN:
{subject}

JENJANG / TINGKAT KELAS:
{jenjang_teks}

TINGKAT KESULITAN MATA PELAJARAN:
{difficulty_teks}

KURIKULUM:
{curriculum_teks}

{akurasi_teks}

RIWAYAT TUGAS SISWA ({jumlah_riwayat} tugas tercatat):
{riwayat_json}

DATA SILABUS KURIKULUM ({jumlah_silabus} topik acuan terurut):
{silabus_json}

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
    "preparation_suggestion": "saran konkret langkah persiapan sebelum kelas berikutnya"
}}

Catatan: confidence harus berupa angka antara 0.0 sampai 1.0. Jangan sertakan field
syllabus_reference; sistem menandainya otomatis."""

SILABUS_UNAVAILABLE_PROMPT = """Kamu adalah AI pendidikan Stoodify yang membantu siswa memprediksi
materi pembelajaran selanjutnya.

MATA PELAJARAN:
{subject}

JENJANG / TINGKAT KELAS:
{jenjang_teks}

TINGKAT KESULITAN MATA PELAJARAN:
{difficulty_teks}

KURIKULUM:
{curriculum_teks}

{akurasi_teks}

RIWAYAT TUGAS SISWA ({jumlah_riwayat} tugas tercatat):
{riwayat_json}

STATUS RUJUKAN SILABUS: TIDAK TERSEDIA.

Sistem tidak memiliki data silabus untuk mata pelajaran ini (umumnya mata pelajaran
kejuruan SMK yang berbeda antarprogram keahlian). Prediksi harus murni inferensi dari
riwayat tugas dan konteks di atas.

PETUNJUK:
1. JANGAN mengaku memiliki atau menemukan rujukan kurikulum/silabus resmi untuk mapel ini.
2. JANGAN mengarang nomor bab, nomor urut, atau nama bab silabus.
3. Simpulkan topik lanjutan yang paling wajar dari pola tugas siswa, jenis tugas, dan progres.
4. Jika riwayat tugas sangat minim, turunkan confidence dan sebutkan keterbatasannya di reason.
5. Berikan confidence antara 0.30 - 0.75 sesuai kekuatan bukti yang tersedia.
6. Tulis alasan prediksi (reason) yang ringkas dan jujur tentang dasar inferensinya.

Keluarkan HANYA format JSON valid tanpa markdown tambahan:
{{
    "predicted_topic": "nama materi yang diprediksi",
    "confidence": 0.55,
    "reason": "alasan inferensi dalam 1-2 kalimat",
    "prerequisites": "materi atau konsep dasar yang perlu dikuasai",
    "preparation_suggestion": "saran konkret langkah persiapan sebelum kelas berikutnya"
}}

Catatan: confidence harus berupa angka antara 0.0 sampai 1.0. Jangan sertakan field
syllabus_reference; sistem menandainya otomatis."""


MAX_HISTORY_ITEMS = 20
_FIELD_MAX_CHARS = {
    "nama_tugas": 150,
    "materi": 150,
    "deskripsi": 300,
    "catatan": 200,
}


def _ringkas_riwayat(data_riwayat: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Batasi jumlah dan panjang teks riwayat tugas agar prompt LLM tetap terkendali."""
    terbaru = data_riwayat[-MAX_HISTORY_ITEMS:]
    ringkas: List[Dict[str, Any]] = []
    for item in terbaru:
        salinan = dict(item)
        for field, max_len in _FIELD_MAX_CHARS.items():
            val = salinan.get(field)
            if isinstance(val, str) and len(val) > max_len:
                salinan[field] = val[:max_len].rstrip() + "..."
        ringkas.append(salinan)
    return ringkas


def _ringkas_silabus(silabus: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ambil maksimal 25 topik pertama silabus untuk konteks prompt."""
    return [
        {
            "no_urut": s.get("no_urut", 0),
            "bab_unit": s.get("bab_unit", ""),
            "nama_topik": s.get("nama_topik", ""),
            "elemen_fokus": s.get("elemen_fokus", ""),
            "sub_materi": s.get("sub_materi", ""),
            "kelas": s.get("kelas", ""),
            "jenjang": s.get("jenjang", ""),
            "jalur_disiplin": s.get("jalur_disiplin", ""),
        }
        for s in silabus[:25]
    ]


def _teks_akurasi(subject: str, akurasi_info: Dict[str, Any]) -> str:
    """Susun catatan akurasi historis untuk prompt."""
    total = akurasi_info.get("total", 0)
    pct = akurasi_info.get("akurasi")
    if total and pct is not None:
        saran = (
            "Pertahankan pola prediksi saat ini."
            if pct >= 70
            else "Tingkatkan akurasi dengan mengikuti alur silabus lebih ketat."
        )
        return (
            f"CATATAN AKURASI HISTORIS ({subject}): "
            f"{pct:.1f}% dari {total} prediksi sebelumnya dinilai tepat oleh siswa. {saran}"
        )
    return f"CATATAN AKURASI HISTORIS ({subject}): Belum ada data feedback dari siswa."


def build_prediction_prompt(
    subject: str,
    difficulty: Optional[int],
    data_riwayat: List[Dict[str, Any]],
    silabus: List[Dict[str, Any]],
    class_level: str = "",
    curriculum: str = "",
    jenjang: str = "",
    akurasi_info: Optional[Dict[str, Any]] = None,
) -> str:
    """Menyusun prompt LLM, memilih varian sesuai ketersediaan silabus.

    `silabus` kosong berarti materi tidak tercakup dataset (mis. mapel kejuruan
    SMK). Prompt varian kedua dipakai agar LLM tidak mengklaim rujukan kurikulum
    yang tidak diberikan.
    """
    ringkasan = _ringkas_silabus(silabus)
    riwayat_ringkas = _ringkas_riwayat(data_riwayat)
    jenjang_bagian = " ".join(p for p in (jenjang.strip(), class_level.strip()) if p)
    jenjang_teks = jenjang_bagian or "Kurikulum Merdeka"

    nilai = {
        "subject": subject,
        "jenjang_teks": jenjang_teks,
        "difficulty_teks": difficulty if difficulty is not None else "Tidak tersedia",
        "curriculum_teks": curriculum or "Kurikulum Merdeka",
        "akurasi_teks": _teks_akurasi(subject, akurasi_info or {}),
        "jumlah_riwayat": len(riwayat_ringkas),
        "riwayat_json": json.dumps(riwayat_ringkas, ensure_ascii=False, indent=2),
        "jumlah_silabus": len(ringkasan),
        "silabus_json": json.dumps(ringkasan, ensure_ascii=False, indent=2),
    }

    templat = SILABUS_AVAILABLE_PROMPT if silabus else SILABUS_UNAVAILABLE_PROMPT
    return templat.format(**nilai)
