# OCI Multi-Account Telegram Monitoring Bot - Technical Specification

Dokumen spesifikasi arsitektur dan cetak biru teknis permanen (*Single Source of Truth*) untuk aplikasi **Telegram Bot Monitoring Multi-Akun Oracle Cloud Infrastructure (OCI)**.

---

## 1. Overview & Objective

Membangun aplikasi backend Python asinkron yang berfungsi sebagai:
1. **Interactive Telegram Bot**: Antarmuka kontrol dan pemantauan terpusat untuk **3 hingga 10 akun OCI** (kombinasi akun PAYG dan Always Free/Trial).
2. **Silent Incident Watchdog**: Background worker otonom yang memantau kesehatan compute instance dan akumulasi biaya secara periodik, tetapi **hanya mengirimkan push alert ke DM Admin jika terdeteksi insiden/anomali**.

---

## 2. Core Functional Requirements

### 2.1 Multi-Account Management (3–10 Akun)
- Mendukung isolasi konfigurasi per akun:
  - Tenancy OCID, User OCID, Fingerprint, Region, Compartment OCID.
  - Tipe Akun: `PAYG` vs `FREE_TIER` (Always Free / Trial).
  - Target `monthly_budget` (USD) per akun untuk alert pengeluaran.
- Kredensial disimpan dalam format deklaratif: `config/accounts.yaml` dengan file kunci privat `credentials/keys/*.pem`.
- Otomatis melakukan sinkronisasi metadata akun ke database SQLite (`ACCOUNTS` table) saat startup.

### 2.2 Periodic Health & Metrics Polling (Interval 5 / 10 / 30 Menit)
- **Status Lifecycle**: Polling status VM (`RUNNING`, `STOPPED`, `TERMINATING`, dll.) via `oci.core.ComputeClient`.
- **IP Address Resolution**: Mendapatkan **Public IP** dan **Private IP** dari VNIC attachments (`oci.core.VirtualNetworkClient`) dan menyimpannya di cache database.
- **Telemetry Query**: Mengambil utilisasi rata-rata CPU (%) via `oci.monitoring.MonitoringClient` (namespace `oci_computeagent`).
- **Silent Watchdog Rule**:
  - Jika seluruh VM berjalan normal dan CPU wajar, bot **tidak mengirim pesan apa pun** ke chat (hanya memperbarui SQLite).
  - Jika VM mati mendadak (`STOPPED` tak terduga) atau CPU `> 85%` selama 2 siklus berurutan, bot langsung mengirim **Push Alert** ke DM Admin Telegram.
  - Mengirim notifikasi **Recovery** jika instance kembali ke status `RUNNING`.

### 2.3 Interactive Compute Control & Security
- Perintah `/instances` menampilkan daftar VM interaktif (dengan Public IP, Region, status, CPU).
- Kontrol daya: `START`, `STOP`, dan `REBOOT` instance.
- **Two-Step Confirmation**: Wajib melalui dialog konfirmasi Inline Keyboard (`[✅ Ya, Lanjutkan]` / `[❌ Batalkan]`) sebelum aksi dikirim ke API OCI.
- Setiap aksi dicatat ke tabel `AUDIT_LOG`.

### 2.4 Billing, Cost Tracking & Linear Forecast (Interval 3 / 6 / 12 Jam)
- Mengambil akumulasi pengeluaran bulan berjalan (**Month-to-Date / MTD**) via `oci.usage_api.UsageapiClient`.
- **Linear Forecast**: Menghitung proyeksi pengeluaran hingga akhir bulan kalender:
  $$\text{Forecast} = \left(\frac{\text{Biaya Aktual (MTD)}}{\text{Hari Berjalan}}\right) \times \text{Total Hari Bulan Ini}$$
- **Free Tier Graceful Fallback**: Menangani akun Free Tier / Trial yang tidak memiliki riwayat tagihan atau memicu error `NotAuthorizedOrNotFound` secara elegan (menampilkan $0.00 tanpa error/crash).
- **Budget Exceeded Alert**: Mengirim push alert jika estimasi forecast akun PAYG melampaui `monthly_budget`.

### 2.5 Telegram UX & On-Demand Chart
- Whitelist ketat: Bot hanya merespons Telegram User ID yang terdaftar di `TELEGRAM_ADMIN_USER_ID`.
- Format pesan rapi berbasis HTML/Markdown dengan status emoji (🟢/🔴/🟡).
- Tombol `[📈 Lihat Grafik]` untuk membuat chart garis PNG (Matplotlib) utilisasi CPU 6–24 jam terakhir secara on-demand.
- Perintah `/settings` untuk mengubah interval polling (5/10/30m dan 3/6/12h) secara langsung tanpa restart aplikasi.

---

## 3. System Architecture & Component Diagram

