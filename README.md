# OCI Multi-Account Telegram Monitoring Bot

Aplikasi monitoring dan otomasi kontrol terpusat untuk multi-akun **Oracle Cloud Infrastructure (OCI)** berbasis Python 3.11+ dan **Telegram Bot**. Dirancang untuk mengelola **3 hingga 10 akun OCI** (kombinasi akun Pay-As-You-Go dan Always Free/Trial) secara terpusat dengan mekanisme **Silent Incident Watchdog**, kendali daya VM dua langkah yang aman (Two-Step Confirmation), visualisasi metrik performa time-series on-demand, dan proyeksi tagihan bulanan (*cost forecast*).

---

## ✨ Fitur Utama

- 🏢 **Multi-Account OCI (3–10 Akun)**: Kelola dan pantau banyak tenancy OCI sekaligus (PAYG, Always Free, Trial) dalam satu antarmuka Telegram terpadu dengan isolasi kegagalan per akun (*fault isolation*).
- 🌐 **Resolusi IP Publik & Privat**: Mengambil Public IP dan Private IP dari VNIC attachment secara otomatis dan menyimpannya di cache basis data SQLite lokal.
- 🔕 **Silent Incident Watchdog**: Polling berkala di latar belakang tanpa spam chat. Push notifikasi ke DM Admin **hanya dikirim jika ada insiden** (VM mati mendadak, beban CPU > 85% selama 2 siklus berurutan, budget bulanan terlampaui, atau pemulihan status).
- ⚡ **Kontrol Daya VM Aman**: Start, Stop, dan Reboot compute instance langsung dari Telegram dengan **konfirmasi dua langkah (two-step confirmation keyboard)** untuk mencegah kesalahan operasional.
- 📈 **Visualisasi Metrik & Grafik On-Demand**: Render grafik garis time-series PNG utilisasi CPU 6–24 jam terakhir secara on-demand via Matplotlib headless (`Agg`) ke in-memory buffer.
- 💳 **Billing & Cost Forecast**: Pantau akumulasi biaya bulan berjalan (MTD) dan proyeksi estimasi tagihan akhir bulan berbasis *linear run-rate* dengan *graceful fallback* untuk akun Free Tier / ServiceError ($0.00 tanpa error).
- ⏱️ **Pengaturan Interval Dinamis**: Ubah interval polling status VM (5/10/30 menit) dan billing (3/6/12 jam) secara langsung melalui `/settings` tanpa perlu me-restart aplikasi (ADR-006).
- 🔒 **Aman & Terisolasi**: Whitelist Telegram User ID ketat, proteksi kunci privat `.pem` lokal (`chmod 600`), dan pencatatan audit log lengkap di SQLite.
- 🐳 **Siap Docker**: Dilengkapi `Dockerfile` berbasis Python 3.11 slim (non-root unprivileged user) dan `docker-compose.yml` dengan volume mounting persisten.

---

## 📁 Struktur Direktori

```
oci-monitoring-bot/
├── config/                   # Konfigurasi aplikasi & parser YAML
│   ├── __init__.py
│   ├── settings.py           # Validasi .env via Pydantic Settings
│   ├── accounts.yaml.example # Template deklaratif daftar akun OCI
│   ├── accounts.yaml         # File konfigurasi akun aktual (git-ignored)
│   └── parser.py             # Parser & validator schema akun OCI
├── credentials/
│   └── keys/                 # Tempat menyimpan private key .pem OCI (git-ignored)
├── src/
│   ├── __init__.py
│   ├── main.py               # Entrypoint & runner aplikasi terpadu
│   ├── database/             # SQLite async WAL connection & SQLAlchemy ORM models
│   ├── oci_services/         # Client factory, Compute, Network, Monitoring, & Billing
│   ├── scheduler/            # APScheduler manager, polling tasks, & incident detector
│   └── bot/                  # Telegram middleware, formatters, keyboards, charts, & handlers
├── docs/
│   └── SPEC.md               # Master technical specification & cetak biru arsitektur
├── tests/                    # 61+ automated unit & integration tests
├── AGENTS.md                 # Konstitusi coding & guardrails operasional
├── DECISIONS.md              # Architecture Decision Records (ADR-001 s/d ADR-007)
├── TASK.md                   # Checklist granular roadmap & progres implementasi
├── HANDOFF.md                # Catatan estafet pengerjaan antar-sesi
├── TROUBLESHOOTING.md        # Basis pengetahuan isu teknis & solusi edge-case
├── Dockerfile                # Production Docker image (Python 3.11-slim, non-root)
├── docker-compose.yml        # Orkestrasi Docker Compose dengan volume mounting
├── requirements.txt          # Dependensi Python
├── pytest.ini                # Konfigurasi automated testing
├── mypy.ini                  # Konfigurasi static type checking
└── README.md                 # Dokumentasi utama proyek
```

---

## 🚀 Panduan Ringkas Memulai (Quick Start)

