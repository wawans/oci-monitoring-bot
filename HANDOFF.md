# HANDOFF.md - Working Memory & Session Handover

Catatan estafet untuk AI Agent / developer yang melanjutkan pengerjaan proyek `oci-bot`.

---

## 1. Status Proyek Saat Ini
- **Status**: Fondasi ekosistem dokumen pendukung dan Git repository berhasil diinisialisasi pada branch `main`.
- **Fase Aktif**: Persiapan Eksekusi **Fase 1 (Environment, Konfigurasi & Basis Data SQLite)**.
- **Git State**: Git repository telah diinisialisasi (`main`), file `.gitignore` aktif, direktori `credentials/keys/.gitkeep` telah dibuat.

---

## 2. File yang Baru Saja Dibuat
1. `.gitignore`: Proteksi menyeluruh untuk kunci `.pem`, `.env`, database SQLite, file cache Python, dll.
2. `credentials/keys/.gitkeep`: Folder penampung kunci privat OCI lokal.
3. `docs/SPEC.md`: Master specification dan arsitektur permanen proyek.
4. `AGENTS.md`: Panduan operasional baku, konvensi kode (Python 3.11+, type hints, async/await, Windows compatibility), dan guardrails keamanan.
5. `DECISIONS.md`: Catatan 7 keputusan arsitektur (ADR-001 s/d ADR-007).
6. `TASK.md`: Checklist granular task dari Fase 1 hingga Fase 5.
7. `TROUBLESHOOTING.md`: Basis pengetahuan isu dan solusi edge-case OCI & Telegram.
8. `README.md`: Panduan pengenalan proyek, fitur, struktur folder, dan petunjuk setup.

---

## 3. Langkah Persis Selanjutnya (Immediate Next Steps)
Bagi AI Agent yang melanjutkan pengerjaan:
1. Mulai eksekusi **Sub-task 1.1** pada `TASK.md`:
   - Buat file `requirements.txt` dengan dependensi yang telah ditentukan di `docs/SPEC.md`.
   - Buat `.env.example` dan modul `config/settings.py` menggunakan `pydantic-settings`.
   - Buat file contoh konfigurasi `config/accounts.yaml.example` yang mencakup 3-10 akun OCI (PAYG & Free Tier).
   - Buat parser konfigurasi di `config/parser.py` untuk memvalidasi keberadaan file `.pem`.
2. Lanjutkan ke **Sub-task 1.2**:
   - Buat koneksi SQLite async di `src/database/connection.py` dengan WAL mode.
   - Buat model SQLAlchemy di `src/database/models.py`.
3. Jalankan pengujian Fase 1, centang task di `TASK.md`, perbarui `HANDOFF.md`, dan lakukan Git commit untuk Fase 1.
