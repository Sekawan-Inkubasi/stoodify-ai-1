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
- CSV memiliki 910 baris: 337 SMA, 147 SMK, 325 SD, dan 101 SMP. CSV runtime juga memiliki salinan XLSX di `DATA/kurikulum_merdeka.xlsx`.
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

- [ ] Baca metadata workbook dan identifikasi header serta area data pada sheet `Materi` dan `SMK - Rincian Sub-Bab`.
- [ ] Hitung baris data aktual per sheet, tidak termasuk baris judul, ringkasan, catatan, atau baris kosong.
- [ ] Catat nama kolom dan padanannya terhadap skema CSV runtime: `ID`, `Jenjang`, `Kelas`, `Fase`, `Mata Pelajaran`, `Status Mapel`, `Jalur / Disiplin`, `No. Urut`, `Bab / Unit`, `Nama Topik`, `Elemen / Fokus`, `Sub-Materi`, dan `Relevansi Jurusan/Karir`.
- [ ] Bandingkan jumlah baris, nilai unik jenjang, kelas, fase, mata pelajaran, status mapel, dan jalur/disiplin pada workbook dan CSV.
- [ ] Periksa data kosong, duplikat, variasi ejaan, nomor urut, serta apakah sebuah rincian SMK merupakan topik tersendiri atau sub-materi dari topik induk.
- [ ] Susun daftar mapel umum SMK yang eksplisit berdasarkan workbook dan tandai mapel vokasi yang harus dikeluarkan dari retrieval silabus runtime.
- [ ] Tulis ringkasan audit pada dokumen ini: tanggal audit, nama file sumber, hitungan per sheet, hitungan CSV, temuan selisih, dan keputusan apakah ekspor ulang diperlukan.

**Kriteria selesai tahap:** pembaca dapat mengetahui secara konkret apakah CSV saat ini identik, subset, atau versi berbeda dari workbook; semua selisih penting dan keputusan ekspor tercatat.

### 2. Tetapkan dan hasilkan dataset runtime

- [ ] Jika CSV sudah mencerminkan data terbaru, jangan melakukan ekspor ulang yang tidak diperlukan; tetap dokumentasikan sumber dan cakupan hasil audit.
- [ ] Jika workbook lebih lengkap/terbaru atau CSV salah format, hasilkan ulang `DATA/kurikulum_merdeka.csv` dari data sumber yang benar.
- [ ] Pertahankan nama header dan format yang dikenali `_normalize_row()` pada prediktor, termasuk encoding yang aman dibaca sebagai UTF-8/UTF-8 BOM.
- [ ] Batasi baris runtime pada cakupan yang disepakati: seluruh data SMA yang relevan dan mapel umum SMK. Jangan memasukkan rincian mapel kejuruan SMK ke urutan prediksi umum.
- [ ] Pertahankan identitas dan relasi baris yang diperlukan untuk audit; jangan mengubah rincian sub-bab menjadi topik berurutan kecuali relasi induk, kelas, mapel, serta urutannya dapat dipetakan dengan benar.
- [ ] Tentukan apakah `DATA/kurikulum_merdeka.xlsx` adalah artefak sumber yang harus ikut diperbarui atau hanya salinan lama. Hindari menyisakan dua salinan yang tampak sebagai sumber resmi tetapi berbeda tanpa penjelasan.
- [ ] Verifikasi ulang jumlah dan distribusi data runtime sesudah ekspor, lalu simpan ringkasan hasilnya di bagian **Hasil Audit dan Keputusan Dataset** di bawah.

**Kriteria selesai tahap:** CSV dapat dibaca parser saat ini, hanya berisi cakupan yang disetujui, dan jumlah/distribusi akhirnya tercatat serta dapat diulang dari sumber.

### 3. Teruskan jenjang ke alur `/predict`

