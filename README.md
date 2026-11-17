# OCI Multi-Account Telegram Monitoring Bot

Aplikasi monitoring multi-akun **Oracle Cloud Infrastructure (OCI)** berbasis Python dan **Telegram Bot**. Dirancang untuk memantau 3 hingga 10 akun OCI (kombinasi akun Pay-As-You-Go dan Always Free/Trial) secara terpusat dengan mekanisme **Silent Incident Watchdog**, kendali daya VM yang aman, visualisasi metrik performa, dan proyeksi tagihan bulanan (*cost forecast*).

---

## ✨ Fitur Utama

- 🏢 **Multi-Account OCI (3–10 Akun)**: Kelola dan pantau banyak tenancy OCI sekaligus (PAYG, Always Free, Trial) dalam satu antarmuka Telegram.
- 🌐 **Resolusi IP Publik & Privat**: Menampilkan Public IP dan Private IP dari masing-masing compute instance secara instan.
- 🔕 **Silent Incident Watchdog**: Polling berkala di latar belakang tanpa membanjiri chat Anda. Push notifikasi darurat **hanya dikirim jika ada insiden** (VM mati mendadak, beban CPU > 85%, budget terlampaui, atau pemulihan status).
- ⚡ **Kontrol Daya VM Aman**: Start, Stop, dan Reboot compute instance langsung dari Telegram dengan **konfirmasi dua langkah (two-step inline keyboard)** untuk mencegah ketidaksengajaan.
- 📈 **Visualisasi Metrik & Grafik On-Demand**: Teks terformat rapi dengan emoji indikator status (🟢/🔴), serta tombol `[📈 Lihat Grafik]` untuk membuat chart PNG performa CPU beberapa jam terakhir.
- 💳 **Billing & Cost Forecast**: Pantau akumulasi biaya bulan berjalan (MTD) dan proyeksi estimasi tagihan akhir bulan berdasarkan *linear run-rate* dengan dukungan graceful fallback untuk akun Free Tier ($0.00).
- ⏱️ **Pengaturan Interval Dinamis**: Ubah interval polling status VM (5/10/30 menit) dan billing (3/6/12 jam) secara langsung melalui perintah `/settings` tanpa perlu me-restart aplikasi.
- 🔒 **Aman & Terisolasi**: Whitelist Telegram User ID yang ketat, penyimpanan kunci privat `.pem` lokal terproteksi, dan audit log lengkap di SQLite.
- 🐳 **Siap Docker**: Dilengkapi `Dockerfile` dan `docker-compose.yml` untuk deployment 24/7 di VPS atau instance Always Free OCI Anda.

---

## 📁 Struktur Direktori

```
oci-bot/
├── config/                   # Konfigurasi aplikasi & parser YAML
│   ├── settings.py           # Validasi .env via Pydantic
│   ├── accounts.yaml.example # Template daftar 3-10 akun OCI
│   └── accounts.yaml         # File konfigurasi akun aktual (git-ignored)
├── credentials/
│   └── keys/                 # Tempat menyimpan file private key .pem OCI (git-ignored)
├── src/
│   ├── main.py               # Entrypoint aplikasi
│   ├── database/             # SQLite connection (WAL mode) & model SQLAlchemy
│   ├── oci_services/         # Abstraksi OCI SDK (Compute, Network/VNIC, Monitoring, Billing)
│   ├── scheduler/            # APScheduler & Incident Detection Engine
│   └── bot/                  # Telegram Bot application, handlers, keyboards, formatters
├── docs/
│   └── SPEC.md               # Spesifikasi teknis & arsitektur permanen
├── tests/                    # Automated unit & integration tests
├── AGENTS.md                 # Konstitusi coding & guardrails operasional AI
├── DECISIONS.md              # Architecture Decision Records (ADR)
├── TASK.md                   # Checklist progres implementasi per fase
├── HANDOFF.md                # Catatan estafet pengerjaan antar-sesi
├── TROUBLESHOOTING.md        # Basis pengetahuan isu teknis & edge-cases
├── Dockerfile                # Image container Python 3.11
├── docker-compose.yml        # Konfigurasi orkestrasi container
├── requirements.txt          # Dependensi Python
└── README.md                 # Dokumentasi utama proyek
```

---

## 🚀 Panduan Ringkas Memulai (Quick Start)

### 1. Prasyarat
- Python 3.11+
- Token Telegram Bot (didapatkan dari [@BotFather](https://t.me/BotFather))
- ID Pengguna Telegram Anda (didapatkan dari [@userinfobot](https://t.me/userinfobot))
- Kredensial API OCI (Tenancy OCID, User OCID, Fingerprint, dan file private key `.pem`)

### 2. Kloning & Persiapan Virtual Environment
```bash
git clone <url-repo-anda>
cd oci-bot
python -m venv .venv
source .venv/bin/activate  # Di Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Konfigurasi Environment (`.env`)
Salin file `.env.example` menjadi `.env` lalu isi token dan ID Telegram Anda:
```bash
cp .env.example .env
```
Isi `.env`:
```env
TELEGRAM_BOT_TOKEN="123456789:ABCdefGHIjklMNOpqrSTUvwxYZ"
TELEGRAM_ADMIN_USER_ID=123456789
POLL_INTERVAL_METRICS_MINUTES=10
POLL_INTERVAL_BILLING_HOURS=6
```

### 4. Konfigurasi Akun OCI (`config/accounts.yaml`)
1. Letakkan file private key OCI Anda di dalam folder: `credentials/keys/` (misal: `acc_01.pem`, `acc_02.pem`).
2. Buat file `config/accounts.yaml` dari template:
   ```bash
   cp config/accounts.yaml.example config/accounts.yaml
   ```
3. Sesuaikan Tenancy OCID, User OCID, Fingerprint, Region, dan path file `.pem`.

### 5. Menjalankan Aplikasi
```bash
python -m src.main
```
Atau menggunakan Docker Compose:
```bash
docker-compose up -d
```

---

## 🤖 Perintah Telegram Bot

| Perintah | Deskripsi |
| :--- | :--- |
| `/start` | Memulai bot dan menampilkan ringkasan informasi |
| `/help` | Menampilkan panduan penggunaan dan daftar perintah |
| `/status` | Menampilkan ringkasan status cepat seluruh akun dan VM |
| `/instances` | Menampilkan daftar instance interaktif (Start/Stop, Public IP, Detail) |
| `/billing` | Menampilkan rekapitulasi pengeluaran bulan berjalan (MTD) dan forecast |
| `/settings` | Mengubah interval polling status VM dan billing secara interaktif |

---

## 📄 Lisensi
Didistribusikan di bawah lisensi MIT. Silakan gunakan dan sesuaikan sesuai kebutuhan Anda.
