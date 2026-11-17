# HANDOFF.md - Working Memory & Session Handover

Catatan estafet untuk AI Agent / developer yang melanjutkan pengerjaan proyek `oci-bot`.

---

## 1. Status Proyek Saat Ini
- **Status**: **Fase 4 (Telegram Bot UI, Handlers & Chart Generator)** telah selesai 100% dan seluruh 61 unit test berhasil lolos (**PASSED**). Mypy static type checking 0 issues (30 source files).
- **Fase Aktif Berikutnya**: **Fase 5 (Hardening, Dockerization & Panduan Operasional)**.
- **Git State**: Branch `feat/phase-4-telegram-bot` siap di-merge ke `main`.

---

## 2. File yang Baru Saja Dibuat pada Fase 4
1. `src/bot/middleware.py`:
   - `@admin_only`: Security middleware decorator membatasi akses bot secara eksklusif ke `TELEGRAM_ADMIN_USER_ID`.
   - `is_admin()` helper function.
2. `src/bot/formatters.py`:
   - Template pesan HTML dengan status emoji (🟢/🔴/🟡/⚪).
   - Formatters untuk `/status`, `/instances`, `/billing`, dialog konfirmasi daya dua langkah (ADR-007), hasil aksi, dan menu interval pengaturan polling.
3. `src/bot/keyboards.py`:
   - `get_main_menu_keyboard()`: Tombol menu navigasi utama.
   - `get_instances_keyboard()`: Tombol daftar instance VM interaktif.
   - `get_instance_actions_keyboard()`: Tombol daya kontekstual (Start/Stop/Reboot) & grafik.
   - `get_action_confirm_keyboard()`: Dialog konfirmasi dua langkah (`[✅ Ya, Lanjutkan Eksekusi]` / `[❌ Batalkan]`) (ADR-007).
   - `get_settings_keyboard()`: Tombol interval metrik (5/10/30m) & billing (3/6/12h) dengan indikator aktif `✅`.
4. `src/bot/charts.py`:
   - `generate_cpu_chart()`: Engine visualisasi headless Matplotlib (`Agg`) merender grafik garis utilisasi CPU time-series dengan batas ambang watchdog 85% ke buffer PNG in-memory `io.BytesIO`.
5. `src/bot/handlers.py`:
   - Handlers `/start`, `/help`, `/status`, `/instances`, `/billing`, `/settings`.
   - Router callback query (`callback_router`) untuk seluruh navigasi, pergantian interval, eksekusi kontrol daya OCI, dan audit logging ke tabel `AUDIT_LOG`.
   - `dispatch_incident_push_alert()`: Pengirim notifikasi insiden real-time ke DM Admin Telegram (ADR-002).
6. `src/main.py`:
   - Application runner terpadu mengintegrasikan inisialisasi basis data SQLite WAL, loader akun OCI, OCI client factory & service layer, dynamic scheduler manager, watchdog incident alert dispatcher, dan bot polling Telegram dengan graceful shutdown signal handling.
7. `tests/test_charts.py` & `tests/test_bot.py`:
   - 16 unit test komprehensif menguji generator chart PNG, template HTML formatters, keyboard builders, admin whitelist security middleware, dan dispatcher push alert. Total test suite mencapai **61/61 PASSED**.

---

## 3. Langkah Persis Selanjutnya (Immediate Next Steps)
Bagi AI Agent yang melanjutkan pengerjaan ke **Fase 5 (Hardening, Dockerization & Panduan Operasional)**:
1. Merge branch `feat/phase-4-telegram-bot` ke `main`.
2. Buat branch baru untuk Fase 5: `git checkout -b feat/phase-5-docker-hardening` dari `main`.
3. Eksekusi **Sub-task 5.1 (Dockerization)**:
   - Buat `Dockerfile` berbasis Python 3.11-slim (multi-stage / lean production image).
   - Buat `docker-compose.yml` dengan volume mounting persisten untuk `data/` dan `credentials/keys/`.
   - Buat `.dockerignore`.
4. Eksekusi **Sub-task 5.2 (Dokumentasi & Pengujian Akhir)**:
   - Perbarui `README.md` dengan panduan operasional lengkap (setup akun OCI, konfigurasi `.env`, menjalankan lokal vs Docker Compose).
   - Jalankan end-to-end full suite verification (`pytest tests/ -v`, `mypy`).
   - Selesaikan seluruh checklist di `TASK.md` dan `HANDOFF.md`.
   - Merge ke branch `main`.
