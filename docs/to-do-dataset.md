# To-do Penyelarasan Dataset Kurikulum SMA/SMK

Dokumen ini menjadi rencana kerja untuk memeriksa sumber silabus, menata cakupan dataset runtime, dan memastikan prediksi materi membedakan siswa SMA dan SMK. Fokus khusus untuk SMK adalah mempertahankan **mata pelajaran umum** dalam dataset, sementara materi kejuruan yang sangat beragam antarprogram keahlian diserahkan kepada LLM.

## Tujuan

- Memastikan `DATA/kurikulum_merdeka.csv` benar-benar sesuai dengan workbook sumber `Kurikulum_Merdeka_Gabungan_Sempurna.xlsx`.
- Menyediakan silabus terstruktur bagi siswa SMA dan bagi mata pelajaran umum SMK yang tercakup dalam sumber.
- Menghindari klaim bahwa dataset memiliki silabus lengkap untuk semua jurusan SMK.
- Mengarahkan prediksi mapel kejuruan SMK ke LLM menggunakan riwayat tugas dan konteks request, dengan perilaku aman saat silabus tidak tersedia atau LLM gagal.
- Menjaga kompatibilitas request `/predict` yang sudah digunakan backend sejauh mungkin.

## Kondisi Saat Ini

- Prediktor membaca `DATA/kurikulum_merdeka.csv`; `DATA/silabus_awal.csv` menjadi cadangan jika CSV utama tidak ada.
- Kondisi awal (sebelum audit): CSV memiliki 910 baris: 337 SMA, 147 SMK, 325 SD, dan 101 SMP, plus salinan XLSX di `DATA/kurikulum_merdeka.xlsx`. Setelah audit dan regenerasi: **440 baris** (SMA 337 + SMK 103 mapel umum); SD dan SMP dibuang sesuai cakupan di atas.
- Sheet workbook yang relevan mencakup `Materi` dan `SMK - Rincian Sub-Bab`. Workbook sumber berada di luar repository pada direktori proyek induk.
- Endpoint `/predict` saat ini mengirim kelas dan kurikulum ke prediktor, tetapi belum mengirim jenjang. Fungsi pembaca silabus sudah menerima filter jenjang dan jalur/disiplin.
- Angka di atas adalah baseline awal dari CSV; hitungan dan perbedaan dengan workbook harus diverifikasi kembali dalam tahap audit sebelum dataset diubah.

## Keputusan Cakupan yang Dituju

| Jenis siswa dan mata pelajaran | Sumber prediksi utama | Status rujukan silabus |
|---|---|---|
| SMA, semua mapel yang tersedia | CSV silabus dengan filter jenjang dan kelas | `available` jika ada hasil cocok |
| SMK, mapel umum yang tersedia di sumber | CSV silabus dengan filter jenjang, kelas, dan mapel | `available` jika ada hasil cocok |
| SMK, mapel kejuruan atau mapel yang tidak tercakup | LLM dengan riwayat tugas dan konteks yang diizinkan | `unavailable` |
| LLM gagal untuk mapel tanpa silabus | Fallback deterministik generik yang jujur tentang keterbatasan rujukan | `unavailable` |

Daftar final mapel umum SMK harus diambil dari hasil audit sumber, bukan diketik berdasarkan asumsi. Jangan menambahkan semua mapel kejuruan dari satu atau beberapa jurusan seolah-olah dataset tersebut mewakili seluruh program keahlian di Indonesia.

## Rencana Kerja

### 1. Audit workbook dan CSV

- [x] Baca metadata workbook dan identifikasi header serta area data pada sheet `Materi` dan `SMK - Rincian Sub-Bab`.
- [x] Hitung baris data aktual per sheet, tidak termasuk baris judul, ringkasan, catatan, atau baris kosong.
- [x] Catat nama kolom dan padanannya terhadap skema CSV runtime: `ID`, `Jenjang`, `Kelas`, `Fase`, `Mata Pelajaran`, `Status Mapel`, `Jalur / Disiplin`, `No. Urut`, `Bab / Unit`, `Nama Topik`, `Elemen / Fokus`, `Sub-Materi`, dan `Relevansi Jurusan/Karir`.
- [x] Bandingkan jumlah baris, nilai unik jenjang, kelas, fase, mata pelajaran, status mapel, dan jalur/disiplin pada workbook dan CSV.
- [x] Periksa data kosong, duplikat, variasi ejaan, nomor urut, serta apakah sebuah rincian SMK merupakan topik tersendiri atau sub-materi dari topik induk.
- [x] Susun daftar mapel umum SMK yang eksplisit berdasarkan workbook dan tandai mapel vokasi yang harus dikeluarkan dari retrieval silabus runtime.
- [x] Tulis ringkasan audit pada dokumen ini: tanggal audit, nama file sumber, hitungan per sheet, hitungan CSV, temuan selisih, dan keputusan apakah ekspor ulang diperlukan.

