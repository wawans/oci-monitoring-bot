# AGENTS.md - Operational Guardrails & Coding Standards

Dokumen ini adalah **pedoman operasional baku (Konstitusi Proyek)** bagi AI Agent dan developer yang berkontribusi pada repositori `oci-bot`. Semua AI Agent yang membaca workspace ini **WAJIB mematuhi seluruh aturan di bawah ini**.

---

## 1. Aturan Keamanan & Kredensial (CRITICAL)

1. **JANGAN PERNAH** menyimpan, menampilkan, atau me-log isi dari file kunci privat `.pem`, token Telegram bot, atau nilai kredensial rahasia ke dalam response chat, log file, atau Git commit.
2. File kunci `.pem` HANYA boleh diletakkan di `credentials/keys/*.pem` (yang sudah terblokir oleh `.gitignore`).
3. File `config/accounts.yaml` berisi konfigurasi akun riil dan tidak boleh di-commit. Gunakan `config/accounts.yaml.example` sebagai referensi struktur publik.
4. Token bot dan Telegram Admin ID HANYA boleh dibaca melalui environment variables (`.env`) via `config/settings.py`.

---

## 2. Standar Bahasa & Gaya Penulisan Kode (Python 3.11+)

1. **Type Hints**: Setiap fungsi dan method **wajib** menyertakan type hint lengkap untuk parameter dan return value (misal: `def get_instance(...) -> Optional[Dict[str, Any]]:`).
2. **Asynchronous First**: 
   - Semua fungsi I/O (Database, Telegram Handlers, Background Tasks) harus menggunakan `async`/`await`.
   - Panggilan ke OCI SDK yang bersifat synchronous harus dibungkus dengan `asyncio.to_thread(...)` agar tidak memblokir event loop asyncio bot Telegram.
3. **Pola Desain Modular (Separation of Concerns)**:
   - **Service Layer (`src/oci_services/`)**: Murni interaksi dengan OCI SDK. Dilarang memanggil method Telegram bot di dalam service layer.
   - **Database Layer (`src/database/`)**: Murni operasi query/upsert tabel SQLite.
   - **Scheduler Layer (`src/scheduler/`)**: Mengatur timer dan pemanggilan berkala.
   - **Bot Layer (`src/bot/`)**: Menangani parsing pesan Telegram, validasi otorisasi, dan tampilan antarmuka (keyboard, template teks, chart).
4. **Path Handling**: Selalu gunakan modul standar `pathlib.Path` untuk memanipulasi file dan direktori, agar path resolusi aman di Linux, Docker, dan Windows PowerShell.

---

## 3. Penanganan Error & Ketahanan Sistem (Fault Tolerance)

1. **Fault Isolation per Akun**:
   Setiap interaksi dengan akun OCI (3–10 akun) di dalam looping **wajib dibungkus dengan `try...except` spesifik per akun**. Kegagalan pada Akun A (misal network timeout atau key invalid) tidak boleh menyebabkan pemrosesan Akun B dan C berhenti.
2. **Graceful Fallback Free Tier**:
   Akun bertipe `FREE_TIER` atau akun tanpa histori tagihan tidak boleh memicu error crash saat query Cost API. Tangkap `oci.exceptions.ServiceError` dan kembalikan nilai `$0.00`.
3. **Structured Logging**:
   Gunakan modul standar `logging` Python dengan format timestamp, level, modul, dan pesan. Jangan gunakan `print()` di production code.

---

## 4. Alur Kerja Agentic & Definition of Done

Sebelum menandai suatu task selesai:
1. **Lakukan Self-Testing**: Jalankan suite unit test (`pytest tests/ -v`) dan pastikan seluruh test berstatus **PASSED**.
2. **Perbarui Dokumentasi**:
   - Beri tanda centang `[x]` pada task yang selesai di `TASK.md`.
   - Perbarui catatan estafet di `HANDOFF.md` yang merangkum apa yang baru saja diselesaikan dan apa langkah berikutnya.
3. **Commit Terstruktur**: Buat Git commit dengan format Conventional Commits:
   - `feat(...)`: Fitur baru
   - `fix(...)`: Perbaikan bug
   - `docs(...)`: Perubahan dokumentasi
   - `test(...)`: Penambahan/perbaikan pengujian
   - `refactor(...)`: Restrukturisasi kode tanpa mengubah fungsionalitas
