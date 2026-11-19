# HANDOFF.md - Working Memory & Session Handover

Catatan estafet untuk AI Agent / developer yang melanjutkan pengerjaan proyek `oci-bot`.

---

## 1. Status Proyek Saat Ini
- **Status Proyek**: **SELESAI PENUH (Fase 1 s/d Fase 12 Berhasil 100% + Centralized User Guide)**.
- **Hasil Pengujian**: **76/76 Unit Test PASSED** (1.42s) & Mypy Static Type Checking **0 issues** (32 source files).
- **Observabilitas (Fase 6)**: `RotatingFileHandler` kondisional (`LOG_LEVEL = DEBUG`) aktif ke `logs/oci_bot.log` (rotasi 5MB, 3 backup), zero file I/O di tingkat INFO.
- **Perbaikan OCI Telemetry (Fase 7)**: Penambahan parameter wajib `namespace="oci_computeagent"` pada OCI Monitoring client, menyelesaikan HTTP 400 `InvalidParameter: namespace cannot be null`.
- **Startup Data Freshness (Fase 8)**: Pengecekan otomatis saat start aplikasi (`check_and_sync_on_startup()`). Jika database kosong atau data lebih lama dari interval, dilakukan polling catch-up paralel secara instan via `asyncio.gather`.
- **Resolusi Batas Callback & Error Handler (Fase 9)**: Pemendekan identifier deterministik SHA-256 12-karakter (`short_id`) pada model database, inline keyboard, dan router callback Telegram, menjamin seluruh `callback_data` $\le 35$ bytes (jauh di bawah batas 64 byte Telegram dan mengeliminasi error `Button_data_invalid`). Registrasi `global_error_handler` terpusat pada `Application` untuk menangkap unhandled exceptions.
- **Presisi Waktu OCI Usage API (Fase 10)**: Normalisasi presisi waktu `time_usage_started` dan `time_usage_ended` (awal bulan berikutnya tepat pukul 00:00:00 UTC) pada query OCI Usage API `RequestSummarizedUsagesDetails`, menyelesaikan penolakan HTTP 400 `InvalidParameter: Passed UTC date does not have the right precision` dan memastikan tagihan riil akun PAYG teragregasi dengan benar.
- **CI/CD GitHub Actions & GHCR (Fase 11)**: Workflow otomatis `.github/workflows/docker-publish.yml` untuk pengujian otomatis (pytest + mypy) dan build multi-arch Docker image (`linux/amd64` dan `linux/arm64` OCI Ampere) yang diunggah ke GitHub Container Registry (`ghcr.io/wawans/oci-monitoring-bot:latest`). Deployment di server kini dapat langsung via `docker compose pull && docker compose up -d`.
- **CI/CD Hardening & Dependencies Resolution (Fase 12)**: Pemisahan dependensi development di `requirements-dev.txt` (`mypy>=1.10.0`, `types-PyYAML>=6.0.0`) untuk menjaga image produksi tetap ramping, serta penyesuaian job `test` di GitHub Actions guna menyelesaikan `mypy: command not found (exit code 127)`.
- **Dokumentasi Terpusat**: `docs/USER_GUIDE.md` (Buku Panduan Pengguna lengkap: Kredensial OCI, Setup Telegram Bot, Konfigurasi Proyek, Operasional & Kontrol Daya, Deployment via GHCR, FAQ).
- **Git State**: Seluruh fase (Fase 1–12) telah diselesaikan dengan branch-per-task dan di-merge ke `main` dengan `--no-ff`. Seluruh task pada `TASK.md` telah berstatus `[x]`.

---

## 2. Rangkuman Deliverables Seluruh Fase

### Fase 1: Environment, Konfigurasi & Basis Data SQLite WAL
- `requirements.txt`: Dependensi OCI SDK, python-telegram-bot, APScheduler, SQLAlchemy async, aiosqlite, Pydantic, Matplotlib, pytest.
- `.env.example` & `config/settings.py`: Manajemen variabel environment terpusat via Pydantic Settings.
- `config/accounts.yaml.example` & `config/parser.py`: Parser deklaratif multi-akun OCI (PAYG & Free Tier) dengan validasi kunci `.pem`.
- `src/database/models.py` & `src/database/connection.py`: Skema ORM SQLAlchemy 2.0 (`Account`, `InstanceState`, `MetricsLog`, `BillingSnapshot`, `AuditLog`, `BotSetting`) dengan otomatisasi SQLite WAL mode.

### Fase 2: OCI Multi-Account Service Layer
- `src/oci_services/client_factory.py`: Client bundle in-memory per akun dengan *fault isolation* dan async handshake verification saat startup.
- `src/oci_services/compute.py`: Discovery compute instances, resolusi Public/Private IP via VNIC attachments (ADR-004), dan kontrol daya (`START`, `STOP`, `SOFTRESET`) dengan `ComputeActionError`.
- `src/oci_services/monitoring.py`: Query MQL utilisasi CPU 5–15 menit via `oci_computeagent` & time-series extraction.
- `src/oci_services/billing.py`: Query MTD spend via `UsageapiClient`, algoritma run-rate linear cost forecast (ADR-003), budget breach alert, dan *graceful fallback* Free Tier ($0.00).

