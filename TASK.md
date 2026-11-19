# TASK.md - Implementation Roadmap & Progress Tracker

Checklist granular pekerjaan proyek **OCI Multi-Account Telegram Monitoring Bot**. Setiap task memiliki status `[ ]` (belum selesai) atau `[x]` (selesai).

---

## [x] FASE 1: Environment, Konfigurasi & Basis Data SQLite
- [x] **1.1 Dependensi & Konfigurasi Lingkungan**:
  - [x] Buat file `requirements.txt` (oci, python-telegram-bot, apscheduler, sqlalchemy, aiosqlite, pydantic, pyyaml, matplotlib, pytest).
  - [x] Buat file `.env.example` dan modul `config/settings.py` menggunakan `pydantic-settings`.
  - [x] Buat file template `config/accounts.yaml.example` untuk 3–10 akun OCI.
  - [x] Buat parser konfigurasi akun di `config/parser.py` dengan validasi path file `.pem`.
- [x] **1.2 Skema Database & Migrasi Otomatis**:
  - [x] Buat engine koneksi SQLite async di `src/database/connection.py` dengan pengaktifan `WAL mode`.
  - [x] Buat model ORM SQLAlchemy di `src/database/models.py` (`Account`, `InstanceState`, `MetricsLog`, `BillingSnapshot`, `AuditLog`, `BotSetting`).
  - [x] Buat fungsi inisialisasi tabel otomatis dan sinkronisasi metadata akun dari YAML ke database.
- [x] **1.3 Unit Test Fase 1**:
  - [x] Buat `tests/test_config.py` dan `tests/test_database.py`.

---

## [x] FASE 2: OCI Multi-Account Service Layer
- [x] **2.1 OCI Client Factory**:
  - [x] Buat `src/oci_services/client_factory.py` untuk menginisialisasi client OCI SDK (Compute, VirtualNetwork, Monitoring, UsageAPI) per akun dari dictionary config in-memory.
  - [x] Tambahkan verifikasi handshake kredensial saat startup.
- [x] **2.2 Compute & IP Resolution Service**:
  - [x] Buat `src/oci_services/compute.py`:
    - `list_instances()`: Ambil daftar VM per compartment.
    - Resolusi IP: Ambil VNIC attachment dan ekstrak `public_ip` dan `private_ip` via `VirtualNetworkClient`.
    - `execute_action()`: Eksekusi kontrol daya (`START`, `STOP`, `SOFTRESET`).
- [x] **2.3 Monitoring / Telemetry Service**:
  - [x] Buat `src/oci_services/monitoring.py`:
    - Query MQL utilisasi CPU 5–15 menit terakhir dari namespace `oci_computeagent`.
- [x] **2.4 Billing & Forecast Service**:
  - [x] Buat `src/oci_services/billing.py`:
    - Query `RequestSummarizedUsagesDetails` untuk akumulasi biaya bulan berjalan (MTD).
    - Implementasikan kalkulasi linear run-rate forecast hingga akhir bulan.
    - Implementasikan penanganan fallback khusus akun Free Tier / Trial ($0.00 tanpa error).
- [x] **2.5 Unit Test Fase 2**:
  - [x] Buat `tests/test_oci_services.py` dengan mock data OCI SDK.

---

## [x] FASE 3: Background Scheduler & Incident Watchdog
- [x] **3.1 Dynamic Scheduler Manager**:
  - [x] Buat `src/scheduler/manager.py` menggunakan `APScheduler` (`AsyncIOScheduler`).
  - [x] Implementasikan fungsi reschedule dinamis untuk interval status (5/10/30m) dan billing (3/6/12h).
- [x] **3.2 Polling Tasks & State Diff Engine**:
  - [x] Buat `src/scheduler/tasks.py`:
    - Task periodic status VM & utilisasi CPU.
    - Task periodic akumulasi billing & snapshot.
- [x] **3.3 Silent Incident Detector**:
  - [x] Buat `src/scheduler/detector.py`:
    - Deteksi transisi status tidak terduga (`RUNNING` -> `STOPPED`).
    - Deteksi CPU spike (`> 85%` selama 2 siklus berurutan).
    - Deteksi pelanggaran budget bulanan PAYG.
    - Deteksi pemulihan status (`RUNNING`).
- [x] **3.4 Unit Test Fase 3**:
  - [x] Buat `tests/test_scheduler.py` dan `tests/test_detector.py`.

---

## [x] FASE 4: Telegram Bot UI, Handlers & Chart Generator
- [x] **4.1 Security Middleware & Formatting**:
  - [x] Buat `src/bot/middleware.py` untuk validasi `TELEGRAM_ADMIN_USER_ID`.
  - [x] Buat `src/bot/formatters.py` untuk template pesan HTML dengan emoji status.
  - [x] Buat `src/bot/keyboards.py` untuk Inline Keyboard menu navigasi dan konfirmasi dua langkah.
