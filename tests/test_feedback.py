import json
import pytest
from feedback import (
    analisis_feedback,
    analisis_feedback_per_mapel,
    baca_akurasi_per_mapel,
    simpan_feedback,
    FEEDBACK_HISTORY_PATH,
)


# ---------------------------------------------------------------------------
# Test lama (batch analysis, tidak menyimpan ke disk)
# ---------------------------------------------------------------------------

def test_analisis_feedback():
    data = [
        {"subject": "Matematika", "user_feedback": "accurate"},
        {"subject": "Matematika", "user_feedback": "inaccurate"},
        {"subject": "Bahasa Indonesia", "user_feedback": "accurate"},
    ]
    hasil = analisis_feedback(data)
    assert hasil["total_feedback"] == 3
    assert hasil["prediksi_benar"] == 2
    assert hasil["prediksi_salah"] == 1
    assert hasil["akurasi_feedback"] == 66.67


def test_analisis_feedback_kosong():
    hasil = analisis_feedback([])
    assert hasil["total_feedback"] == 0
    assert hasil["akurasi_feedback"] == 0.0


def test_analisis_feedback_per_mapel():
    data = [
        {"subject": "Matematika", "user_feedback": "accurate"},
        {"subject": "Matematika", "user_feedback": "inaccurate"},
        {"subject": "Bahasa Indonesia", "user_feedback": "accurate"},
        {"subject": "Bahasa Indonesia", "user_feedback": "accurate"},
    ]
    hasil = analisis_feedback_per_mapel(data)
    assert "Matematika" in hasil
    assert "Bahasa Indonesia" in hasil
    assert hasil["Matematika"]["akurasi_feedback"] == 50.0
    assert hasil["Bahasa Indonesia"]["akurasi_feedback"] == 100.0


# ---------------------------------------------------------------------------
# Test baru: simpan_feedback & baca_akurasi_per_mapel
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def bersihkan_file_riwayat(tmp_path, monkeypatch):
    """Redirect FEEDBACK_HISTORY_PATH ke file sementara agar test tidak mengotori DATA/ asli."""
    import feedback as fb_module
    tmp_file = tmp_path / "feedback_history.json"
    monkeypatch.setattr(fb_module, "FEEDBACK_HISTORY_PATH", tmp_file)
    yield
    # cleanup otomatis oleh tmp_path


def test_simpan_feedback_menyimpan_ke_disk(tmp_path, monkeypatch):
    import feedback as fb_module
    tmp_file = tmp_path / "feedback_history.json"
    monkeypatch.setattr(fb_module, "FEEDBACK_HISTORY_PATH", tmp_file)

    data = [
        {"subject": "Fisika", "user_feedback": "accurate"},
        {"subject": "Fisika", "user_feedback": "accurate"},
        {"subject": "Fisika", "user_feedback": "inaccurate"},
    ]
    hasil = simpan_feedback(data)
    assert hasil["disimpan"] == 3
    assert hasil["dilewati"] == 0

    # Verifikasi file benar-benar ditulis
    assert tmp_file.exists()
    riwayat = json.loads(tmp_file.read_text(encoding="utf-8"))
    assert riwayat["Fisika"]["benar"] == 2
    assert riwayat["Fisika"]["salah"] == 1


def test_simpan_feedback_akumulasi(tmp_path, monkeypatch):
    """Memanggil simpan_feedback dua kali harus mengakumulasikan, bukan menimpa."""
    import feedback as fb_module
    tmp_file = tmp_path / "feedback_history.json"
    monkeypatch.setattr(fb_module, "FEEDBACK_HISTORY_PATH", tmp_file)

    simpan_feedback([{"subject": "Kimia", "user_feedback": "correct"}])
    simpan_feedback([{"subject": "Kimia", "user_feedback": "correct"}])
    simpan_feedback([{"subject": "Kimia", "user_feedback": "incorrect"}])

    riwayat = json.loads(tmp_file.read_text(encoding="utf-8"))
    assert riwayat["Kimia"]["benar"] == 2
    assert riwayat["Kimia"]["salah"] == 1


def test_simpan_feedback_label_indonesia(tmp_path, monkeypatch):
    """Label Bahasa Indonesia (benar/salah) juga harus diterima."""
    import feedback as fb_module
    tmp_file = tmp_path / "feedback_history.json"
    monkeypatch.setattr(fb_module, "FEEDBACK_HISTORY_PATH", tmp_file)

    simpan_feedback([
        {"subject": "Biologi", "user_feedback": "benar"},
        {"subject": "Biologi", "user_feedback": "salah"},
    ])
    riwayat = json.loads(tmp_file.read_text(encoding="utf-8"))
    assert riwayat["Biologi"]["benar"] == 1
    assert riwayat["Biologi"]["salah"] == 1


def test_simpan_feedback_tanpa_subject_dilewati(tmp_path, monkeypatch):
    """Item tanpa subject atau feedback valid harus dicatat sebagai dilewati."""
    import feedback as fb_module
    monkeypatch.setattr(fb_module, "FEEDBACK_HISTORY_PATH", tmp_path / "fb.json")

    hasil = simpan_feedback([
        {"user_feedback": "accurate"},          # tidak ada subject
        {"subject": "Geografi", "user_feedback": "unknown_label"},  # label tidak dikenal
    ])
    assert hasil["disimpan"] == 0
    assert hasil["dilewati"] == 2


def test_baca_akurasi_per_mapel_semua(tmp_path, monkeypatch):
    """baca_akurasi_per_mapel() tanpa subject mengembalikan semua mapel."""
    import feedback as fb_module
    tmp_file = tmp_path / "fb.json"
    monkeypatch.setattr(fb_module, "FEEDBACK_HISTORY_PATH", tmp_file)

    simpan_feedback([
        {"subject": "Matematika", "user_feedback": "accurate"},
        {"subject": "Matematika", "user_feedback": "accurate"},
        {"subject": "Fisika", "user_feedback": "inaccurate"},
    ])

    hasil = baca_akurasi_per_mapel()
    assert "Matematika" in hasil
    assert "Fisika" in hasil
    assert hasil["Matematika"]["akurasi"] == 100.0
    assert hasil["Fisika"]["akurasi"] == 0.0


def test_baca_akurasi_per_mapel_satu_subject(tmp_path, monkeypatch):
    """baca_akurasi_per_mapel(subject=...) hanya mengembalikan data satu mapel."""
    import feedback as fb_module
    tmp_file = tmp_path / "fb.json"
    monkeypatch.setattr(fb_module, "FEEDBACK_HISTORY_PATH", tmp_file)

    simpan_feedback([
        {"subject": "Sejarah", "user_feedback": "accurate"},
        {"subject": "Sejarah", "user_feedback": "accurate"},
        {"subject": "Sejarah", "user_feedback": "inaccurate"},
    ])

    hasil = baca_akurasi_per_mapel("Sejarah")
    assert hasil["total"] == 3
    assert hasil["benar"] == 2
    assert hasil["salah"] == 1
    assert abs(hasil["akurasi"] - 66.67) < 0.01


def test_baca_akurasi_mapel_belum_ada(tmp_path, monkeypatch):
    """Mapel yang belum punya feedback harus mengembalikan akurasi None."""
    import feedback as fb_module
    monkeypatch.setattr(fb_module, "FEEDBACK_HISTORY_PATH", tmp_path / "fb.json")

    hasil = baca_akurasi_per_mapel("Ekonomi")
    assert hasil["total"] == 0
    assert hasil["akurasi"] is None

