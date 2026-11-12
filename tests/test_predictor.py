import json
import pytest

from predictor import (
    baca_silabus,
    build_prediction_prompt,
    fallback_prediction,
    normalisasi_riwayat,
    predict_material,
)


def test_baca_silabus_matematika():
    silabus = baca_silabus("Matematika")
    assert len(silabus) > 0
    assert silabus[0]["mata_pelajaran"] == "Matematika"
    assert "Komposisi Fungsi" in [s["materi"] for s in silabus]


def test_baca_silabus_mapel_tidak_ada():
    silabus = baca_silabus("Fisika Kuantum")
    assert silabus == []


def test_normalisasi_riwayat():
    raw = [
        {"title": "PR Fungsi", "material_name": "Komposisi Fungsi", "deadline": "2026-11-01"},
        {"task_name": "Latihan Soal", "topic": "Invers Fungsi", "task_date": "2026-11-05"},
    ]
    norm = normalisasi_riwayat(raw)
    assert len(norm) == 2
    assert norm[0]["nama_tugas"] == "PR Fungsi"
    assert norm[0]["materi"] == "Komposisi Fungsi"
    assert norm[1]["nama_tugas"] == "Latihan Soal"
    assert norm[1]["materi"] == "Invers Fungsi"


def test_build_prediction_prompt():
    prompt = build_prediction_prompt(
        subject="Matematika",
        difficulty=4,
        data_riwayat=[{"nama_tugas": "Tugas 1", "materi": "Fungsi", "tanggal": "2026-10-01"}],
        silabus=[{"materi": "Komposisi Fungsi", "urutan_materi": "1"}],
    )
    assert "MATA PELAJARAN:" in prompt
    assert "Matematika" in prompt
    assert "Komposisi Fungsi" in prompt


def test_fallback_prediction_dengan_silabus():
    silabus = baca_silabus("Matematika")
    pred = fallback_prediction(
        subject="Matematika",
        difficulty=3,
        task_history=[{"title": "PR 1", "material_name": "Komposisi Fungsi"}],
        silabus=silabus,
    )
    assert pred["source"] == "fallback"
    assert pred["predicted_topic"] != ""
    assert pred["confidence"] >= 50
    assert pred["syllabus_reference"] == "available"


def test_fallback_prediction_tanpa_silabus():
    pred = fallback_prediction(
        subject="Kimia Industri",
        difficulty=4,
        task_history=[{"title": "Laporan Titrasi Asam Basa"}],
        silabus=[],
    )
    assert pred["source"] == "fallback"
    assert "Titrasi Asam Basa" in pred["predicted_topic"]
    assert pred["syllabus_reference"] == "unavailable"


def test_fallback_prediction_riwayat_kosong():
    pred = fallback_prediction(subject="Biologi", task_history=[])
    assert pred["source"] == "fallback"
    assert "Materi Pengantar Biologi" in pred["predicted_topic"]


def test_predict_material_dengan_mock_llm():
    mock_response = json.dumps({
        "predicted_topic": "Transformasi Fungsi",
        "confidence": 0.88,
        "reason": "Siswa sudah menguasai komposisi dan invers fungsi.",
        "prerequisites": ["Komposisi Fungsi", "Invers Fungsi"],
        "preparation_suggestion": "Pelajari translasi grafik fungsi kuadrat.",
        "syllabus_reference": "available",
    })

    result = predict_material(
        subject="Matematika",
        difficulty=4,
        task_history=[{"title": "PR 1", "material_name": "Invers Fungsi"}],
        call_fn=lambda prompt: mock_response,
    )

    assert result["source"] == "ai"
    assert result["predicted_topic"] == "Transformasi Fungsi"
    assert result["confidence"] == 88.0
    assert "Komposisi Fungsi, Invers Fungsi" in result["prerequisites"]
    assert "translasi grafik" in result["preparation_suggestion"]


def test_predict_material_llm_json_rusak_pindah_fallback():
    result = predict_material(
        subject="Matematika",
        difficulty=4,
        task_history=[{"title": "Tugas 1", "material_name": "Fungsi"}],
        call_fn=lambda prompt: "Bukan JSON sama sekali",
    )
    assert result["source"] == "fallback"
    assert result["predicted_topic"] != ""