**Kriteria selesai tahap:** pembaca dapat mengetahui secara konkret apakah CSV saat ini identik, subset, atau versi berbeda dari workbook; semua selisih penting dan keputusan ekspor tercatat.

### 2. Tetapkan dan hasilkan dataset runtime

- [x] Jika CSV sudah mencerminkan data terbaru, jangan melakukan ekspor ulang yang tidak diperlukan; tetap dokumentasikan sumber dan cakupan hasil audit. *(CSV lama memang identik dengan `Materi` kecuali kolom Relevansi SMK; ekspor ulang tetap dilakukan untuk memulihkan kolom itu dan menerapkan batas kejuruan.)*
- [x] Jika workbook lebih lengkap/terbaru atau CSV salah format, hasilkan ulang `DATA/kurikulum_merdeka.csv` dari data sumber yang benar.
- [x] Pertahankan nama header dan format yang dikenali `_normalize_row()` pada prediktor, termasuk encoding yang aman dibaca sebagai UTF-8/UTF-8 BOM.
- [x] Batasi baris runtime pada cakupan yang disepakati: seluruh data SMA yang relevan dan mapel umum SMK. Jangan memasukkan rincian mapel kejuruan SMK ke urutan prediksi umum.
- [x] Pertahankan identitas dan relasi baris yang diperlukan untuk audit; jangan mengubah rincian sub-bab menjadi topik berurutan kecuali relasi induk, kelas, mapel, serta urutannya dapat dipetakan dengan benar.
- [x] Tentukan apakah `DATA/kurikulum_merdeka.xlsx` adalah artefak sumber yang harus ikut diperbarui atau hanya salinan lama. Hindari menyisakan dua salinan yang tampak sebagai sumber resmi tetapi berbeda tanpa penjelasan.
- [x] Verifikasi ulang jumlah dan distribusi data runtime sesudah ekspor, lalu simpan ringkasan hasilnya di bagian **Hasil Audit dan Keputusan Dataset** di bawah.

**Kriteria selesai tahap:** CSV dapat dibaca parser saat ini, hanya berisi cakupan yang disetujui, dan jumlah/distribusi akhirnya tercatat serta dapat diulang dari sumber.

### 3. Teruskan jenjang ke alur `/predict`

- [x] Tambahkan field opsional `jenjang` pada `PredictionPayload`, dengan nilai yang didukung setidaknya `SMA` dan `SMK`.
- [x] Teruskan `jenjang` dari endpoint ke `predict_material()` dan kemudian ke `baca_silabus()`.
- [x] Pastikan filter jenjang diterapkan pada silabus yang diberikan baik ke prompt LLM maupun ke fallback deterministik; tidak boleh terjadi pencampuran baris SMA dan SMK pada kelas yang sama.
- [x] Untuk kelas 10–12 tanpa field `jenjang`, gunakan default **SMA** agar request lama tidak tiba-tiba mencampur dua jenjang dan tetap kompatibel. Klien/backend yang memprediksi siswa SMK harus mengirim `jenjang: "SMK"`.
- [x] Untuk jenjang selain SMA/SMK atau nilai yang tidak dikenal, pilih validasi konsisten pada batas API (disarankan respons validasi 422) dan jelaskan nilai yang diterima pada deskripsi field.
- [x] Pertahankan perilaku kelas kosong yang ada, kecuali hasil audit menemukan bahwa perilaku tersebut mencampur jenjang; bila perlu, dokumentasikan aturan default yang sama. *(Audit menemukan `class_level` kosong mengembalikan SMA+SMK sekaligus, jadi kelas kosong kini default SMA.)*

**Perubahan interface yang diharapkan:** request `/predict` mendapat field opsional `jenjang`. Respons tetap kompatibel; tidak perlu mengubah bentuk respons untuk pekerjaan ini.

### 4. Arahkan mapel vokasi SMK ke LLM dengan aman

