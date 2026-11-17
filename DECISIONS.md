# Architecture Decision Records (ADR) - OCI Telegram Bot

Dokumen ini mencatat keputusan-keputusan arsitektur fundamental yang telah disepakati bersama. Tujuannya adalah memastikan AI Agent dan developer di masa depan memahami *mengapa* suatu solusi dipilih dan tidak merombak keputusan yang sudah matang.

---

### ADR-001: Manajemen Kredensial Multi-Akun via File Deklaratif Lokal
- **Status**: Disetujui
- **Konteks**: Aplikasi perlu mengelola 3 hingga 10 akun OCI (tenancy OCID, user OCID, fingerprint, region, dan file private key `.pem`).
- **Keputusan**: Kredensial disimpan secara terstruktur di `config/accounts.yaml` dengan file kunci privat diletakkan di `credentials/keys/*.pem` pada server lokal, dilindungi oleh `.gitignore` dan permission file `chmod 600`.
- **Alasan**: Opsi mengunggah file `.pem` via Telegram Bot memiliki risiko keamanan tinggi karena file kriptografis sensitif akan transit dan tersimpan di server cloud pihak ketiga (Telegram). Penyimpanan lokal adalah standar baku industri DevOps.

---

### ADR-002: Pola Notifikasi "Silent Incident Watchdog"
- **Status**: Disetujui
- **Konteks**: Scheduler memeriksa status instance dan metrik setiap 5/10/30 menit dan tagihan setiap 3/6/12 jam.
- **Keputusan**: Background worker berjalan senyap di latar belakang dan **HANYA** mengirim push notification ke DM Admin jika terdeteksi insiden/anomali (VM mati mendadak, CPU > 85%, budget terlampaui, atau recovery).
- **Alasan**: Mencegah spam pesan berkala yang mengganggu di DM Telegram Admin. Laporan status lengkap dan tagihan tetap dapat diakses kapan saja secara on-demand via perintah `/status`, `/instances`, atau `/billing`.

---

### ADR-003: Proyeksi Biaya Menggunakan Algoritma Linear Run-Rate
- **Status**: Disetujui
- **Konteks**: Pengguna membutuhkan estimasi tagihan hingga akhir bulan untuk akun PAYG.
- **Keputusan**: Menggunakan formula linear run-rate:
  $$\text{Forecast} = \left(\frac{\text{Biaya Aktual (MTD)}}{\text{Hari Berjalan}}\right) \times \text{Total Hari Bulan Ini}$$
- **Alasan**: Fitur Forecast bawaan OCI API tidak selalu tersedia atau aktif di semua tenancy (terutama tenancy baru atau akun Free Tier). Rumus linear run-rate bersifat deterministik, independen, dan sangat akurat untuk resource cloud yang menyala 24/7. Akun Free Tier/Trial secara otomatis di-set ke `$0.00`.

---

### ADR-004: Resolusi Public IP & Private IP Melalui VNIC Attachment
- **Status**: Disetujui
- **Konteks**: Pengguna ingin melihat Public IP dari masing-masing compute instance di Telegram.
- **Keputusan**: Mengambil VNIC ID dari instance via `ComputeClient.list_vnic_attachments`, kemudian mengambil Public IP dan Private IP via `VirtualNetworkClient.get_vnic`, lalu menyimpannya di tabel cache `INSTANCE_STATE` di database SQLite.
- **Alasan**: Di OCI, Public IP menempel pada VNIC dan bukan objek instance langsung. Menyimpannya di cache database membuat query tampilan di Telegram instan tanpa delay latensi jaringan.

---

### ADR-005: SQLite dengan Write-Ahead Logging (WAL Mode) sebagai Basis Data
- **Status**: Disetujui
- **Konteks**: Aplikasi membutuhkan penyimpanan relasional untuk metadata akun, status instance, log metrik, histori tagihan, dan pengaturan.
- **Keputusan**: Menggunakan SQLite lokal dengan SQLAlchemy 2.0 (async via `aiosqlite`) dan mengaktifkan `PRAGMA journal_mode = WAL`.
- **Alasan**: SQLite bersifat self-contained, nol dependensi server tambahan, sangat ringan, dan WAL mode memungkinkan operasi baca (read oleh Telegram bot) dan tulis (write oleh scheduler) berjalan konkuren tanpa database lock issue.

---

### ADR-006: In-Process APScheduler dengan Runtime Rescheduling
- **Status**: Disetujui
- **Konteks**: Polling interval dapat diubah antara 5/10/30 menit untuk metrik dan 3/6/12 jam untuk tagihan.
- **Keputusan**: Menggunakan `APScheduler` (`AsyncIOScheduler`) yang berjalan di dalam event loop asyncio aplikasi yang sama, dengan kemampuan `scheduler.reschedule_job(...)` langsung dari handler Telegram `/settings`.
- **Alasan**: Tidak memerlukan sistem antrean rumit seperti Redis atau Celery, sangat hemat RAM untuk VPS kecil, dan perubahan interval langsung aktif saat itu juga tanpa perlu restart aplikasi.

---

### ADR-007: Pengamanan Aksi Daya Dua Langkah (Two-Step Confirmation)
- **Status**: Disetujui
- **Konteks**: Bot memiliki fitur untuk mematikan (`STOP`), menghidupkan (`START`), dan me-reboot instance.
- **Keputusan**: Wajib menampilkan konfirmasi Inline Keyboard (`[✅ Ya, Eksekusi]` / `[❌ Batalkan]`) sebelum aksi dikirim ke OCI API, serta mencatat setiap eksekusi ke `AUDIT_LOG`.
- **Alasan**: Menghindari pemadaman server produksi yang tidak disengaja akibat kesalahan ketukan tombol di layar HP.