- [x] **4.2 On-Demand Chart Generator**:
  - [x] Buat `src/bot/charts.py` untuk merender grafik garis utilisasi CPU menggunakan Matplotlib ke buffer in-memory `BytesIO`.
- [x] **4.3 Command Handlers**:
  - [x] `/start` dan `/help`: Pengenalan dan panduan penggunaan bot.
  - [x] `/status`: Ringkasan instan seluruh akun dan VM.
  - [x] `/instances`: Navigasi daftar instance, detail Public IP, dan tombol aksi Start/Stop dengan dialog konfirmasi.
  - [x] `/billing`: Rekapitulasi MTD spend, estimasi forecast, dan status budget seluruh akun.
  - [x] `/settings`: Menu interaktif ubah interval polling (5/10/30m dan 3/6/12h).
- [x] **4.4 Application Runner**:
  - [x] Hubungkan router bot, scheduler, dan database di `src/main.py`.

---

## [x] FASE 5: Hardening, Dockerization & Panduan Operasional
- [x] **5.1 Dockerization**:
  - [x] Buat `Dockerfile` berbasis Python 3.11 slim.
  - [x] Buat `docker-compose.yml` dengan volume mounting untuk `data/` dan `credentials/`.
- [x] **5.2 Dokumentasi & Pengujian Akhir**:
  - [x] Lengkapi panduan setup kredensial OCI di `README.md`.
  - [x] Buat Buku Panduan Pengguna terpusat di `docs/USER_GUIDE.md` (Panduan Kredensial OCI, Bot Telegram, Operasional, Deployment, FAQ).
  - [x] Jalankan end-to-end suite test (`pytest tests/ -v`).

---

## [x] FASE 6: Observabilitas & Conditional Rotating File Logging
- [x] **6.1 Konfigurasi & Modul Logging Terdedikasi**:
  - [x] Tambahkan opsi konfigurasi log (`LOG_FILE_PATH`, `LOG_FILE_MAX_BYTES`, `LOG_FILE_BACKUP_COUNT`) di `config/settings.py` dan `.env.example`.
  - [x] Buat `src/logging_config.py` dengan `setup_logging()` dan `RotatingFileHandler` kondisional (hanya aktif jika `LOG_LEVEL = DEBUG`).
  - [x] Hubungkan `setup_logging` ke `src/main.py`.
- [x] **6.2 Hardening Docker & Mount Logs**:
  - [x] Perbarui `Dockerfile` (`mkdir -p /app/logs`) dan `docker-compose.yml` (`./logs:/app/logs`).
- [x] **6.3 Unit Testing & Dokumentasi**:
  - [x] Buat unit test suite di `tests/test_logging.py` (5 unit test).
  - [x] Perbarui `docs/USER_GUIDE.md` dengan panduan logging debug.

---

## [x] FASE 7: Penguatan & Perbaikan OCI Telemetry Layer
- [x] **7.1 Perbaikan Namespace OCI Monitoring API**:
  - [x] Tambahkan parameter wajib `namespace="oci_computeagent"` pada `SummarizeMetricsDataDetails` di `src/oci_services/monitoring.py`.
  - [x] Perbaiki penolakan HTTP 400 `InvalidParameter: namespace cannot be null` dari OCI Telemetry endpoint.
- [x] **7.2 Pengujian Unit & Validasi Payload**:
  - [x] Tambahkan assertion eksplisit pada mock monitoring client untuk memvalidasi atribut `namespace`.
  - [x] Tambahkan unit test `test_get_cpu_history` di `tests/test_oci_services.py`.

---

## [x] FASE 8: Siklus Hidup & Sinkronisasi Kesegaran Data Startup (Catch-Up Sync)
- [x] **8.1 Persistensi Timestamp Siklus Polling**:
  - [x] Tambahkan pencatatan `last_poll_metrics_at` ke tabel `bot_settings` di `src/scheduler/tasks.py`.
  - [x] Tambahkan pencatatan `last_poll_billing_at` ke tabel `bot_settings` di `src/scheduler/tasks.py`.
- [x] **8.2 Evaluasi Usia Data Database & Catch-Up Poller**:
  - [x] Buat fungsi normalisasi timezone `_ensure_utc()` untuk mencegah `TypeError` selisih waktu naive SQLite.
  - [x] Buat method `get_latest_metrics_timestamp()` dan `get_latest_billing_timestamp()` di `SchedulerManager`.
  - [x] Buat method `check_and_sync_on_startup()` di `src/scheduler/manager.py` untuk memicu polling catch-up paralel instan jika data kosong atau usang ($\ge$ interval).
- [x] **8.3 Integrasi ke Runner Utama**:
  - [x] Hubungkan `await scheduler_mgr.check_and_sync_on_startup()` di `src/main.py` sebelum `application.start_polling()`.
- [x] **8.4 Unit Testing Komprehensif**:
  - [x] Buat 4 unit test di `tests/test_scheduler.py` (empty DB, stale data, fresh data, timezone-safe).
