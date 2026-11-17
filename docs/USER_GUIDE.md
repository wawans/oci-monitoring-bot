# Buku Panduan Pengguna (USER_GUIDE.md)
## OCI Multi-Account Telegram Monitoring Bot

Dokumen ini adalah pusat panduan operasional terpadu (*Centralized User Guide*) untuk penyiapan, konfigurasi, pengoperasian, dan pemeliharaan aplikasi **OCI Multi-Account Telegram Monitoring Bot**.

---

## 📑 Daftar Isi

1. [Bab 1: Panduan Kredensial API Oracle Cloud (OCI)](#bab-1-panduan-kredensial-api-oracle-cloud-oci)
   - [1.1 Mengetahui Region Identifier](#11-mengetahui-region-identifier)
   - [1.2 Mengambil Tenancy OCID & Compartment OCID](#12-mengambil-tenancy-ocid--compartment-ocid)
   - [1.3 Mengambil User OCID & Membuat API Key (.pem)](#13-mengambil-user-ocid--membuat-api-key-pem)
   - [1.4 Menata File Kunci Privat & Hak Akses (chmod 600)](#14-menata-file-kunci-privat--hak-akses-chmod-600)
   - [1.5 Menambahkan Akun Tambahan (Multi-Tenancy)](#15-menambahkan-akun-tambahan-multi-tenancy)
2. [Bab 2: Panduan Setup Bot Telegram](#bab-2-panduan-setup-bot-telegram)
   - [2.1 Membuat Bot & Mendapatkan Token via @BotFather](#21-membuat-bot--mendapatkan-token-via-botfather)
   - [2.2 Mendapatkan ID Pengguna Admin Telegram](#22-mendapatkan-id-pengguna-admin-telegram)
3. [Bab 3: Konfigurasi File Proyek](#bab-3-konfigurasi-file-proyek)
   - [3.1 Konfigurasi Environment (.env)](#31-konfigurasi-environment-env)
   - [3.2 Konfigurasi Daftar Akun (config/accounts.yaml)](#32-konfigurasi-daftar-akun-configaccountsyaml)
4. [Bab 4: Panduan Operasional Bot Telegram](#bab-4-panduan-operasional-bot-telegram)
   - [4.1 Perintah Utama (/status, /instances, /billing, /settings)](#41-perintah-utama)
   - [4.2 Keamanan Kontrol Daya Dua Langkah (Two-Step Confirmation)](#42-keamanan-kontrol-daya-dua-langkah-two-step-confirmation)
   - [4.3 Grafik Utilisasi CPU On-Demand](#43-grafik-utilisasi-cpu-on-demand)
   - [4.4 Silent Incident Watchdog & Push Alert](#44-silent-incident-watchdog--push-alert)
5. [Bab 5: Panduan Deployment & Eksekusi](#bab-5-panduan-deployment--eksekusi)
   - [5.1 Menjalankan Secara Lokal (Python Virtual Environment)](#51-menjalankan-secara-lokal-python-virtual-environment)
   - [5.2 Menjalankan 24/7 via Docker Compose](#52-menjalankan-247-via-docker-compose)
6. [Bab 6: Pertanyaan Umum & Troubleshooting (FAQ)](#bab-6-pertanyaan-umum--troubleshooting-faq)

---

## Bab 1: Panduan Kredensial API Oracle Cloud (OCI)

Aplikasi bot membutuhkan autentikasi resmi OCI API Signing Key untuk mengakses data compute, VNIC, telemetri, dan tagihan. Anda memerlukan 5 komponen untuk setiap akun:

| Parameter | Deskripsi | Contoh Nilai |
| :--- | :--- | :--- |
| `region` | Identifier resmi region data center OCI | `ap-singapore-1`, `ap-tokyo-1` |
| `tenancy_ocid` | OCID unik tenancy/organisasi cloud Anda | `ocid1.tenancy.oc1..aaaaaaa...` |
| `user_ocid` | OCID unik akun pengguna OCI Anda | `ocid1.user.oc1..aaaaaaa...` |
| `fingerprint` | Hash fingerprint dari API Key yang terdaftar | `20:3b:97:13:55:1c:...` |
| `key_file` | Path lokal file private key `.pem` | `credentials/keys/acc_01.pem` |

---

### 1.1 Mengetahui Region Identifier
1. Login ke [Oracle Cloud Console](https://cloud.oracle.com/).
2. Di pojok kanan atas layar navigasi, klik nama region yang sedang aktif (misalnya: **Singapore**, **Tokyo**, atau **Ashburn**).
3. Salin nilai **Region Identifier** (berformat huruf kecil dengan strip, contoh: `ap-singapore-1`).

---

### 1.2 Mengambil Tenancy OCID & Compartment OCID
1. Di pojok kanan atas, klik ikon profil/avatar pengguna, lalu klik nama tenancy Anda (**Tenancy: [NamaTenancy]**).
   *(Atau buka menu kiri atas $\rightarrow$ **Administration** $\rightarrow$ **Tenancy Details**)*.
2. Pada bagian **Tenancy Information**, temukan baris **OCID**.
3. Klik tombol **Copy**. Formatnya: `ocid1.tenancy.oc1..aaaaaaa...`
4. **Compartment OCID**:
   - Jika instance VM Anda berada di root compartment (default), isi `compartment_id` dengan nilai yang sama persis dengan `tenancy_ocid`.
   - Jika VM Anda ditempatkan di sub-compartment khusus, buka menu **Identity & Security** $\rightarrow$ **Compartments**, lalu salin OCID compartment target Anda.

---

### 1.3 Mengambil User OCID & Membuat API Key (.pem)
OCI Console menyediakan generator kunci otomatis yang praktis:

1. Klik ikon **Profile** di pojok kanan atas $\rightarrow$ pilih **My Profile** *(atau buka **Identity & Security** $\rightarrow$ **Domains** / **Users** $\rightarrow$ pilih user Anda)*.
2. Di bagian atas profil, cari baris **OCID**, lalu klik **Copy**. Formatnya: `ocid1.user.oc1..aaaaaaa...` *(Ini adalah `user_ocid`)*.
3. Scroll ke bawah ke panel kiri bagian **Resources**, lalu klik tab **API Keys**.
4. Klik tombol **Add API Key**.
5. Pada jendela popup yang muncul:
   - Pilih opsi **Generate API Key Pair**.
   - Klik tombol **Download Private Key** (file akan terunduh dengan ekstensi `.pem`).
     > [!IMPORTANT]
     > Simpan file `.pem` ini dengan aman. OCI hanya mengizinkan pengunduhan kunci privat satu kali saat pertama kali dibuat!
   - Klik tombol **Add**.
6. Setelah tombol *Add* diklik, OCI akan menampilkan kotak dialog **Configuration File Preview**.
   - Pada baris `fingerprint = ...`, salin nilai fingerprint tersebut (format: `xx:xx:xx:...`).

---

### 1.4 Menata File Kunci Privat & Hak Akses (chmod 600)
1. Pindahkan file `.pem` yang baru diunduh ke folder `credentials/keys/` di direktori proyek:
   ```bash
   mv ~/Downloads/*.pem credentials/keys/acc_01.pem
   ```
2. Kunci permission file agar hanya bisa dibaca oleh user pemilik (standar keamanan DevOps):
   ```bash
   chmod 600 credentials/keys/*.pem
   ```

> [!NOTE]
> Seluruh isi folder `credentials/keys/*.pem` telah dilindungi oleh `.gitignore` dan `.dockerignore`, sehingga tidak akan pernah ter-commit atau terunggah ke repositori Git publik.

---

### 1.5 Menambahkan Akun Tambahan (Multi-Tenancy)
Jika Anda memiliki 2 hingga 10 akun OCI (misalnya kombinasi akun Pay-As-You-Go dan Always Free Tier):
1. Logout dari OCI Console, lalu login ke tenancy akun ke-2.
2. Ulangi langkah 1.1 sampai 1.3 pada tenancy tersebut.
3. Simpan file private key-nya sebagai `credentials/keys/acc_02.pem` (dan `credentials/keys/acc_03.pem` untuk akun ke-3).
4. Daftarkan akun-akun tersebut di file `config/accounts.yaml`.

---

## Bab 2: Panduan Setup Bot Telegram

### 2.1 Membuat Bot & Mendapatkan Token via @BotFather
1. Buka aplikasi Telegram Anda, cari kontak resmi [@BotFather](https://t.me/BotFather).
2. Kirim perintah `/newbot`.
3. Masukkan nama tampilan bot Anda (misal: `My OCI Watchdog Bot`).
4. Masukkan username bot (harus berakhiran `bot`, misal: `my_oci_monitor_bot`).
5. BotFather akan memberikan **HTTP API Bot Token** berupa string acak panjang:
   Contoh: `1234567890:ABCDefGhIJKlmNoPQRsTUVwxyZ`
6. Salin token ini untuk konfigurasi file `.env`.

---

### 2.2 Mendapatkan ID Pengguna Admin Telegram
Untuk alasan keamanan (*Zero Trust Security*), bot ini dilengkapi **Admin Whitelist Middleware** yang hanya merespons Telegram User ID terdaftar:

1. Di Telegram, cari bot [@userinfobot](https://t.me/userinfobot) atau [@raw_data_bot](https://t.me/raw_data_bot).
2. Kirim pesan apa saja atau klik `/start`.
3. Bot tersebut akan membalas dengan profil Anda, termasuk baris **Id** (berupa angka numerik, misal: `123456789`).
4. Salin nomor ID ini untuk mengisi `TELEGRAM_ADMIN_USER_ID` di file `.env`.

---

## Bab 3: Konfigurasi File Proyek

### 3.1 Konfigurasi Environment (`.env`)
Salin file template `.env.example`:
```bash
cp .env.example .env
```
Buka file `.env` menggunakan teks editor (misal: `nano .env`) dan sesuaikan nilainya:
```env
# Kredensial Bot Telegram
TELEGRAM_BOT_TOKEN="1234567890:ABCDefGhIJKlmNoPQRsTUVwxyZ"
TELEGRAM_ADMIN_USER_ID=123456789

# Database SQLite Async (aiosqlite WAL mode)
DATABASE_URL="sqlite+aiosqlite:///data/oci_bot.db"

# Path Konfigurasi Akun
ACCOUNTS_CONFIG_PATH="config/accounts.yaml"

# Level Logging
LOG_LEVEL="INFO"

# Default Polling Intervals (dapat diubah dinamis via bot)
DEFAULT_METRICS_INTERVAL_MINUTES=10
DEFAULT_BILLING_INTERVAL_HOURS=6
```

---

### 3.2 Konfigurasi Daftar Akun (`config/accounts.yaml`)
Salin file template:
```bash
cp config/accounts.yaml.example config/accounts.yaml
```
Isi data akun Anda:
```yaml
accounts:
  # Akun 1: Pay-As-You-Go Tenancy
  - account_id: "acc_01"
    name: "Production (Singapore PAYG)"
    account_type: "PAYG"             # Gunakan "PAYG" atau "FREE_TIER"
    tenancy_ocid: "ocid1.tenancy.oc1..aaaaaaaexampletenancy1"
    user_ocid: "ocid1.user.oc1..aaaaaaaexampleuser1"
    fingerprint: "20:3b:97:13:55:1c:11:0d:43:dc:14:28:b5:12:34:56"
    key_file: "credentials/keys/acc_01.pem"
    region: "ap-singapore-1"
    compartment_id: "ocid1.tenancy.oc1..aaaaaaaexampletenancy1"
    monthly_budget: 75.0             # Limit spend (USD) untuk watchdog alert
    is_active: true

  # Akun 2: Always Free Tier Tenancy
  - account_id: "acc_02"
    name: "Dev & Lab (Tokyo Free Tier)"
    account_type: "FREE_TIER"        # Biaya otomatis fallback $0.00
    tenancy_ocid: "ocid1.tenancy.oc1..aaaaaaaexampletenancy2"
    user_ocid: "ocid1.user.oc1..aaaaaaaexampleuser2"
    fingerprint: "11:22:33:44:55:66:77:88:99:aa:bb:cc:dd:ee:ff:00"
    key_file: "credentials/keys/acc_02.pem"
    region: "ap-tokyo-1"
    compartment_id: "ocid1.tenancy.oc1..aaaaaaaexampletenancy2"
    monthly_budget: 0.0
    is_active: true
```

---

## Bab 4: Panduan Operasional Bot Telegram

### 4.1 Perintah Utama

| Perintah | Fungsi | Tampilan Utama |
| :--- | :--- | :--- |
| `/start` | Memulai interaksi | Menampilkan pesan sambutan & menu tombol navigasi cepat |
| `/help` | Manual penggunaan | Menampilkan dokumentasi ringkas dan daftar fitur |
| `/status` | Ikhtisar Global | Total akun, jumlah VM berjalan (🟢) vs mati (🔴), dan total pengeluaran |
| `/instances`| Daftar Compute VM | Tombol navigasi instance untuk melihat Public IP, CPU %, dan kontrol daya |
| `/billing` | Biaya & Forecast | Akumulasi spend MTD, proyeksi linear run-rate akhir bulan, & status budget |
| `/settings` | Pengaturan Polling | Tombol interaktif ubah interval metrik (5/10/30m) & billing (3/6/12h) |

---

### 4.2 Keamanan Kontrol Daya Dua Langkah (Two-Step Confirmation)
Demi mencegah pemadaman server produksi yang tidak disengaja akibat kesalahan sentuh tombol:
1. Saat memilih tombol **[⏹️ Stop]**, **[▶️ Start]**, atau **[🔄 Reboot]**, bot tidak akan langsung mematikan server.
2. Bot akan memunculkan dialog konfirmasi:
   > ⚠️ **KONFIRMASI AKSI KONTROL DAYA**  
   > Apakah Anda yakin ingin mematikan `prod-api-server`?
3. Aksi hanya dieksekusi ke OCI API jika Anda menekan **[✅ Ya, Lanjutkan Eksekusi]**.
4. Setiap eksekusi aksi (berhasil atau gagal) secara otomatis dicatat ke tabel `AUDIT_LOG` di SQLite.

---

### 4.3 Grafik Utilisasi CPU On-Demand
1. Buka menu `/instances` lalu pilih salah satu instance Anda.
2. Klik tombol **[📈 Lihat Grafik CPU]**.
3. Bot akan menghasilkan gambar chart garis PNG beresolusi tinggi yang menampilkan beban CPU 24 jam terakhir lengkap dengan garis batas ambang alert merah (85%).

---

### 4.4 Silent Incident Watchdog & Push Alert
Bot tidak akan mengirim pesan jika kondisi server berjalan normal. Notifikasi langsung ke DM Admin hanya dikirim jika:
- 🚨 **VM Mati Mendadak**: Instance yang tadinya `RUNNING` berubah menjadi `STOPPED` tanpa instruksi bot.
- ⚠️ **CPU Spike**: Beban CPU instance `> 85%` selama 2 siklus pemantauan berurutan.
- 💸 **Budget Terlampaui**: Proyeksi pengeluaran linear akhir bulan pada akun PAYG melampaui `monthly_budget`.
- ✅ **Pemulihan**: Server kembali `RUNNING` atau utilisasi CPU telah turun kembali normal.

---

## Bab 5: Panduan Deployment & Eksekusi

### 5.1 Menjalankan Secara Lokal (Python Virtual Environment)
Cocok untuk pengembangan atau pengujian lokal:
```bash
# 1. Masuk ke environment virtual
source .venv/bin/activate

# 2. Jalankan bot
python -m src.main
```

### 5.2 Menjalankan 24/7 via Docker Compose
Rekomendasi terbaik untuk deployment di VPS atau instance Always Free OCI:
```bash
# 1. Jalankan container di latar belakang
docker compose up -d

# 2. Periksa status dan log bot secara real-time
docker compose logs -f oci-bot

# 3. Menghentikan bot
docker compose down
```

---

## Bab 6: Pertanyaan Umum & Troubleshooting (FAQ)

### Q1: Bot tidak merespons pesan sama sekali saat saya klik `/start`?
- **Penyebab**: Telegram User ID Anda belum cocok dengan nilai `TELEGRAM_ADMIN_USER_ID` di file `.env`.
- **Solusi**: Cek kembali numeric ID Anda melalui [@userinfobot](https://t.me/userinfobot) dan pastikan nilai pada `.env` telah sesuai, lalu restart bot.

### Q2: Muncul error `Private key file not found` saat startup?
- **Penyebab**: Path file `.pem` pada `config/accounts.yaml` tidak cocok dengan lokasi fisik file.
- **Solusi**: Pastikan file `.pem` diletakkan di `credentials/keys/` dan namanya cocok dengan yang tertulis di `config/accounts.yaml`.

### Q3: Akun Always Free saya mengalami error pada query biaya/billing?
- **Penyebab**: Akun Free Tier atau tenancy baru sering kali belum memiliki hak akses atau histori pada OCI Usage API.
- **Solusi**: Sistem bot ini secara otomatis memiliki fitur *Graceful Fallback Free Tier*. Pastikan field `account_type` pada akun tersebut diatur ke `"FREE_TIER"`, sehingga bot otomatis menetapkan nilai biaya ke `$0.00` tanpa error.

### Q4: Apakah aman menyimpan file `.pem` di server?
- **Penyebab**: Kunci API OCI adalah aset kriptografi sensitif.
- **Solusi**: Gunakan hak akses `chmod 600 credentials/keys/*.pem` agar hanya akun user Anda yang dapat membaca file tersebut. Jangan pernah membagikan atau meng-upload folder `credentials/keys/` ke GitHub.
