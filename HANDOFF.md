# HANDOFF.md - Working Memory & Session Handover

Catatan estafet untuk AI Agent / developer yang melanjutkan pengerjaan proyek `oci-bot`.

---

## 1. Status Proyek Saat Ini
- **Status**: **Fase 1 (Environment, Konfigurasi & Basis Data SQLite)** telah selesai 100% dan seluruh 16 unit test berhasil lolos (**PASSED**).
- **Fase Aktif Berikutnya**: **Fase 2 (OCI Multi-Account Service Layer)**.
- **Git State**: Branch `main`. Environment Python 3.14 + `.venv` aktif dengan seluruh dependensi terinstal.

---

## 2. File yang Baru Saja Dibuat pada Fase 1
1. `requirements.txt`: Dependensi OCI SDK, python-telegram-bot, APScheduler, SQLAlchemy (asyncio), aiosqlite, greenlet, Pydantic, pydantic-settings, PyYAML, Matplotlib, pytest, pytest-asyncio.
2. `.env.example`: Template konfigurasi environment variables (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_USER_ID`, `DATABASE_URL`, dll.).
3. `config/settings.py`: Manajemen konfigurasi global asinkron/tervalidasi via `pydantic-settings`.
4. `config/accounts.yaml.example`: Template deklaratif multi-akun OCI (3 akun: PAYG dan Always Free Tier).
5. `config/parser.py`: Parser dan validator akun OCI berbasis Pydantic dengan pemeriksaan eksistensi file `.pem`.
6. `src/database/models.py`: Model ORM SQLAlchemy 2.0 (`Account`, `InstanceState`, `MetricsLog`, `BillingSnapshot`, `AuditLog`, `BotSetting`).
7. `src/database/connection.py`: Engine SQLite async (`aiosqlite`) dengan PRAGMA WAL mode, session factory, fungsi inisialisasi tabel otomatis (`init_db`), pembaca/penyimpan pengaturan dinamis, dan sinkronisasi metadata akun (`sync_accounts_to_db`).
8. `pytest.ini`: Konfigurasi pengujian pytest dan asyncio.
9. `tests/test_config.py` & `tests/test_database.py`: 16 unit test komprehensif menguji parser konfigurasi, validasi schema, operasi database CRUD, foreign key cascade, dan inisialisasi WAL.

---

## 3. Langkah Persis Selanjutnya (Immediate Next Steps)
Bagi AI Agent yang melanjutkan pengerjaan ke **Fase 2 (OCI Multi-Account Service Layer)**:
1. Eksekusi **Sub-task 2.1 (OCI Client Factory)**:
   - Buat `src/oci_services/client_factory.py` untuk menginisialisasi client OCI SDK (`ComputeClient`, `VirtualNetworkClient`, `MonitoringClient`, `UsageapiClient`) per akun dari konfigurasi in-memory.
   - Tambahkan fungsi validasi autentikasi / handshake kredensial saat startup.
2. Eksekusi **Sub-task 2.2 (Compute & IP Resolution Service)**:
   - Buat `src/oci_services/compute.py`:
     - `list_instances()`: Ambil daftar instance per compartment.
     - Resolusi IP: Ambil VNIC attachment dan ekstrak Public IP serta Private IP.
     - `execute_action()`: Kontrol daya (`START`, `STOP`, `SOFTRESET`).
3. Eksekusi **Sub-task 2.3 (Monitoring / Telemetry Service)**:
   - Buat `src/oci_services/monitoring.py`: Query MQL utilisasi CPU 5–15 menit terakhir dari namespace `oci_computeagent`.
4. Eksekusi **Sub-task 2.4 (Billing & Forecast Service)**:
   - Buat `src/oci_services/billing.py`: Ambil akumulasi MTD spend via `UsageapiClient`, hitung linear run-rate forecast, dan tangani graceful fallback Free Tier ($0.00 tanpa crash).
5. Eksekusi **Sub-task 2.5 (Unit Test Fase 2)**:
   - Buat `tests/test_oci_services.py` menggunakan mock OCI SDK responses.
