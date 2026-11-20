"""Hasilkan ulang dataset runtime silabus dari workbook sumber Kurikulum Merdeka.

Sumber resmi: ../../Kurikulum_Merdeka_Gabungan_Sempurna.xlsx (sheet `Materi`).
Keluaran      : DATA/kurikulum_merdeka.csv (UTF-8 BOM, header sesuai `_normalize_row()`).

Cakupan runtime yang disepakati (`docs/to-do-dataset.md`):
- Seluruh baris SMA dipertahankan apa adanya.
- Baris SMK dipertahankan hanya untuk mata pelajaran umum.
- Baris SD dan SMP dibuang; Stoodify memprediksi siswa SMA/SMK.
- Mata pelajaran kejuruan SMK dibuang dari runtime karena hanya mewakili sebagian
  program keahlian; prediksinya diserahkan ke LLM.

Daftar mapel umum SMK TIDAK diketik manual: diturunkan dari sheet `Daftar Mapel`
pada kolom `Keterangan` yang memuat frasa "Mata Pelajaran Umum" untuk jenjang SMK.
Mapel SMK lain (Dasar Program Keahlian, Konsentrasi Keahlian, PKK, PKL, PPLG, TJKT)
dianggap kejuruan dan tidak masuk runtime.

Jalankan:
    venv/bin/python scripts/regen_dataset.py [--check]

`--check` hanya membandingkan tanpa menulis file.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from openpyxl import load_workbook

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "DATA"
CSV_PATH = DATA_DIR / "kurikulum_merdeka.csv"
XLSX_MIRROR_PATH = DATA_DIR / "kurikulum_merdeka.xlsx"
DEFAULT_SOURCE = BASE_DIR.parent.parent / "Kurikulum_Merdeka_Gabungan_Sempurna.xlsx"

MATERI_SHEET = "Materi"
MAPEL_SHEET = "Daftar Mapel"

EXPECTED_HEADER: Tuple[str, ...] = (
    "ID",
    "Jenjang",
    "Kelas",
    "Fase",
    "Mata Pelajaran",
    "Status Mapel",
    "Jalur / Disiplin",
    "No. Urut",
    "Bab / Unit",
    "Nama Topik",
    "Elemen / Fokus",
    "Sub-Materi",
    "Relevansi Jurusan/Karir",
)


def _cell(value: Any) -> str:
    """Ubah nilai sel menjadi string CSV yang stabil (None -> string kosong)."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def baca_materi(source: Path) -> Tuple[List[str], List[Tuple[str, ...]]]:
    """Baca sheet `Materi` dan kembalikan (header, baris data tidak kosong)."""
    wb = load_workbook(source, data_only=True, read_only=True)
    try:
        if MATERI_SHEET not in wb.sheetnames:
            raise SystemExit(f"Sheet '{MATERI_SHEET}' tidak ditemukan di {source}")
        rows = list(wb[MATERI_SHEET].iter_rows(values_only=True))
    finally:
        wb.close()

    if not rows:
        raise SystemExit(f"Sheet '{MATERI_SHEET}' kosong di {source}")

    header = tuple(_cell(c) for c in rows[0])
    if header != EXPECTED_HEADER:
        raise SystemExit(
            "Header workbook tidak sesuai skema runtime.\n"
            f"  diharapkan: {EXPECTED_HEADER}\n"
            f"  ditemukan : {header}"
        )

    data = [tuple(_cell(c) for c in row) for row in rows[1:]]
    data = [row for row in data if any(v for v in row)]
    return list(header), data


def baca_mapel_umum_smk(source: Path) -> Set[str]:
    """Turunkan daftar mata pelajaran umum SMK dari sheet `Daftar Mapel`.

    Penanda resmi adalah kolom `Keterangan` yang memuat frasa
    "Mata Pelajaran Umum". Mapel SMK tanpa penanda itu diperlakukan vokasi.
    """
    wb = load_workbook(source, data_only=True, read_only=True)
    try:
        if MAPEL_SHEET not in wb.sheetnames:
            raise SystemExit(f"Sheet '{MAPEL_SHEET}' tidak ditemukan di {source}")
        rows = list(wb[MAPEL_SHEET].iter_rows(values_only=True))
    finally:
        wb.close()

    header = [_cell(c) for c in rows[0]]
    try:
        idx_jenjang = header.index("Jenjang")
        idx_mapel = header.index("Mata Pelajaran")
        idx_ket = header.index("Keterangan")
    except ValueError:
        raise SystemExit(f"Kolom wajib tidak lengkap pada sheet '{MAPEL_SHEET}': {header}")

    umum: Set[str] = set()
    for row in rows[1:]:
        if len(row) <= max(idx_jenjang, idx_mapel, idx_ket):
            continue
        if _cell(row[idx_jenjang]).upper() != "SMK":
            continue
        if "mata pelajaran umum" in _cell(row[idx_ket]).lower():
            nama = _cell(row[idx_mapel])
            if nama:
                umum.add(nama)
    return umum


