# HANDOFF.md - Working Memory & Session Handover

Catatan estafet untuk AI Agent / developer yang melanjutkan pengerjaan proyek `oci-bot`.

---

## 1. Status Proyek Saat Ini
- **Status**: **Fase 3 (Background Scheduler & Incident Watchdog)** telah selesai 100% dan seluruh 45 unit test berhasil lolos (**PASSED**). Mypy static type checking 0 issues (21 source files).
- **Fase Aktif Berikutnya**: **Fase 4 (Telegram Bot UI, Handlers & Chart Generator)**.
- **Git State**: Branch `feat/phase-3-scheduler-watchdog` siap di-merge ke `main`.

---

## 2. File yang Baru Saja Dibuat pada Fase 3
1. `src/scheduler/detector.py`:
   - `IncidentType` (`VM_DOWN`, `VM_RECOVERED`, `HIGH_CPU_SPIKE`, `HIGH_CPU_RESOLVED`, `BUDGET_EXCEEDED`).
   - `IncidentSeverity` (`CRITICAL`, `WARNING`, `INFO`).
   - `IncidentAlert`: Data payload alert insiden.
   - `IncidentDetector`: Evaluasi transisi lifecycle tak terduga, deteksi lonjakan CPU `> 85%` selama 2 siklus berurutan, deteksi recovery, dan deteksi pelanggaran budget bulanan PAYG.
2. `src/scheduler/tasks.py`:
   - `poll_metrics_task`: Polling status compute VM & utilisasi CPU periodik ke seluruh akun OCI dengan *fault isolation per account*, update cache tabel `INSTANCE_STATE`, histori telemetri `METRICS_LOG`, dan dispatch alert hanya jika terjadi insiden.
   - `poll_billing_task`: Polling periodik pengeluaran MTD & kalkulasi forecast ke seluruh akun, penyimpanan histori `BILLING_SNAPSHOT`, dan dispatch alert jika budget terlampaui.
3. `src/scheduler/manager.py`:
   - `SchedulerManager`: Orkestrasi `APScheduler` (`AsyncIOScheduler`) dengan dukungan *runtime rescheduling* (ADR-006) untuk interval status (5/10/30 menit) dan billing (3/6/12 jam) tanpa restart aplikasi.
4. `src/scheduler/__init__.py`: Package init mengekspos public interface layer scheduler & detector.
5. `mypy.ini`: Konfigurasi strict type checking dengan ignore stubs untuk `apscheduler.*`.
6. `tests/test_detector.py` & `tests/test_scheduler.py`: 15 unit test baru menguji seluruh skenario detector insiden, lifecycle scheduler, dynamic rescheduling, dan polling tasks. Total test suite mencapai **45/45 PASSED**.

---

## 3. Langkah Persis Selanjutnya (Immediate Next Steps)
Bagi AI Agent yang melanjutkan pengerjaan ke **Fase 4 (Telegram Bot UI, Handlers & Chart Generator)**:
1. Merge branch `feat/phase-3-scheduler-watchdog` ke `main`.
2. Buat branch baru untuk Fase 4: `git checkout -b feat/phase-4-telegram-bot` dari `main`.
3. Eksekusi **Sub-task 4.1 (Security Middleware, Formatting & Keyboards)**:
   - Buat `src/bot/middleware.py` untuk validasi whitelist `TELEGRAM_ADMIN_USER_ID`.
   - Buat `src/bot/formatters.py` untuk template pesan HTML dengan emoji status.
   - Buat `src/bot/keyboards.py` untuk Inline Keyboard menu navigasi, list VM, interval settings, dan konfirmasi dua langkah (`[✅ Ya, Lanjutkan]` / `[❌ Batalkan]`) (ADR-007).
4. Eksekusi **Sub-task 4.2 (On-Demand Chart Generator)**:
   - Buat `src/bot/charts.py` untuk render grafik garis PNG utilisasi CPU 6–24 jam via Matplotlib headless (`Agg`) ke in-memory `BytesIO`.
5. Eksekusi **Sub-task 4.3 (Command & Callback Handlers)**:
   - Buat handlers untuk `/start`, `/help`, `/status`, `/instances`, `/billing`, `/settings`, dan callback query tombol interaktif.
   - Audit logging setiap kontrol daya ke `AUDIT_LOG`.
6. Eksekusi **Sub-task 4.4 (Application Runner)**:
   - Buat `src/main.py` menghubungkan router bot, background scheduler, client factory, dan database.
7. Eksekusi **Sub-task 4.5 (Unit Test Fase 4)**:
   - Buat `tests/test_bot.py` dan `tests/test_charts.py`.