### 1. Prasyarat Sistem
- Python 3.11+
- Token Telegram Bot dari [@BotFather](https://t.me/BotFather)
- Numeric Telegram User ID Anda dari [@userinfobot](https://t.me/userinfobot)
- Kredensial API OCI (Tenancy OCID, User OCID, Fingerprint, Region, dan file kunci `.pem`)

---

### 2. Setup Lingkungan Lokal

```bash
# 1. Kloning repositori
git clone <url-repo-anda>
cd oci-monitoring-bot

# 2. Buat dan aktifkan virtual environment
python3 -m venv .venv
source .venv/bin/activate  # Di Windows: .venv\Scripts\activate

# 3. Instal dependensi
pip install -r requirements.txt
```

---

### 3. Konfigurasi Kredensial

#### A. File `.env`
Salin template `.env.example`:
```bash
cp .env.example .env
```
Sesuaikan nilainya di `.env`:
```env
TELEGRAM_BOT_TOKEN="1234567890:ABCDefGhIJKlmNoPQRsTUVwxyZ"
TELEGRAM_ADMIN_USER_ID=123456789
DATABASE_URL="sqlite+aiosqlite:///data/oci_bot.db"
ACCOUNTS_CONFIG_PATH="config/accounts.yaml"
LOG_LEVEL="INFO"
DEFAULT_METRICS_INTERVAL_MINUTES=10
DEFAULT_BILLING_INTERVAL_HOURS=6
```

#### B. Kunci Privat OCI & `config/accounts.yaml`
1. Letakkan file `.pem` API Key OCI di dalam `credentials/keys/`:
   ```bash
   cp /path/ke/key_anda.pem credentials/keys/acc_01.pem
   chmod 600 credentials/keys/*.pem
   ```
2. Salin template konfigurasi akun:
   ```bash
   cp config/accounts.yaml.example config/accounts.yaml
   ```
3. Edit `config/accounts.yaml` dengan Tenancy OCID, User OCID, Fingerprint, dan path kunci privat:
   ```yaml
   accounts:
     - account_id: "acc_01"
       name: "Production (Singapore PAYG)"
       account_type: "PAYG"
       tenancy_ocid: "ocid1.tenancy.oc1..aaaaaaaexample"
       user_ocid: "ocid1.user.oc1..aaaaaaaexample"
       fingerprint: "20:3b:97:13:55:1c:11:0d:43:dc:14:28:b5:12:34:56"
       key_file: "credentials/keys/acc_01.pem"
       region: "ap-singapore-1"
       compartment_id: "ocid1.tenancy.oc1..aaaaaaaexample"
       monthly_budget: 75.0
       is_active: true
   ```

---

### 4. Menjalankan Aplikasi

#### Cara 1: Menjalankan Langsung via Python
```bash
source .venv/bin/activate
python -m src.main
```

#### Cara 2: Menjalankan via Docker Compose (Rekomendasi Production 24/7)
```bash
# Build dan jalankan container di latar belakang
docker compose up -d

# Periksa log aplikasi
docker compose logs -f oci-bot

# Menghentikan container
docker compose down
```

---

### 5. Menjalankan Pengujian (Unit Tests & Type Checking)

Seluruh komponen telah dilengkapi unit test komprehensif:
```bash
source .venv/bin/activate

# Menjalankan 61 unit test
pytest tests/ -v

# Menjalankan pemeriksaan tipe statis
mypy config/ src/ tests/
```

---

## 🤖 Daftar Perintah Telegram Bot

| Perintah | Deskripsi |
| :--- | :--- |
| `/start` | Memulai interaksi dengan bot dan menampilkan tombol navigasi utama |
| `/help` | Menampilkan panduan komprehensif dan daftar fitur bot |
| `/status` | Ikhtisar global status kesehatan seluruh akun dan VM |
| `/instances` | Navigasi interaktif daftar instance, Public IP, kontrol daya, dan grafik |
| `/billing` | Rekapitulasi MTD spend aktual, proyeksi run-rate forecast, dan status budget |
| `/settings` | Menu interaktif untuk mengubah interval polling metrik (5/10/30m) dan billing (3/6/12h) |

---

## 🔔 Aturan Silent Incident Watchdog

Bot tidak akan mengirim spam pesan berkala saat kondisi normal. Push Alert hanya dikirim ke DM Admin jika:
- 🚨 **VM Mati Mendadak**: Instance yang sebelumnya berstatus `RUNNING` berubah menjadi `STOPPED` atau `CRITICAL`.
- ⚠️ **CPU Spike**: Utilisasi CPU melampaui `85%` selama 2 siklus pemantauan berurutan.
- 💸 **Budget Terlampaui**: Proyeksi pengeluaran linear akhir bulan pada akun PAYG melampaui `monthly_budget`.
- ✅ **Pemulihan**: Instance kembali berstatus `RUNNING` atau CPU kembali normal.

---

## 📄 Lisensi
Didistribusikan di bawah lisensi MIT.