- [x] Tentukan berdasarkan jenjang dan hasil pencarian silabus apakah request merupakan mapel umum yang didukung atau mapel yang tidak tercakup (termasuk mapel kejuruan).
- [x] Jika ada silabus cocok, jalankan alur saat ini dengan silabus sebagai konteks retrieval.
- [x] Jika tidak ada silabus cocok, tetap berikan LLM riwayat tugas dan konteks siswa yang sudah diizinkan oleh kontrak; jangan mengirim nama lengkap, catatan pribadi, atau deskripsi rahasia.
- [x] Prompt harus membedakan materi yang benar-benar didukung silabus dari prediksi berbasis inferensi. LLM tidak boleh diminta mengaku menemukan referensi kurikulum yang tidak diberikan.
- [x] Pastikan metadata hasil menunjukkan `syllabus_reference: "unavailable"` ketika retrieval kosong, termasuk jika LLM berhasil memberi prediksi.
- [x] Saat LLM timeout, output rusak, atau provider gagal untuk mapel tanpa silabus, berikan fallback deterministik generik dengan `source: "fallback"`, `syllabus_reference: "unavailable"`, dan tingkat keyakinan yang tidak menyiratkan validasi oleh dataset.
- [x] Pastikan request dengan silabus tersedia tetap mempertahankan fallback kurikulum yang sekarang.
- [x] Jangan mengubah pemilihan mapel umum/vokasi lewat tebakan nama jurusan yang rapuh. Gunakan kecocokan dataset/alias yang teruji; mapel yang tidak cocok diperlakukan sebagai tidak tercakup dan diarahkan ke LLM.

**Kriteria selesai tahap:** mapel kejuruan tidak menerima silabus yang salah, LLM tetap dapat memprediksi dari konteks yang ada, dan kegagalan provider tidak menimbulkan HTTP 500.

### 5. Tambahkan pengujian

- [x] Tambahkan tes dataset untuk header, jumlah data yang diharapkan, cakupan jenjang, kelas, mapel umum SMK, dan tidak adanya rincian mapel kejuruan pada runtime (sesuaikan angka setelah audit final).
- [x] Uji `baca_silabus()` untuk kelas 10, 11, dan 12 dengan `jenjang="SMA"` dan `jenjang="SMK"`; pastikan setiap hasil hanya berisi jenjang yang diminta.
- [x] Uji mapel umum yang sama-sama muncul di SMA/SMK agar filter jenjang benar-benar mengubah himpunan hasil.
- [x] Uji mapel umum SMK yang tercatat dari audit dan satu atau lebih alias yang memang didukung.
- [x] Uji mapel vokasi yang tidak ada di dataset: retrieval kosong, LLM mock tetap dipanggil, dan hasil menandai silabus tidak tersedia.
- [x] Uji kegagalan LLM untuk mapel vokasi: fallback aman, sumber fallback, rujukan unavailable, dan tidak ada exception yang lolos.
- [x] Uji request `/predict` lama tanpa `jenjang` pada kelas 10–12: memilih SMA.
- [x] Uji request `/predict` dengan `jenjang="SMK"`: filter SMK diteruskan; uji juga nilai jenjang tidak valid sesuai aturan validasi yang dipilih.
- [x] Jalankan suite offline dengan mock/monkeypatch; tes tidak boleh memerlukan internet atau API key nyata.

### 6. Perbarui dokumentasi proyek

- [x] Perbarui README: file yang benar-benar dibaca saat runtime, hubungan CSV dengan XLSX sumber, cakupan SMA dan mapel umum SMK, serta batas cakupan kejuruan.
- [x] Perbarui dokumentasi kontrak `/predict`: field `jenjang`, nilai yang diterima, default SMA untuk payload lama, dan contoh request SMK.
- [x] Perbarui `AGENTS.md`: peta dataset, alur filter jenjang, routing mapel tanpa silabus ke LLM, dan batas privasi/fallback yang relevan.
- [x] Perbarui dokumentasi teknis lain hanya bila masih menyebut silabus lama atau cakupan yang sudah tidak benar; hindari menyebarkan klaim angka yang belum diverifikasi.
- [x] Tambahkan contoh payload ringkas untuk SMA dan SMK mapel umum, serta satu contoh mapel vokasi dengan penjelasan bahwa prediksi tidak memiliki rujukan silabus runtime.

### 7. Contoh payload `/predict`

**SMA, mapel umum — silabus tersedia:**

