"""Modul Material & Topic Predictor untuk Stoodify AI Engine.
Menganalisis riwayat tugas siswa dan silabus Kurikulum Merdeka untuk
memprediksi materi/topik pembelajaran berikutnya.
"""
import csv
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from llm import _call_with_timeout, call_llm, get_api_key, get_timeout

log = logging.getLogger("stoodify.predictor")

BASE_DIR = Path(__file__).resolve().parent
SILABUS_PATH = BASE_DIR / "DATA" / "silabus_awal.csv"


def baca_silabus(subject: str, class_level: str = "", curriculum: str = "") -> List[Dict[str, str]]:
    """Membaca silabus dari CSV berdasarkan mata pelajaran, kelas, dan kurikulum."""
    if not SILABUS_PATH.exists():
        log.warning("File silabus tidak ditemukan di: %s", SILABUS_PATH)
        return []

    try:
        with open(SILABUS_PATH, "r", encoding="utf-8-sig", newline="") as file:
            silabus = list(csv.DictReader(file))
    except Exception as e:
        log.error("Gagal membaca file silabus: %s", e)
        return []

    hasil = []
    sub_clean = subject.strip().lower()

    for item in silabus:
        mapel_item = item.get("mata_pelajaran", "").strip().lower()
        if mapel_item != sub_clean:
            continue

        if class_level and item.get("kelas", "").strip().upper() != class_level.strip().upper():
            continue

        if curriculum and item.get("kurikulum", "").strip().lower() != curriculum.strip().lower():
            continue

        hasil.append(item)

    hasil.sort(key=lambda x: int(x.get("urutan_materi", 0)) if str(x.get("urutan_materi", "")).isdigit() else 999)
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
    # Urutkan berdasarkan tanggal jika tersedia
    data.sort(key=lambda x: x["tanggal"])
    return data


def build_prediction_prompt(
    subject: str,
    difficulty: Optional[int],
    data_riwayat: List[Dict[str, Any]],
    silabus: List[Dict[str, str]],
    class_level: str = "",
    curriculum: str = "",
) -> str:
    """Menyusun prompt analisis materi untuk model LLM."""
    return f"""Kamu adalah AI pendidikan Stoodify yang bertugas memprediksi materi
pembelajaran selanjutnya berdasarkan riwayat tugas siswa dan acuan silabus kurikulum.

MATA PELAJARAN:
{subject}

TINGKAT KESULITAN MATA PELAJARAN:
{difficulty if difficulty is not None else "Tidak tersedia"}

TINGKAT KELAS:
{class_level if class_level else "Fase F / Kelas XI-XII SMA/SMK"}

KURIKULUM:
{curriculum if curriculum else "Kurikulum Merdeka"}

RIWAYAT TUGAS SISWA ({len(data_riwayat)} tugas tercatat):
{json.dumps(data_riwayat, ensure_ascii=False, indent=2)}

DATA SILABUS KURIKULUM ({len(silabus)} topik acuan):
{json.dumps(silabus, ensure_ascii=False, indent=2)}

PETUNJUK ANALISIS PEDAGOGIS:
1. Analisis judul, materi, deskripsi, jenis tugas, status, progres, dan catatan setiap tugas siswa.
2. Prioritaskan isi deskripsi dan materi tugas untuk memahami bab apa saja yang telah dibahas.
3. Hubungkan perkembangan materi dari riwayat tugas terhadap urutan materi pada silabus.
4. Jika silabus tersedia, cari topik berikutnya yang belum dibahas siswa berdasarkan alur prasyarat.
5. Jika silabus tidak mencakup materi siswa, lakukan inferensi materi lanjutan yang paling logis secara akademis.
6. Pertimbangkan tingkat kesulitan mata pelajaran dan tugas sebagai konteks tambahan.
7. Jika riwayat tugas masih sedikit (1-2 tugas), berikan tingkat keyakinan (confidence) yang lebih konservatif (antara 0.40 - 0.65).
8. Tuliskan alasan prediksi yang spesifik dan mudah dipahami siswa dalam bahasa Indonesia.
9. Tentukan prasyarat yang relevan dan berikan saran persiapan belajar ("Curi Start") yang aplikatif.

Keluarkan HANYA format JSON valid tanpa markdown tambahan:
{{
    "predicted_topic": "nama materi yang diprediksi",
    "confidence": 0.85,
    "reason": "alasan analisis prediksi dalam 1-2 kalimat jelas",
    "prerequisites": "materi atau konsep dasar yang perlu dikuasai",
    "preparation_suggestion": "saran konkret langkah persiapan sebelum kelas berikutnya",
    "syllabus_reference": "available atau unavailable"
}}

Catatan: confidence harus berupa angka antara 0.0 sampai 1.0 (atau 0 sampai 100)."""