### Fase 3: Background Scheduler & Silent Incident Watchdog
- `src/scheduler/detector.py`: Logika Silent Watchdog (ADR-002) mendeteksi pemadaman mendadak (`VM_DOWN`), CPU spike > 85% selama 2 siklus berurutan (`HIGH_CPU_SPIKE`), pelanggaran budget PAYG (`BUDGET_EXCEEDED`), dan pemulihan (`VM_RECOVERED`, `HIGH_CPU_RESOLVED`).
- `src/scheduler/tasks.py`: Background tasks periodik untuk status/CPU dan billing snapshot dengan fault isolation per akun.
- `src/scheduler/manager.py`: Orkestrasi `APScheduler` dengan *runtime dynamic rescheduling* (ADR-006) untuk interval 5/10/30m dan 3/6/12h tanpa restart.

### Fase 4: Telegram Bot UI, Handlers & Chart Generator
- `src/bot/middleware.py`: Whitelist authentication decorator `@admin_only` (`TELEGRAM_ADMIN_USER_ID`).
- `src/bot/formatters.py`: Template HTML terformat rapi dengan emoji status (🟢/🔴/🟡/⚪).
- `src/bot/keyboards.py`: Inline keyboards interaktif dan dialog konfirmasi dua langkah (`[✅ Ya, Lanjutkan]` / `[❌ Batalkan]`) (ADR-007).
- `src/bot/charts.py`: Visualisasi time-series grafik garis CPU via Matplotlib headless `Agg` ke PNG in-memory `io.BytesIO`.
- `src/bot/handlers.py`: Command handlers (`/start`, `/help`, `/status`, `/instances`, `/billing`, `/settings`), callback query router, audit logger ke `AUDIT_LOG`, dan push alert dispatcher ke DM Admin.
- `src/main.py`: Entrypoint terpadu dengan graceful shutdown handling.

### Fase 5: Hardening, Dockerization & Panduan Operasional
- `Dockerfile`: Hardened image berbasis Python 3.11 slim, menjalankan aplikasi dengan unprivileged non-root user `appuser`.
- `docker-compose.yml`: Orkestrasi container production dengan persistent volume mounting untuk `data/` dan `credentials/keys/`.
- `.dockerignore`: Proteksi menyeluruh dari data sensitif, database lokal, dan file cache saat build context.
- `README.md`: Panduan komprehensif mulai dari setup lokal, setup OCI API keys, deployment Docker Compose, hingga manual bot.

### Fase 6: Observabilitas & Conditional Rotating File Logging
- `src/logging_config.py`: Pengaturan logging terpadu dengan `setup_logging()`. Mengaktifkan `RotatingFileHandler` ke `logs/oci_bot.log` hanya jika `LOG_LEVEL = DEBUG` (5MB per file, 3 backups) dengan format rinci nama berkas & nomor baris. Zero disk file I/O pada mode `INFO`/`WARNING`/`ERROR`.
- `config/settings.py` & `.env.example`: Konfigurasi deklaratif untuk `LOG_LEVEL`, `LOG_FILE_PATH`, `LOG_FILE_MAX_BYTES`, dan `LOG_FILE_BACKUP_COUNT`.
- `Dockerfile` & `docker-compose.yml`: Persiapan direktori `/app/logs` dan volume mount `./logs:/app/logs`.
- `tests/test_logging.py`: 5 unit test komprehensif untuk pengujian kondisional dan rotasi berkas.

### Fase 7: Penguatan & Perbaikan OCI Telemetry Layer
- `src/oci_services/monitoring.py`: Penambahan parameter wajib `namespace="oci_computeagent"` pada `SummarizeMetricsDataDetails` untuk kueri metrik dan grafik riwayat CPU, menyelesaikan isu penolakan HTTP 400 OCI Telemetry API.
- `tests/test_oci_services.py`: Validasi payload `namespace` dan unit test `test_get_cpu_history`.

### Fase 8: Siklus Hidup & Sinkronisasi Kesegaran Data Startup (Catch-Up Sync)
- `src/scheduler/tasks.py`: Pencatatan otomatis timestamp `last_poll_metrics_at` dan `last_poll_billing_at` ke tabel `bot_settings`.
- `src/scheduler/manager.py`: Fungsi normalisasi timezone `_ensure_utc()`, evaluasi usia data database terhadap interval aktif, dan eksekusi catch-up paralel via `asyncio.gather`.
- `src/main.py`: Integrasi pemanggilan `await scheduler_mgr.check_and_sync_on_startup()` sebelum bot polling dimulai.
- `tests/test_scheduler.py`: 4 unit test komprehensif (empty DB, stale data, fresh data, timezone-safe).