def saring_runtime(
    header: List[str], data: List[Tuple[str, ...]], umum_smk: Set[str]
) -> Tuple[List[Tuple[str, ...]], List[Tuple[str, ...]]]:
    """Pisahkan baris runtime (dipertahankan) dan baris di luar cakupan (dibuang)."""
    i_jenjang = header.index("Jenjang")
    i_mapel = header.index("Mata Pelajaran")

    runtime: List[Tuple[str, ...]] = []
    dibuang: List[Tuple[str, ...]] = []
    for row in data:
        jenjang = row[i_jenjang].upper()
        if jenjang == "SMA":
            runtime.append(row)
        elif jenjang == "SMK" and row[i_mapel] in umum_smk:
            runtime.append(row)
        else:
            dibuang.append(row)
    return runtime, dibuang


def tulis_csv(header: List[str], data: List[Tuple[str, ...]], target: Path) -> None:
    """Tulis CSV runtime dengan encoding UTF-8 BOM dan newline LF."""
    tmp = target.with_suffix(target.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(data)
    tmp.replace(target)


def hitung(data: List[Tuple[str, ...]], idx: int) -> Dict[str, int]:
    """Hitung frekuensi kemunculan nilai pada satu kolom."""
    hasil: Dict[str, int] = {}
    for row in data:
        hasil[row[idx]] = hasil.get(row[idx], 0) + 1
    return dict(sorted(hasil.items()))


def ringkas(label: str, header: List[str], data: List[Tuple[str, ...]]) -> None:
    """Cetak ringkasan audit untuk satu himpunan baris."""
    print(f"[{label}] baris data: {len(data)}")
    print(f"  jenjang     : {hitung(data, header.index('Jenjang'))}")
    print(f"  status mapel: {hitung(data, header.index('Status Mapel'))}")
    smk = [r for r in data if r[header.index("Jenjang")].upper() == "SMK"]
    if smk:
        print(f"  mapel SMK   : {hitung(smk, header.index('Mata Pelajaran'))}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE,
                        help=f"Workbook sumber (default: {DEFAULT_SOURCE})")
    parser.add_argument("--check", action="store_true",
                        help="Hanya bandingkan dengan CSV saat ini, tanpa menulis file")
    parser.add_argument("--no-xlsx-mirror", action="store_true",
                        help="Jangan sinkronkan salinan DATA/kurikulum_merdeka.xlsx")
    args = parser.parse_args()

    source: Path = args.source.resolve()
    if not source.exists():
        raise SystemExit(f"Workbook sumber tidak ditemukan: {source}")

    print(f"sumber: {source}")
    header, materi = baca_materi(source)
    umum_smk = baca_mapel_umum_smk(source)
    print(f"mapel umum SMK (dari sheet '{MAPEL_SHEET}'): {sorted(umum_smk)}")

    runtime, dibuang = saring_runtime(header, materi, umum_smk)
    ringkas("workbook Materi", header, materi)
    ringkas("di luar cakupan (SD/SMP/vokasi)", header, dibuang)
    ringkas("runtime hasil", header, runtime)

    if args.check:
        now = CSV_PATH.read_text(encoding="utf-8-sig").splitlines()
        akan = [",".join(header)] + [",".join(r) for r in runtime]
        if len(now) - 1 != len(runtime):
            print(f"BEDA: CSV saat ini {len(now) - 1} baris, hasil {len(runtime)} baris")
            return 1
        print("CSV saat ini sudah sesuai hasil regenerasi.")
        return 0

    tulis_csv(header, runtime, CSV_PATH)
    print(f"ditulis: {CSV_PATH}")

    if not args.no_xlsx_mirror:
        XLSX_MIRROR_PATH.write_bytes(source.read_bytes())
        print(f"disalin: {XLSX_MIRROR_PATH} (mirror apa adanya dari workbook sumber)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