- [ ] Tambahkan field opsional `jenjang` pada `PredictionPayload`, dengan nilai yang didukung setidaknya `SMA` dan `SMK`.
- [ ] Teruskan `jenjang` dari endpoint ke `predict_material()` dan kemudian ke `baca_silabus()`.
- [ ] Pastikan filter jenjang diterapkan pada silabus yang diberikan baik ke prompt LLM maupun ke fallback deterministik; tidak boleh terjadi pencampuran baris SMA dan SMK pada kelas yang sama.
- [ ] Untuk kelas 10–12 tanpa field `jenjang`, gunakan default **SMA** agar request lama tidak tiba-tiba mencampur dua jenjang dan tetap kompatibel. Klien/backend yang memprediksi siswa SMK harus mengirim `jenjang: "SMK"`.
- [ ] Untuk jenjang selain SMA/SMK atau nilai yang tidak dikenal, pilih validasi konsisten pada batas API (disarankan respons validasi 422) dan jelaskan nilai yang diterima pada deskripsi field.
- [ ] Pertahankan perilaku kelas kosong yang ada, kecuali hasil audit menemukan bahwa perilaku tersebut mencampur jenjang; bila perlu, dokumentasikan aturan default yang sama.

**Perubahan interface yang diharapkan:** request `/predict` mendapat field opsional `jenjang`. Respons tetap kompatibel; tidak perlu mengubah bentuk respons untuk pekerjaan ini.

### 4. Arahkan mapel vokasi SMK ke LLM dengan aman

- [ ] Tentukan berdasarkan jenjang dan hasil pencarian silabus apakah request merupakan mapel umum yang didukung atau mapel yang tidak tercakup (termasuk mapel kejuruan).
- [ ] Jika ada silabus cocok, jalankan alur saat ini dengan silabus sebagai konteks retrieval.
- [ ] Jika tidak ada silabus cocok, tetap berikan LLM riwayat tugas dan konteks siswa yang sudah diizinkan oleh kontrak; jangan mengirim nama lengkap, catatan pribadi, atau deskripsi rahasia.
- [ ] Prompt harus membedakan materi yang benar-benar didukung silabus dari prediksi berbasis inferensi. LLM tidak boleh diminta mengaku menemukan referensi kurikulum yang tidak diberikan.
- [ ] Pastikan metadata hasil menunjukkan `syllabus_reference: "unavailable"` ketika retrieval kosong, termasuk jika LLM berhasil memberi prediksi.
- [ ] Saat LLM timeout, output rusak, atau provider gagal untuk mapel tanpa silabus, berikan fallback deterministik generik dengan `source: "fallback"`, `syllabus_reference: "unavailable"`, dan tingkat keyakinan yang tidak menyiratkan validasi oleh dataset.
- [ ] Pastikan request dengan silabus tersedia tetap mempertahankan fallback kurikulum yang sekarang.
- [ ] Jangan mengubah pemilihan mapel umum/vokasi lewat tebakan nama jurusan yang rapuh. Gunakan kecocokan dataset/alias yang teruji; mapel yang tidak cocok diperlakukan sebagai tidak tercakup dan diarahkan ke LLM.

**Kriteria selesai tahap:** mapel kejuruan tidak menerima silabus yang salah, LLM tetap dapat memprediksi dari konteks yang ada, dan kegagalan provider tidak menimbulkan HTTP 500.

### 5. Tambahkan pengujian

- [ ] Tambahkan tes dataset untuk header, jumlah data yang diharapkan, cakupan jenjang, kelas, mapel umum SMK, dan tidak adanya rincian mapel kejuruan pada runtime (sesuaikan angka setelah audit final).
- [ ] Uji `baca_silabus()` untuk kelas 10, 11, dan 12 dengan `jenjang="SMA"` dan `jenjang="SMK"`; pastikan setiap hasil hanya berisi jenjang yang diminta.
- [ ] Uji mapel umum yang sama-sama muncul di SMA/SMK agar filter jenjang benar-benar mengubah himpunan hasil.
- [ ] Uji mapel umum SMK yang tercatat dari audit dan satu atau lebih alias yang memang didukung.
- [ ] Uji mapel vokasi yang tidak ada di dataset: retrieval kosong, LLM mock tetap dipanggil, dan hasil menandai silabus tidak tersedia.
- [ ] Uji kegagalan LLM untuk mapel vokasi: fallback aman, sumber fallback, rujukan unavailable, dan tidak ada exception yang lolos.
- [ ] Uji request `/predict` lama tanpa `jenjang` pada kelas 10–12: memilih SMA.
- [ ] Uji request `/predict` dengan `jenjang="SMK"`: filter SMK diteruskan; uji juga nilai jenjang tidak valid sesuai aturan validasi yang dipilih.
- [ ] Jalankan suite offline dengan mock/monkeypatch; tes tidak boleh memerlukan internet atau API key nyata.

