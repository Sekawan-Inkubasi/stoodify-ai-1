"""Modul Material & Topic Predictor untuk Stoodify AI Engine.

Menggabungkan retrieval silabus Kurikulum Merdeka (`predictor_data`), prompt LLM
(`predictor_prompts`), dan fallback deterministik.

Cakupan silabus runtime: seluruh SD/SMP/SMA dan mata pelajaran umum SMK. Mapel
kejuruan SMK tidak ada di dataset sehingga silabusnya kosong dan prediksinya
diarahkan ke LLM (atau fallback generik yang jujur saat LLM gagal).
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from llm import _call_with_timeout, call_llm, get_api_key, get_timeout
from predictor_data import (
    DEFAULT_JENJANG_SMA,
    MAPEL_ALIASES,
    SUPPORTED_JENJANG,
    baca_silabus,
    normalize_class_level,
    resolve_jenjang,
)
from predictor_prompts import build_prediction_prompt

log = logging.getLogger("stoodify.predictor")

__all__ = [
    "MAPEL_ALIASES",
    "SUPPORTED_JENJANG",
    "DEFAULT_JENJANG_SMA",
    "baca_silabus",
    "build_prediction_prompt",
    "cari_topik_berikutnya",
    "fallback_prediction",
    "normalisasi_riwayat",
    "normalize_class_level",
    "predict_material",
    "resolve_jenjang",
]


def _baca_akurasi(subject: str) -> dict:
    """Lazy wrapper baca akurasi historis untuk menghindari circular import."""
    try:
        from feedback import baca_akurasi_per_mapel  # noqa: PLC0415
        return baca_akurasi_per_mapel(subject)
    except Exception:
        return {}


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


def _hasil_fallback_silabus(
    topik: str,
    confidence: float,
    reason: str,
    prerequisites: str,
    preparation_suggestion: str,
) -> Dict[str, Any]:
    """Bentuk hasil fallback ketika silabus tersedia."""
    return {
        "predicted_topic": topik,
        "confidence": confidence,
        "reason": reason,
        "prerequisites": prerequisites,
        "preparation_suggestion": preparation_suggestion,
        "syllabus_reference": "available",
        "source": "fallback",
    }


def _cari_kecocokan_riwayat(
    history: List[Dict[str, Any]], silabus: List[Dict[str, Any]]
) -> List[Tuple[int, Dict[str, Any]]]:
    """Skor kecocokan tiap tugas siswa terhadap topik silabus.

    Skor 3 = judul/materi persis sama dengan Nama Topik, 2 = saling substring,
    1 = hanya cocok pada Sub-Materi.
    """
    scored: List[Tuple[int, Dict[str, Any]]] = []
    for t in history:
        tokens = [
            str(t.get("materi") or t.get("material_name") or t.get("topic") or "").lower().strip(),
            str(t.get("nama_tugas") or t.get("title") or "").lower().strip(),
            str(t.get("deskripsi") or "").lower().strip(),
        ]
        for s in silabus:
            nama_topik_low = s["nama_topik"].lower()
            sub_low = s["sub_materi"].lower()
            for tok in tokens:
                if not tok:
                    continue
                if tok == nama_topik_low:
                    scored.append((3, s))
                    break
                elif tok in nama_topik_low or nama_topik_low in tok:
                    scored.append((2, s))
                    break
                elif tok in sub_low:
                    scored.append((1, s))
                    break
    return scored


def _pilih_topik_berikutnya(
    silabus: List[Dict[str, Any]],
    current_item: Dict[str, Any],
) -> Tuple[Dict[str, Any], bool]:
    """Tentukan topik berikutnya (No. Urut + 1) dalam jenjang & jalur yang sama."""
    cur_no = current_item["no_urut"]
    cur_track = current_item["jalur_disiplin"]
    cur_jenjang = current_item["jenjang"]

    next_candidates = [
        s for s in silabus
        if s["no_urut"] == cur_no + 1
        and (not cur_track or s["jalur_disiplin"] == cur_track)
        and (not cur_jenjang or s["jenjang"] == cur_jenjang)
    ]
    if next_candidates:
        return next_candidates[0], False

    higher_topics = [
        s for s in silabus
        if s["no_urut"] > cur_no
        and (not cur_track or s["jalur_disiplin"] == cur_track)
        and (not cur_jenjang or s["jenjang"] == cur_jenjang)
    ]
    if higher_topics:
        return higher_topics[0], False

    return current_item, True


def cari_topik_berikutnya(
    subject: str,
    task_history: List[Dict[str, Any]],
    silabus: List[Dict[str, Any]],
    class_level: str = "",
) -> Dict[str, Any]:
    """Menentukan materi berikutnya: alur No. Urut + 1 bila silabus ada,
    atau inferensi dari riwayat tugas bila silabus tidak tersedia.
    """
    history = task_history or []

    if silabus:
        if not history:
            first_topic = silabus[0]
            topik_nama = first_topic["nama_topik"]
            sub_mat = first_topic.get("sub_materi", "")
            prep = (
                f"Pelajari konsep dasar {topik_nama}: {sub_mat} sebelum dibahas di kelas."
                if sub_mat
                else f"Siapkan buku teks dan pelajari silabus awal {topik_nama}."
            )
            return _hasil_fallback_silabus(
                topik_nama,
                55.0,
                (
                    f"Belum ada riwayat tugas pada mata pelajaran {subject}. "
                    f"Memulai dari bab awal Kurikulum Merdeka: {topik_nama}."
                ),
                f"Pengantar dan konsep dasar {subject}",
                prep,
            )

        scored_matches = _cari_kecocokan_riwayat(history, silabus)
        if scored_matches:
            scored_matches.sort(key=lambda x: (
                x[0],
                int(x[1]["kelas"]) if str(x[1]["kelas"]).isdigit() else 0,
                x[1]["no_urut"],
            ))
            current_item = scored_matches[-1][1]
        else:
            current_item = silabus[0]

        next_topic, is_end = _pilih_topik_berikutnya(silabus, current_item)
        topik_nama = next_topic["nama_topik"]
        sub_mat = next_topic.get("sub_materi", "")

        if is_end:
            return _hasil_fallback_silabus(
                f"Pendalaman & Evaluasi {topik_nama}",
                80.0,
                (
                    f"Siswa telah menyelesaikan materi silabus {subject} hingga bab akhir "
                    f"({topik_nama}). Sesi selanjutnya difokuskan pada pengayaan dan evaluasi akhir."
                ),
                f"Materi {topik_nama} dan bab-bab sebelumnya",
                f"Lakukan review menyeluruh rangkuman {subject} dan latihan soal akhir semester.",
            )

        prereq = (
            f"{current_item['nama_topik']} ({current_item['sub_materi']})"
            if current_item != next_topic and current_item.get("sub_materi")
            else f"Materi {current_item['nama_topik']} sebelumnya"
        )
        prep = (
            f"Pelajari konsep dasar {topik_nama}: {sub_mat} sebelum dibahas di kelas."
            if sub_mat
            else f"Pelajari ringkasan materi {topik_nama} sebelum materi dimulai di kelas."
        )
        confidence = 85.0 if len(scored_matches) >= 2 else (75.0 if scored_matches else 65.0)

        return _hasil_fallback_silabus(
            topik_nama,
            confidence,
            (
                f"Berdasarkan alur silabus Kurikulum Merdeka {next_topic.get('jenjang', '')} "
                f"Kelas {next_topic.get('kelas', '')}, setelah menyelesaikan {current_item['nama_topik']}, "
                f"topik berikutnya pada No. Urut {next_topic['no_urut']} adalah {topik_nama}."
            ),
            prereq,
            prep,
        )

    if history:
        last_task = history[-1]
        title = last_task.get("nama_tugas") or last_task.get("title") or f"materi {subject}"
        topic = last_task.get("materi") or last_task.get("material_name") or last_task.get("topic") or title
        return {
            "predicted_topic": f"Lanjutan {topic}",
            "confidence": 45.0,
            "reason": (
                f"Silabus mapel {subject} tidak tersedia pada dataset; prediksi disusun dari "
                f"{len(history)} tugas terakhir dengan melanjutkan pembahasan {topic}."
            ),
            "prerequisites": f"Materi {topic} sebelumnya",
            "preparation_suggestion": f"Ulangi rangkuman dan latihan soal {topic} sebelum masuk ke bab lanjutan.",
            "syllabus_reference": "unavailable",
            "source": "fallback",
        }

    return {
        "predicted_topic": f"Materi Pengantar {subject}",
        "confidence": 35.0,
        "reason": f"Belum ada riwayat tugas pada mata pelajaran {subject} dan silabus tidak tersedia pada dataset.",
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
    jenjang: str = "",
) -> Dict[str, Any]:
    """Fallback deterministik ketika LLM offline, timeout, atau API key belum disetel.

    Bila `silabus` tidak diberikan, silabus dibaca ulang dengan filter jenjang yang
    sama seperti alur utama agar hasil fallback tidak mencampur SMA dan SMK.
    """
    history = task_history or []
    sil = (
        silabus
        if silabus is not None
        else baca_silabus(subject, class_level=class_level, jenjang=jenjang)
    )
    hasil = cari_topik_berikutnya(subject, history, sil, class_level=class_level)

    akurasi_info = _baca_akurasi(subject)
    akurasi_pct = akurasi_info.get("akurasi")
    if akurasi_pct is not None and "confidence" in hasil and akurasi_pct < 50.0:
        hasil["confidence"] = max(0.0, hasil["confidence"] - 10.0)

    return hasil


def _parse_output_llm(
    raw_output: str, silabus: List[Dict[str, Any]], subject: str, jumlah_riwayat: int
) -> Dict[str, Any]:
    """Parse dan normalisasi output JSON LLM; lempar exception bila tidak valid."""
    clean_text = raw_output.strip()
    if "```" in clean_text:
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", clean_text, re.DOTALL)
        clean_text = match.group(1) if match else clean_text.replace("```json", "").replace("```", "").strip()

    hasil = json.loads(clean_text)
    if not isinstance(hasil, dict):
        raise ValueError("Respons LLM bukan dictionary.")

    predicted_topic = str(hasil.get("predicted_topic", "")).strip()
    if not predicted_topic:
        raise ValueError("Respons LLM tidak memiliki predicted_topic.")

    confidence = float(hasil.get("confidence", 0.0))
    if 0.0 <= confidence <= 1.0:
        confidence = round(confidence * 100, 2)
    else:
        confidence = round(min(max(confidence, 0.0), 100.0), 2)

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
        "reason": reason or f"Prediksi berdasarkan riwayat {jumlah_riwayat} tugas {subject}.",
        "prerequisites": prereqs_str or f"Konsep dasar {subject}",
        "preparation_suggestion": prep or f"Pelajari bab {predicted_topic} sebelum kelas dimulai.",
        "syllabus_reference": "available" if silabus else "unavailable",
        "source": "ai",
    }


def predict_material(
    subject: str,
    difficulty: Optional[int] = None,
    task_history: Optional[List[Dict[str, Any]]] = None,
    class_level: str = "",
    curriculum: str = "",
    timeout: Optional[float] = None,
    call_fn: Any = None,
    jenjang: str = "",
) -> Dict[str, Any]:
    """Fungsi utama prediksi materi: retrieval silabus berfilter jenjang, LLM, dan fallback.

    `jenjang` kosong pada kelas 10-12 diperlakukan sebagai SMA (lihat `resolve_jenjang`),
    sehingga payload lama tidak mencampur baris SMA dan SMK.
    """
    raw_history = task_history or []
    data_riwayat = normalisasi_riwayat(raw_history)
    jenjang_efektif = resolve_jenjang(class_level, jenjang)
    silabus = baca_silabus(
        subject, class_level=class_level, curriculum=curriculum, jenjang=jenjang_efektif
    )

    call = call_fn
    if call is None:
        if not get_api_key():
            log.info("LLM_API_KEY tidak ditemukan, beralih ke fallback deterministik.")
            return fallback_prediction(
                subject, difficulty, raw_history, silabus,
                class_level=class_level, jenjang=jenjang_efektif,
            )
        call = call_llm

    effective_timeout = get_timeout() if timeout is None else timeout
    prompt = build_prediction_prompt(
        subject=subject,
        difficulty=difficulty,
        data_riwayat=data_riwayat,
        silabus=silabus,
        class_level=class_level,
        curriculum=curriculum,
        jenjang=jenjang_efektif,
        akurasi_info=_baca_akurasi(subject),
    )

    try:
        raw_output = _call_with_timeout(call, prompt, effective_timeout)
    except Exception as e:
        log.warning("Panggilan LLM prediksi materi gagal: %s. Menggunakan fallback.", e)
        return fallback_prediction(
            subject, difficulty, raw_history, silabus,
            class_level=class_level, jenjang=jenjang_efektif,
        )

    try:
        return _parse_output_llm(raw_output, silabus, subject, len(data_riwayat))
    except Exception as e:
        log.warning("Gagal mem-parsing output LLM (%s): %s. Menggunakan fallback.", e, str(raw_output)[:120])
        return fallback_prediction(
            subject, difficulty, raw_history, silabus,
            class_level=class_level, jenjang=jenjang_efektif,
        )
