"""Modul analisis dan evaluasi feedback akurasi prediksi materi Stoodify."""
from typing import Any, Dict, List


def analisis_feedback(data_feedback: List[Dict[str, Any]]) -> Dict[str, Any]:
    benar = 0
    salah = 0

    for item in data_feedback:
        feedback = str(
            item.get("user_feedback") or item.get("feedback") or ""
        ).strip().lower()

        if feedback in ("accurate", "correct"):
            benar += 1
        elif feedback in ("inaccurate", "incorrect"):
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
    hasil_per_mapel: Dict[str, List[Dict[str, Any]]] = {}

    for item in data_feedback:
        subject = item.get("subject") or item.get("mata_pelajaran") or "Tidak diketahui"

        if isinstance(subject, dict):
            subject = subject.get("name", "Tidak diketahui")

        subject = str(subject)

        if subject not in hasil_per_mapel:
            hasil_per_mapel[subject] = []

        hasil_per_mapel[subject].append(item)

    hasil: Dict[str, Dict[str, Any]] = {}

    for subject, feedback in hasil_per_mapel.items():
        hasil[subject] = analisis_feedback(feedback)

    return hasil
