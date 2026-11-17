# HANDOFF.md - Working Memory & Session Handover

Catatan estafet untuk AI Agent / developer yang melanjutkan pengerjaan proyek `oci-bot`.

---

## 1. Status Proyek Saat Ini
- **Status**: **Fase 2 (OCI Multi-Account Service Layer)** telah selesai 100% dan seluruh 30 unit test berhasil lolos (**PASSED**). Mypy static type checking 0 issues.
- **Fase Aktif Berikutnya**: **Fase 3 (Background Scheduler & Incident Watchdog)**.
- **Git State**: Branch `feat/phase-2-oci-services` siap di-merge ke `main`.

---

## 2. File yang Baru Saja Dibuat pada Fase 2
1. `src/oci_services/client_factory.py`:
   - `OCIClientBundle`: Container client OCI per akun (`ComputeClient`, `VirtualNetworkClient`, `MonitoringClient`, `UsageapiClient`).
   - `OCIClientFactory`: Manajemen inisialisasi client OCI dengan isolasi kegagalan per akun (*fault isolation*) dan asynchronous handshake verification saat startup.
2. `src/oci_services/compute.py`:
   - `ComputeService`: Discovery instance per compartment, resolusi Public & Private IP melalui VNIC attachments (`VirtualNetworkClient`), dan eksekusi kontrol daya (`START`, `STOP`, `SOFTRESET`) dengan `ComputeActionError`. Seluruh pemanggilan synchronous dibungkus `asyncio.to_thread`.
3. `src/oci_services/monitoring.py`:
   - `MonitoringService`: Query MQL utilisasi CPU 5–15 menit terakhir dari namespace `oci_computeagent` (`CpuUtilization[1m]{resourceId = "..."}.mean()`) serta historical datapoints untuk chart render.
4. `src/oci_services/billing.py`:
   - `BillingService`: Query MTD spend via `UsageapiClient`, algoritma proyeksi pengeluaran linear run-rate akhir bulan (ADR-003), flag pelanggaran budget bulanan, dan *graceful fallback* khusus akun Free Tier / ServiceError ($0.00 tanpa error).
5. `mypy.ini`: Konfigurasi strict type checking dengan ignore stubs untuk `oci.*`.
6. `tests/test_oci_services.py`: 14 unit test komprehensif menguji client factory, isolasi error akun, resolusi VNIC IP, kontrol daya, telemetri CPU, formula forecast linear, dan fallback Free Tier.

---

## 3. Langkah Persis Selanjutnya (Immediate Next Steps)
Bagi AI Agent yang melanjutkan pengerjaan ke **Fase 3 (Background Scheduler & Incident Watchdog)**:
1. Buat branch baru untuk Fase 3: `git checkout -b feat/phase-3-scheduler-watchdog` dari `main`.
2. Eksekusi **Sub-task 3.1 (Dynamic Scheduler Manager)**:
   - Buat `src/scheduler/manager.py` menggunakan `APScheduler` (`AsyncIOScheduler`).
   - Implementasikan fungsi reschedule dinamis untuk interval status (5/10/30m) dan billing (3/6/12h).
3. Eksekusi **Sub-task 3.2 (Polling Tasks & State Diff Engine)**:
   - Buat `src/scheduler/tasks.py`:
     - Task periodic status VM & utilisasi CPU.
     - Task periodic akumulasi billing & snapshot.
4. Eksekusi **Sub-task 3.3 (Silent Incident Detector)**:
   - Buat `src/scheduler/detector.py`:
     - Deteksi transisi status tidak terduga (`RUNNING` -> `STOPPED`).
     - Deteksi CPU spike (`> 85%` selama 2 siklus berurutan).
     - Deteksi pelanggaran budget bulanan PAYG.
     - Deteksi pemulihan status (`RUNNING`).
5. Eksekusi **Sub-task 3.4 (Unit Test Fase 3)**:
   - Buat `tests/test_scheduler.py` dan `tests/test_detector.py`.