### Fase 9: Resolusi Batas Callback Data Telegram & Global Error Handler
- `src/database/models.py`: Helper `compute_short_id()` menghasilkan hash hex SHA-256 12-karakter dan property `short_id` pada model `InstanceState`.
- `src/bot/keyboards.py`: Pemetaan button `vm_detail:`, `act_prompt:`, `act_exec:`, dan `vm_chart:` menggunakan `short_id`, menjamin seluruh payload callback $\le 35$ bytes (jauh di bawah batas 64 byte Telegram).
- `src/bot/handlers.py`: Helper `get_instance_by_identifier()` yang mendukung dual-lookup (OCID penuh dan 12-karakter short ID), pembaruan router callback query, dan registrasi `global_error_handler` untuk menangkap unhandled exceptions.
- `src/main.py`: Pendaftaran `app.add_error_handler(global_error_handler)` pada inisialisasi aplikasi Telegram bot.
- `tests/test_bot.py`: Penambahan unit test verifikasi batas 64-byte untuk seluruh keyboard dengan real-world long OCID, tes fungsi `get_instance_by_identifier`, `global_error_handler`, dan `callback_router`.

### Fase 10: Presisi Waktu OCI Usage API & Penyempurnaan Billing Aggregator
- `src/oci_services/billing.py`: Perhitungan `start_of_month` dan `end_of_month` (tanggal 1 bulan berikutnya pada 00:00:00 UTC) untuk parameter `time_usage_started` dan `time_usage_ended` pada `RequestSummarizedUsagesDetails`, menjamin presisi waktu UTC bersih tanpa fraksi jam/detik/mikrodetik dan menyelesaikan penolakan HTTP 400 OCI Usage API.
- `tests/test_oci_services.py`: Penambahan assertions validasi UTC zero-hour precision pada payload `RequestSummarizedUsagesDetails` dan unit test rollover akhir tahun `test_payg_billing_december_year_rollover`.

### Fase 11: CI/CD GitHub Actions & GHCR Automated Build Pipeline
- `.github/workflows/docker-publish.yml`: Workflow CI/CD otomatis dengan 2 tahap: Quality Gate (`pytest` + `mypy`) dan Multi-Arch Build & Push (`linux/amd64` dan `linux/arm64`) ke GitHub Container Registry (`ghcr.io/wawans/oci-monitoring-bot`) menggunakan cache GHA.
- `docker-compose.yml`: Penambahan direktif `image: ghcr.io/wawans/oci-monitoring-bot:latest` memungkinkan penarikan image pra-bangun di server produksi via `docker compose pull && docker compose up -d`.
- `README.md` & `docs/USER_GUIDE.md`: Perbaikan URL repositori `git clone https://github.com/wawans/oci-monitoring-bot.git` dan penambahan panduan deployment via GHCR pull.

### Fase 12: CI/CD Pipeline Hardening & Runner Dependencies Resolution
- `requirements-dev.txt`: Pemisahan dependensi development & static analysis (`mypy>=1.10.0`, `types-PyYAML>=6.0.0`) agar image Docker produksi tetap bersih dan ringan.
- `.github/workflows/docker-publish.yml`: Penggunaan `requirements-dev.txt` pada job `test` untuk menyelesaikan error `mypy: command not found (exit code 127)`, serta penambahan variabel `ACTIONS_ALLOW_NODE20_RUNNER: true` untuk meredam deprecation warning Node.js 20.

---

## 3. Panduan Pemeliharaan & Pengembangan Selanjutnya
Jika di masa mendatang ingin menambahkan fitur baru atau perbaikan:
1. **Prinsip Anti-Bloat**: DILARANG menumpuk pekerjaan baru ke dalam fase yang sudah selesai. Setiap pekerjaan baru WAJIB dibuatkan fase/milestone baru berurutan (misal: Fase 13, dst.) secara modular dan terisolasi di `TASK.md` dan `HANDOFF.md`.
2. **Git Branching Per-Task**: Buat feature branch baru dari `main` untuk tiap fase/task yang dikerjakan.
3. **Kepatuhan Guardrails**: Pastikan setiap penambahan kode baru mematuhi seluruh aturan di `AGENTS.md` (type hints lengkap, async first, pathlib.Path, structured logging, 0 print, isolasi error OCI).
4. **Verifikasi Kualitas**: Jalankan automated test suite `pytest tests/ -v` dan `mypy config/ src/ tests/` (wajib 100% PASSED & 0 error) sebelum melakukan merge `--no-ff` ke `main`.
5. **Git Push Remote**: Lakukan push ke remote repository HANYA setelah mendapatkan instruksi eksplisit dari pengguna.