```json
{
  "subject": "Matematika",
  "difficulty": 4,
  "class_level": "11",
  "jenjang": "SMA",
  "history": [
    {"title": "PR Fungsi", "material_name": "Fungsi Komposisi dan Fungsi Invers", "deadline": "2026-11-20"}
  ]
}
```

Hasil: `syllabus_reference: "available"`, topik mengikuti alur silabus SMA.

**SMK, mapel umum — silabus tersedia dan berfilter SMK:**

```json
{
  "subject": "Matematika",
  "difficulty": 4,
  "class_level": "11",
  "jenjang": "SMK",
  "history": [
    {"title": "PR Fungsi", "material_name": "Fungsi Komposisi dan Fungsi Invers", "deadline": "2026-11-20"}
  ]
}
```

Hasil: `syllabus_reference: "available"`, topik dari baris SMK (mis.
`Matriks dan Aljabar Linear Terapan`), bukan dari baris SMA.

**SMK, mapel vokasi — tidak ada rujukan silabus runtime:**

```json
{
  "subject": "Pengembangan Perangkat Lunak dan Gim (PPLG)",
  "difficulty": 4,
  "class_level": "11",
  "jenjang": "SMK",
  "history": [
    {"title": "Projek Web", "material_name": "Pemrograman Web Frontend", "deadline": "2026-11-25"}
  ]
}
```

Hasil: `syllabus_reference: "unavailable"`. LLM memprediksi dari riwayat tugas;
bila LLM gagal, fallback deterministik tetap mengembalikan
`syllabus_reference: "unavailable"` dengan `source: "fallback"` dan confidence rendah.

## Hasil Audit dan Keputusan Dataset

Audit dijalankan pada **20 November 2026** terhadap workbook
`../Kurikulum_Merdeka_Gabungan_Sempurna.xlsx` (di direktori proyek induk) dan
`DATA/kurikulum_merdeka.csv` sebelum regenerasi. Pelaksana: AI agent (Sisyphus),
diverifikasi dengan skrip `scripts/regen_dataset.py`.

| Sumber | Baris data | Jenjang/kelas/mapel | Catatan |
|---|---:|---|---|
| Workbook — `Materi` | 910 | SD 325, SMP 101, SMA 337, SMK 147; kelas 1–12; 46 kombinasi mapel-jenjang | Header identik dengan skema CSV runtime |
| Workbook — `SMK - Rincian Sub-Bab` | 294 | SMK kelas 10–12, 14 mapel | 147 bab × 2 sub-bab (`x.1 Konsep Pokok`, `x.2 Prosedur Praktik`) |
| CSV runtime (sebelum) | 910 | SD, SMP, SMA, SMK; kelas 1–12 | **Identik** dengan sheet `Materi` kecuali satu kolom |
| CSV runtime (sesudah) | **440** | SMA 337, SMK 103 | SD 325, SMP 101, dan 44 baris SMK kejuruan dibuang |

### Temuan selisih

Perbandingan sel per sel antara sheet `Materi` dan CSV lama: **147 sel berbeda,
semuanya pada kolom `Relevansi Jurusan/Karir`**. Workbook mengisi kolom itu untuk
147 baris SMK, sedangkan CSV lama mengosongkannya (hanya 16 baris SMA Informatika
yang terisi di CSV). Tidak ada selisih pada jenjang, kelas, fase, mapel, status,
jalur, nomor urut, bab, topik, elemen, maupun sub-materi.

Tidak ditemukan duplikat `(Jenjang, Kelas, Mapel, Jalur, No. Urut)`, tidak ada
nomor urut bolong per kelompok mapel, dan fase konsisten dengan kelas.

### Cakupan yang dibuang

| Kelompok | Baris | Alasan |
|---|---:|---|
| SD | 325 | Kelas 1–6; engine memprediksi siswa SMA/SMK |
| SMP | 101 | Kelas 7–9; engine memprediksi siswa SMA/SMK |
| SMK kejuruan | 44 | PPLG, TJKT, PKK, PKL; tidak mewakili seluruh program keahlian |

Baris SD dan SMP tetap tersedia di `DATA/kurikulum_merdeka.xlsx` (salinan workbook
sumber) sebagai rujukan audit. Bila request datang dengan kelas SD/SMP, prediktor
tidak melempar error: silabus kosong, hasil memakai `syllabus_reference: "unavailable"`.

