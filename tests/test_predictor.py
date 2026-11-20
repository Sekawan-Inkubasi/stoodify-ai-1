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
    resolve_jenjang,
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


def test_mapel_vokasi_smk_tidak_ada_di_dataset():
    assert baca_silabus(
        "Pengembangan Perangkat Lunak dan Gim (PPLG)", class_level="11", jenjang="SMK"
    ) == []
    assert baca_silabus(
        "Teknik Jaringan Komputer dan Telekomunikasi (TJKT)", class_level="11", jenjang="SMK"
    ) == []


def test_mapel_vokasi_smk_diarahkan_ke_llm():
    mock_response = json.dumps({
        "predicted_topic": "Pemrograman Web Backend",
        "confidence": 0.6,
        "reason": "Melanjutkan proyek web dari tugas frontend sebelumnya.",
        "prerequisites": "Dasar pemrograman web dan basis data",
        "preparation_suggestion": "Pelajari dasar API dan routing backend.",
    })
    prompt_diterima = {}

    def fake_call(prompt):
        prompt_diterima["prompt"] = prompt
        return mock_response

    result = predict_material(
        subject="Pengembangan Perangkat Lunak dan Gim (PPLG)",
        difficulty=4,
        task_history=[{"title": "Projek Web", "material_name": "Pemrograman Web Frontend"}],
        class_level="11",
        jenjang="SMK",
        call_fn=fake_call,
    )

    assert result["source"] == "ai"
    assert result["predicted_topic"] == "Pemrograman Web Backend"
    assert result["syllabus_reference"] == "unavailable"
    assert "TIDAK TERSEDIA" in prompt_diterima["prompt"]
    assert "JANGAN mengarang nomor bab" in prompt_diterima["prompt"]
    assert "No. Urut sekarang + 1" not in prompt_diterima["prompt"]


def test_mapel_vokasi_smk_llm_gagal_fallback_aman():
    def gagal(prompt):
        raise TimeoutError("provider timeout")

    result = predict_material(
        subject="Teknik Jaringan Komputer dan Telekomunikasi (TJKT)",
        difficulty=4,
        task_history=[{"title": "Konfigurasi Router", "material_name": "Routing Statis"}],
        class_level="11",
        jenjang="SMK",
        call_fn=gagal,
    )

    assert result["source"] == "fallback"
    assert result["syllabus_reference"] == "unavailable"
    assert "Routing Statis" in result["predicted_topic"]
    assert result["confidence"] <= 50


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


def test_baca_silabus_filter_jenjang_per_kelas():
    for kelas in ("10", "11", "12"):
        sma = baca_silabus("Matematika", class_level=kelas, jenjang="SMA")
        smk = baca_silabus("Matematika", class_level=kelas, jenjang="SMK")
        assert sma, f"silabus SMA kelas {kelas} kosong"
        assert smk, f"silabus SMK kelas {kelas} kosong"
        assert {s["jenjang"] for s in sma} == {"SMA"}
        assert {s["jenjang"] for s in smk} == {"SMK"}
        assert {s["id"] for s in sma}.isdisjoint({s["id"] for s in smk})
        assert [s["nama_topik"] for s in sma] != [s["nama_topik"] for s in smk]


def test_baca_silabus_mapel_umum_smk_hanya_baris_smk():
    silabus = baca_silabus("Bahasa Indonesia", class_level="11", jenjang="SMK")
    assert silabus
    assert {s["jenjang"] for s in silabus} == {"SMK"}
    silabus_sma = baca_silabus("Bahasa Indonesia", class_level="11", jenjang="SMA")
    assert {s["jenjang"] for s in silabus_sma} == {"SMA"}
    assert len(silabus) != len(silabus_sma)


def test_baca_silabus_alias_mapel_umum_smk():
    assert baca_silabus("b. inggris", class_level="10", jenjang="SMK")
    assert baca_silabus("pai", class_level="10", jenjang="SMK")
    assert {s["jenjang"] for s in baca_silabus("b. inggris", class_level="10", jenjang="SMK")} == {"SMK"}


def test_baca_silabus_kelas_10_12_tanpa_jenjang_default_sma():
    tanpa_jenjang = baca_silabus("Matematika", class_level="11")
    eksplisit_sma = baca_silabus("Matematika", class_level="11", jenjang="SMA")
    assert [s["id"] for s in tanpa_jenjang] == [s["id"] for s in eksplisit_sma]
    assert {s["jenjang"] for s in tanpa_jenjang} == {"SMA"}


def test_resolve_jenjang_default_dan_inferensi():
    assert resolve_jenjang("11") == "SMA"
    assert resolve_jenjang("XII") == "SMA"
    assert resolve_jenjang("11", "SMK") == "SMK"
    assert resolve_jenjang("8") == "SMP"
    assert resolve_jenjang("4") == "SD"
    assert resolve_jenjang("") == "SMA"


def test_predict_material_meneruskan_jenjang_ke_retrieval():
    sma = predict_material(subject="Matematika", class_level="11", jenjang="SMA")
    smk = predict_material(subject="Matematika", class_level="11", jenjang="SMK")
    assert sma["syllabus_reference"] == "available"
    assert smk["syllabus_reference"] == "available"
    assert sma["predicted_topic"] != smk["predicted_topic"]


def test_jenjang_sd_smp_tidak_punya_silabus_runtime():
    assert baca_silabus("Matematika", class_level="4") == []
    assert baca_silabus("Matematika", class_level="VIII") == []
    assert baca_silabus("Matematika", class_level="IX", jenjang="SMP") == []


def test_siswa_smp_dapat_prediksi_tanpa_rujukan_silabus():
    result = predict_material(
        subject="Matematika",
        class_level="VIII",
        task_history=[{"material_name": "Persamaan Linear Dua Variabel"}],
    )
    assert result["syllabus_reference"] == "unavailable"
    assert "Persamaan Linear Dua Variabel" in result["predicted_topic"]


def test_tanpa_kelas_dan_jenjang_tidak_mencampur_sma_smk():
    silabus = baca_silabus("Matematika")
    assert silabus
    assert {s["jenjang"] for s in silabus} == {"SMA"}
