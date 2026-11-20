"""Kontrak dataset runtime silabus: header, cakupan jenjang, dan batas kejuruan.

Angka di sini adalah hasil audit `docs/to-do-dataset.md` terhadap workbook
`Kurikulum_Merdeka_Gabungan_Sempurna.xlsx` (sheet `Materi`, 910 baris data).
Runtime hanya memuat SMA dan mapel umum SMK: 337 + 103 = 440 baris.
"""
import csv
from collections import Counter
from pathlib import Path

import pytest

HEADER = [
    "ID", "Jenjang", "Kelas", "Fase", "Mata Pelajaran", "Status Mapel",
    "Jalur / Disiplin", "No. Urut", "Bab / Unit", "Nama Topik",
    "Elemen / Fokus", "Sub-Materi", "Relevansi Jurusan/Karir",
]

CSV_PATH = Path(__file__).resolve().parent.parent / "DATA" / "kurikulum_merdeka.csv"

JUMLAH_PER_JENJANG = {"SMA": 337, "SMK": 103}

MAPEL_UMUM_SMK = {
    "Pendidikan Agama dan Budi Pekerti",
    "Pendidikan Pancasila",
    "Bahasa Indonesia",
    "Matematika",
    "Bahasa Inggris",
    "Sejarah",
    "Seni dan Budaya",
    "Pendidikan Jasmani Olahraga dan Kesehatan (PJOK)",
    "Informatika",
    "Ilmu Pengetahuan Alam dan Sosial (IPAS)",
}

MAPEL_KEJURUAN_SMK = {
    "Pengembangan Perangkat Lunak dan Gim (PPLG)",
    "Teknik Jaringan Komputer dan Telekomunikasi (TJKT)",
    "Projek Kreatif dan Kewirausahaan",
    "Praktik Kerja Lapangan (PKL)",
}


@pytest.fixture(scope="module")
def rows():
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def test_dataset_file_ada():
    assert CSV_PATH.exists(), f"dataset runtime tidak ditemukan: {CSV_PATH}"


def test_header_sesuai_skema_parser(rows):
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        assert next(csv.reader(f)) == HEADER


def test_encoding_utf8_bom(rows):
    assert CSV_PATH.read_bytes().startswith(b"\xef\xbb\xbf")


def test_jumlah_baris_runtime(rows):
    assert len(rows) == 440


def test_distribusi_jenjang(rows):
    assert dict(Counter(r["Jenjang"] for r in rows)) == JUMLAH_PER_JENJANG


def test_hanya_jenjang_sma_dan_smk(rows):
    assert {r["Jenjang"] for r in rows} == {"SMA", "SMK"}
    assert not [r for r in rows if r["Jenjang"] in ("SD", "SMP")]


def test_kelas_hanya_angka_10_sampai_12(rows):
    assert {r["Kelas"] for r in rows} == {"10", "11", "12"}


def test_tidak_ada_mapel_kejuruan_smk(rows):
    mapel_smk = {r["Mata Pelajaran"] for r in rows if r["Jenjang"] == "SMK"}
    assert mapel_smk == MAPEL_UMUM_SMK
    assert mapel_smk.isdisjoint(MAPEL_KEJURUAN_SMK)


def test_mapel_umum_smk_hanya_punya_baris_smk(rows):
    umum_di_smk = {
        r["Mata Pelajaran"] for r in rows if r["Jenjang"] == "SMK"
    }
    for mapel in umum_di_smk:
        jenjang_mapel = {r["Jenjang"] for r in rows if r["Mata Pelajaran"] == mapel}
        assert "SMK" in jenjang_mapel


def test_relevansi_jurusan_smk_terisi_dari_workbook(rows):
    relevansi_smk = [r for r in rows if r["Jenjang"] == "SMK" and r["Relevansi Jurusan/Karir"].strip()]
    assert relevansi_smk, "kolom Relevansi Jurusan/Karir SMK kosong seluruhnya"
    assert len(relevansi_smk) == 103


def test_tidak_ada_baris_duplikat(rows):
    kunci = [
        (r["Jenjang"], r["Kelas"], r["Mata Pelajaran"], r["Jalur / Disiplin"], r["No. Urut"])
        for r in rows
    ]
    assert len(kunci) == len(set(kunci))


def test_no_urut_berurutan_per_mapel_jenjang(rows):
    grup = {}
    for r in rows:
        key = (r["Jenjang"], r["Mata Pelajaran"], r["Jalur / Disiplin"])
        grup.setdefault(key, set()).add(int(r["No. Urut"]))
    for key, nomor in grup.items():
        assert nomor == set(range(1, len(nomor) + 1)), f"no urut tidak berurutan: {key}"


def test_semua_baris_punya_topik_dan_mapel(rows):
    for r in rows:
        assert r["Nama Topik"].strip(), f"topik kosong pada ID {r['ID']}"
        assert r["Mata Pelajaran"].strip(), f"mapel kosong pada ID {r['ID']}"


def test_fase_konsisten_dengan_kelas(rows):
    fase_harapan = {"10": {"E"}, "11": {"F"}, "12": {"F"}}
    for r in rows:
        assert r["Fase"] in fase_harapan[r["Kelas"]], f"fase salah pada ID {r['ID']}"