### 6. Perbarui dokumentasi proyek

- [ ] Perbarui README: file yang benar-benar dibaca saat runtime, hubungan CSV dengan XLSX sumber, cakupan SMA dan mapel umum SMK, serta batas cakupan kejuruan.
- [ ] Perbarui dokumentasi kontrak `/predict`: field `jenjang`, nilai yang diterima, default SMA untuk payload lama, dan contoh request SMK.
- [ ] Perbarui `AGENTS.md`: peta dataset, alur filter jenjang, routing mapel tanpa silabus ke LLM, dan batas privasi/fallback yang relevan.
- [ ] Perbarui dokumentasi teknis lain hanya bila masih menyebut silabus lama atau cakupan yang sudah tidak benar; hindari menyebarkan klaim angka yang belum diverifikasi.
- [ ] Tambahkan contoh payload ringkas untuk SMA dan SMK mapel umum, serta satu contoh mapel vokasi dengan penjelasan bahwa prediksi tidak memiliki rujukan silabus runtime.

## Hasil Audit dan Keputusan Dataset

Isi bagian ini setelah tahap audit selesai. Jangan mengisi angka hasil akhir berdasarkan baseline awal tanpa verifikasi workbook.

| Sumber | Baris data | Jenjang/kelas/mapel | Catatan |
|---|---:|---|---|
| Workbook — `Materi` | Belum diaudit | Belum diaudit | Isi setelah pemeriksaan |
| Workbook — `SMK - Rincian Sub-Bab` | Belum diaudit | Belum diaudit | Isi setelah pemeriksaan |
| CSV runtime | 910 (baseline awal) | SD, SMP, SMA, SMK; kelas 1–12 | Hitung ulang setelah audit |

- **Mapel umum SMK yang dipertahankan:** belum ditetapkan; isi dari hasil audit.
- **Mapel/rincian vokasi yang dikecualikan dari retrieval runtime:** belum ditetapkan; isi dari hasil audit.
- **Selisih workbook terhadap CSV:** belum diaudit.
- **Keputusan ekspor ulang:** belum diputuskan; hanya dilakukan jika audit menunjukkan kebutuhan.
- **Tanggal dan pelaksana audit:** belum diisi.

## Urutan Pelaksanaan yang Disarankan

1. Selesaikan audit workbook dan tetapkan daftar mapel umum SMK.
2. Putuskan apakah CSV runtime perlu dibuat ulang dan verifikasi artefaknya.
3. Implementasikan filter jenjang dan alur mapel tanpa silabus menuju LLM/fallback.
4. Tambahkan tes unit dan endpoint berdasarkan perilaku yang disepakati.
5. Perbarui dokumentasi kontrak dan instruksi proyek.
6. Jalankan seluruh suite pytest offline dan tinjau diff dataset serta dokumentasi sebelum menyelesaikan pekerjaan.

## Kriteria Selesai Keseluruhan

- [ ] Keputusan sumber dan cakupan dataset didukung hasil perbandingan workbook–CSV yang terdokumentasi.
- [ ] Runtime berisi materi SMA dan hanya mapel umum SMK sesuai hasil audit.
- [ ] Prediksi SMA/SMK tidak bercampur; request SMK dapat menyatakan jenjang secara eksplisit.
- [ ] Mapel vokasi yang tidak ada pada dataset diarahkan ke LLM tanpa klaim rujukan silabus; kegagalan LLM tetap menghasilkan fallback aman.
- [ ] Tes dataset, prediktor, endpoint, backward compatibility, dan jalur kegagalan lulus secara offline.
- [ ] README, kontrak API, dan `AGENTS.md` menjelaskan perilaku yang sama dan tidak memuat hitungan atau cakupan usang.