def fallback_prediction(
    subject: str,
    difficulty: Optional[int] = None,
    task_history: Optional[List[Dict[str, Any]]] = None,
    silabus: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Fallback deterministik ketika LLM offline, timeout, atau API key belum disetel."""
    history = task_history or []
    sil = silabus or []

    # Skenario 1: Ada silabus kurikulum
    if sil:
        # Coba cocokkan dengan topik yang belum ada di riwayat
        riwayat_topics = {
            str(t.get("material_name") or t.get("topic") or t.get("title") or "").lower()
            for t in history
        }
        next_topic = None
        for item in sil:
            materi = item.get("materi", "")
            if materi.lower() not in riwayat_topics:
                next_topic = item
                break

        if not next_topic:
            next_topic = sil[-1]

        topic_name = next_topic.get("materi", f"Lanjutan {subject}")
        prereq = next_topic.get("prasyarat") or f"Konsep dasar {subject}"
        return {
            "predicted_topic": topic_name,
            "confidence": 70.0 if history else 55.0,
            "reason": f"Berdasarkan urutan silabus Kurikulum Merdeka untuk {subject}.",
            "prerequisites": prereq,
            "preparation_suggestion": f"Pelajari konsep dasar {topic_name} sebelum pembahasan di kelas.",
            "syllabus_reference": "available",
            "source": "fallback",
        }

    # Skenario 2: Tidak ada silabus, gunakan riwayat tugas terakhir
    if history:
        last_task = history[-1]
        title = last_task.get("title") or last_task.get("task_name") or f"materi {subject}"
        topic = last_task.get("material_name") or last_task.get("topic") or title
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
        "reason": f"Belum ada riwayat tugas pada mata pelajaran {subject}.",
        "prerequisites": f"{subject} dasar",
        "preparation_suggestion": f"Siapkan catatan dan baca buku teks pengantar {subject}.",
        "syllabus_reference": "unavailable",
        "source": "fallback",
    }


def predict_material(
    subject: str,
    difficulty: Optional[int] = None,
    task_history: Optional[List[Dict[str, Any]]] = None,
    class_level: str = "",
    curriculum: str = "",
    timeout: Optional[float] = None,
    call_fn: Any = None,
) -> Dict[str, Any]:
    """Fungsi utama prediksi materi yang menggabungkan RAG silabus, LLM, dan fallback."""
    raw_history = task_history or []
    data_riwayat = normalisasi_riwayat(raw_history)
    silabus = baca_silabus(subject, class_level, curriculum)

    call = call_fn
    if call is None:
        if not get_api_key():
            log.info("LLM_API_KEY tidak ditemukan, beralih ke fallback deterministik.")
            return fallback_prediction(subject, difficulty, raw_history, silabus)
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
        log.warning("Panggilan LLM prediksi materi gagal: %s. Menggunakan fallback.", e)
        return fallback_prediction(subject, difficulty, raw_history, silabus)

    # Parsing output JSON LLM
    try:
        # Bersihkan potensi markdown backticks ```json ... ```
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

        # Parsing prerequisites (jika berupa array, gabungkan jadi string)
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
            "reason": reason or f"Prediksi berdasarkan riwayat {len(data_riwayat)} tugas {subject}.",
            "prerequisites": prereqs_str or f"Konsep dasar {subject}",
            "preparation_suggestion": prep or f"Pelajari bab {predicted_topic} sebelum kelas dimulai.",
            "syllabus_reference": "available" if silabus else "unavailable",
            "source": "ai",
        }
    except Exception as e:
        log.warning("Gagal mem-parsing output LLM (%s): %s. Menggunakan fallback.", e, raw_output[:120])
        return fallback_prediction(subject, difficulty, raw_history, silabus)
