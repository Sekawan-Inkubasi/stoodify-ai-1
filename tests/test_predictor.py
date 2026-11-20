import json
import pytest

from predictor import (
    baca_silabus,
    build_prediction_prompt,
    cari_topik_berikutnya,
    fallback_prediction,
    normalize_class_level,
    normalisasi_riwayat,
    predict_material,
)


def test_baca_silabus_matematika():
    silabus = baca_silabus("Matematika")
    assert len(silabus) > 0
    assert silabus[0]["mata_pelajaran"] == "Matematika"
    assert any("Komposisi Fungsi" in s["materi"] for s in silabus)


def test_baca_silabus_mapel_tidak_ada():
    silabus = baca_silabus("Fisika Kuantum Fiksi")
    assert silabus == []


def test_normalisasi_kelas():
    assert normalize_class_level("10") == ("10", "E")
    assert normalize_class_level("X") == ("10", "E")
    assert normalize_class_level("Kelas 11") == ("11", "F")
    assert normalize_class_level("XI") == ("11", "F")
    assert normalize_class_level("Fase F")[1] == "F"


def test_baca_silabus_differensiasi_kelas():
    silabus_10 = baca_silabus("Matematika", class_level="X")
    silabus_11 = baca_silabus("Matematika", class_level="XI")
    assert len(silabus_10) > 0
    assert len(silabus_11) > 0
    # Topik kelas 10 tidak sama dengan topik kelas 11
    topik_10 = [s["nama_topik"] for s in silabus_10]
    topik_11 = [s["nama_topik"] for s in silabus_11]
    assert "Eksponen dan Logaritma" in topik_10
    assert "Komposisi Fungsi dan Fungsi Invers" in topik_11
    assert "Eksponen dan Logaritma" not in topik_11


def test_prediksi_sekuensial_no_urut_plus_satu():
    # Siswa kelas 10 selesai Bab 1 (Eksponen dan Logaritma) -> Bab 2 (Barisan dan Deret)
    silabus_10 = baca_silabus("Matematika", class_level="10")
    pred = fallback_prediction(
        subject="Matematika",
        difficulty=3,
        task_history=[{"title": "Latihan 1", "material_name": "Eksponen dan Logaritma"}],
        silabus=silabus_10,
        class_level="10",
    )
    assert pred["source"] == "fallback"
    assert pred["predicted_topic"] == "Barisan dan Deret"
    assert pred["syllabus_reference"] == "available"
    assert "Eksponen dan Logaritma" in pred["prerequisites"]
    assert "barisan aritmetika" in pred["preparation_suggestion"].lower()


def test_prediksi_vokasi_smk_pplg():
    # Siswa SMK PPLG selesai Pemrograman Web Frontend -> Pemrograman Web Backend
    silabus_pplg = baca_silabus("Pengembangan Perangkat Lunak dan Gim (PPLG)", class_level="11")
    assert len(silabus_pplg) > 0
    pred = fallback_prediction(
        subject="Pengembangan Perangkat Lunak dan Gim (PPLG)",
        difficulty=4,
        task_history=[{"title": "Projek Web", "material_name": "Pemrograman Web Frontend"}],
        silabus=silabus_pplg,
        class_level="11",
    )
    assert pred["source"] == "fallback"
    assert "Backend" in pred["predicted_topic"]
    assert pred["syllabus_reference"] == "available"


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
        silabus=[{"materi": "Komposisi Fungsi", "nama_topik": "Komposisi Fungsi", "urutan_materi": "1", "no_urut": 1, "bab_unit": "Bab 1", "elemen_fokus": "Aljabar", "sub_materi": "Fungsi", "kelas": "11"}],
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
        subject="Kimia Industri Khusus",
        difficulty=4,
        task_history=[{"title": "Laporan Titrasi Asam Basa"}],
        silabus=[],
    )
    assert pred["source"] == "fallback"
    assert "Titrasi Asam Basa" in pred["predicted_topic"]
    assert pred["syllabus_reference"] == "unavailable"


def test_fallback_prediction_riwayat_kosong():
    pred = fallback_prediction(subject="Biologi Antariksa", task_history=[])
    assert pred["source"] == "fallback"
    assert "Materi Pengantar Biologi Antariksa" in pred["predicted_topic"]


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
