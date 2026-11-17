# HANDOFF.md - Working Memory & Session Handover

Catatan estafet untuk AI Agent / developer yang melanjutkan pengerjaan proyek `oci-bot`.

---

## 1. Status Proyek Saat Ini
- **Status Proyek**: **SELESAI PENUH (Fase 1 s/d Fase 5 Berhasil 100%)**.
- **Hasil Pengujian**: **61/61 Unit Test PASSED** (1.28s) & Mypy Static Type Checking **0 issues** (30 source files).
- **Git State**: Branch `feat/phase-5-docker-hardening` siap di-merge ke `main`. Seluruh task pada `TASK.md` telah berstatus `[x]`.

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

---

## 3. Panduan Pemeliharaan & Pengembangan Selanjutnya
Jika di masa mendatang ingin menambahkan fitur baru:
1. Buat feature branch baru dari `main`.
2. Pastikan setiap penambahan kode baru mematuhi konvensi di `AGENTS.md` (type hints lengkap, async first, pathlib.Path, structured logging, 0 print).
3. Jalankan automated test suite `pytest tests/ -v` dan `mypy config/ src/ tests/` sebelum melakukan merge ke `main`.