### Keputusan ekspor ulang

Ekspor ulang **dilakukan**, dengan tiga alasan dan bukan karena data tidak sinkron:

1. Memulihkan kolom `Relevansi Jurusan/Karir` untuk 147 baris SMK yang hilang di CSV lama.
2. Menerapkan cakupan yang disepakati: hanya SMA + mapel umum SMK (membuang SD 325 dan SMP 101).
3. Membuang 44 baris SMK kejuruan.

Sumber regenerasi tunggal adalah `scripts/regen_dataset.py` yang membaca sheet
`Materi` dan menurunkan daftar mapel umum SMK dari kolom `Keterangan` = "Mata
Pelajaran Umum" pada sheet `Daftar Mapel`. `DATA/kurikulum_merdeka.xlsx` kini
merupakan **salinan byte-identik** dari workbook sumber, bukan artefak kedua yang
berbeda.

- **Mapel umum SMK yang dipertahankan (10 mapel, 103 baris):** Pendidikan Agama dan
  Budi Pekerti (14), Pendidikan Pancasila (11), Bahasa Indonesia (15), Matematika (15),
  Bahasa Inggris (14), Sejarah (6), Seni dan Budaya (4), PJOK (9), Informatika (8),
  Ilmu Pengetahuan Alam dan Sosial/IPAS (7).
- **Mapel/rincian vokasi yang dikecualikan dari retrieval runtime (4 mapel, 44 baris):**
  Pengembangan Perangkat Lunak dan Gim/PPLG (15), Teknik Jaringan Komputer dan
  Telekomunikasi/TJKT (15), Projek Kreatif dan Kewirausahaan (9),
  Praktik Kerja Lapangan/PKL (5).
- **Selisih workbook terhadap CSV awal:** hanya kolom `Relevansi Jurusan/Karir` pada SMK
  (147 sel), sudah dipulihkan. Cakupan CSV akhir sengaja menyusut (440 dari 910) karena
  SD, SMP, dan SMK kejuruan di luar cakupan.
- **Keputusan ekspor ulang:** ya, lihat alasan di atas. Cakupan akhir: SMA + mapel umum SMK (440 baris).
- **Tanggal dan pelaksana audit:** 20 November 2026, AI agent (diverifikasi skrip).

### Catatan penting tentang `SMK - Rincian Sub-Bab`

Sheet ini (294 baris) berisi rincian sub-bab yang lebih rinci daripada sheet `Materi`
(147 baris SMK). Rincian itu **tidak** diekspor ke runtime karena:

- sub-bab bukan topik berurutan mandiri; ia menempel pada bab induk;
- memasukkannya akan menggandakan alur `No. Urut + 1` dan merusak prediksi sekuensial;
- sheet `Materi` sudah memuat peta topik per kelas yang dibutuhkan prediktor.

Sheet tersebut tetap tersedia di `DATA/kurikulum_merdeka.xlsx` sebagai rujukan audit.


## Urutan Pelaksanaan yang Disarankan

1. Selesaikan audit workbook dan tetapkan daftar mapel umum SMK.
2. Putuskan apakah CSV runtime perlu dibuat ulang dan verifikasi artefaknya.
3. Implementasikan filter jenjang dan alur mapel tanpa silabus menuju LLM/fallback.
4. Tambahkan tes unit dan endpoint berdasarkan perilaku yang disepakati.
5. Perbarui dokumentasi kontrak dan instruksi proyek.
6. Jalankan seluruh suite pytest offline dan tinjau diff dataset serta dokumentasi sebelum menyelesaikan pekerjaan.

## Kriteria Selesai Keseluruhan

- [x] Keputusan sumber dan cakupan dataset didukung hasil perbandingan workbook–CSV yang terdokumentasi.
- [x] Runtime berisi materi SMA dan hanya mapel umum SMK sesuai hasil audit.
- [x] Prediksi SMA/SMK tidak bercampur; request SMK dapat menyatakan jenjang secara eksplisit.
- [x] Mapel vokasi yang tidak ada pada dataset diarahkan ke LLM tanpa klaim rujukan silabus; kegagalan LLM tetap menghasilkan fallback aman.
- [x] Tes dataset, prediktor, endpoint, backward compatibility, dan jalur kegagalan lulus secara offline.
- [ ] README, kontrak API, dan `AGENTS.md` menjelaskan perilaku yang sama dan tidak memuat hitungan atau cakupan usang.