```mermaid
flowchart TD
    subgraph TelegramClient ["Telegram App (Admin Personal DM)"]
        Admin["Admin User"]
    end

    subgraph BotApp ["Application Container (Docker / Python 3.11+)"]
        subgraph TelegramRouter ["Telegram Layer"]
            AuthMid["Admin Whitelist Middleware"]
            Dispatcher["Command & Callback Router"]
            Keyboards["Inline Keyboards (Menu & Confirm)"]
            ChartEngine["Matplotlib PNG Chart Engine"]
        end

        subgraph BackgroundDaemon ["Scheduler & Watchdog Daemon"]
            Scheduler["APScheduler (AsyncIOScheduler)"]
            MetricsPoller["Metrics Poller (5/10/30m)"]
            BillingPoller["Cost Poller (3/6/12h)"]
            IncidentDetector{"Incident Detector"}
        end

        subgraph OCIEngine ["OCI Integration Engine"]
            ClientFactory["Multi-Account Client Factory"]
            ComputeSvc["Compute & VNIC Service"]
            MonitoringSvc["Telemetry Service"]
            BillingSvc["Usage & Forecast Service"]
        end

        subgraph Storage ["Persistence"]
            DB[("SQLite WAL Database\n- ACCOUNTS\n- INSTANCE_STATE\n- METRICS_LOG\n- BILLING_SNAPSHOT\n- AUDIT_LOG\n- BOT_SETTINGS")]
            YAMLConfig["config/accounts.yaml"]
            Keys["credentials/keys/*.pem"]
        end
    end

    subgraph OCICloud ["Oracle Cloud Tenancies"]
        Acc1["Account 1: PAYG (e.g. ap-singapore-1)"]
        Acc2["Account 2: Always Free (e.g. ap-tokyo-1)"]
        AccN["Account N: Always Free / Trial"]
    end

    Admin <-->|DM / Commands / Callbacks| AuthMid
    AuthMid --> Dispatcher
    Dispatcher --> Keyboards & ChartEngine & ComputeSvc & DB

    Scheduler --> MetricsPoller & BillingPoller
    MetricsPoller --> ComputeSvc & MonitoringSvc
    BillingPoller --> BillingSvc
    ComputeSvc & MonitoringSvc & BillingSvc --> OCICloud

    YAMLConfig & Keys --> ClientFactory
    ClientFactory -.-> ComputeSvc & MonitoringSvc & BillingSvc

    MetricsPoller --> IncidentDetector
    BillingPoller --> IncidentDetector
    IncidentDetector -->|Catat Histori| DB
    IncidentDetector -->|🚨 Push Alert HANYA Jika Insiden| Admin
```

---

## 4. Database Schema (SQLite WAL Mode)

```mermaid
erDiagram
    ACCOUNTS {
        string account_id PK "e.g. acc_01"
        string name "Display name"
        string account_type "PAYG | FREE_TIER"
        string region "e.g. ap-singapore-1"
        string tenancy_ocid
        string compartment_id
        float monthly_budget
        boolean is_active
        datetime created_at
    }
    INSTANCE_STATE {
        string instance_id PK "Instance OCID"
        string account_id FK
        string region
        string compartment_id
        string display_name
        string shape
        string public_ip "Extracted from VNIC"
        string private_ip "Extracted from VNIC"
        string lifecycle_state "RUNNING | STOPPED | etc."
        float latest_cpu_percent
        int consecutive_high_cpu
        datetime last_seen
    }
    METRICS_LOG {
        int id PK
        string instance_id FK
        float cpu_percent
        datetime timestamp
    }
    BILLING_SNAPSHOT {
        int id PK
        string account_id FK
        float amount
        string currency
        string billing_period "e.g. 2026-11"
        datetime recorded_at
    }
    AUDIT_LOG {
        int id PK
        int user_id
        string account_id
        string instance_id
        string action "START | STOP | REBOOT"
        string status "SUCCESS | FAILED"
        datetime timestamp
    }
    BOT_SETTINGS {
        string key PK "e.g. poll_metrics_interval"
        string value
        datetime updated_at
    }

    ACCOUNTS ||--o{ INSTANCE_STATE : "owns"
    ACCOUNTS ||--o{ BILLING_SNAPSHOT : "has"
    INSTANCE_STATE ||--o{ METRICS_LOG : "has history"
```

---

## 5. Technical Stack

- **Runtime**: Python 3.11+
- **OCI SDK**: `oci>=2.120.0`
- **Telegram Bot Framework**: `python-telegram-bot>=21.0` (asyncio native)
- **Background Scheduler**: `APScheduler>=3.10.4` (`AsyncIOScheduler`)
- **Database ORM**: `SQLAlchemy>=2.0.0` + `aiosqlite>=0.20.0` (SQLite with WAL mode)
- **Data Modeling & Config**: `pydantic>=2.6.0`, `pydantic-settings>=2.2.0`, `PyYAML>=6.0`
- **Visualization**: `matplotlib>=3.8.0` (headless backend `Agg`)
- **Containerization**: Docker & Docker Compose
