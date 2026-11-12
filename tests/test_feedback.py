import pytest
from feedback import analisis_feedback, analisis_feedback_per_mapel


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
