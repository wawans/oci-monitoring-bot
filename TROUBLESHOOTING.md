# TROUBLESHOOTING.md - Edge Cases & Known Issues Knowledge Base

Basis pengetahuan untuk mengatasi masalah teknis, keanehan (*quirks*) OCI SDK, dan batasan lingkungan yang telah diidentifikasi pada proyek `oci-bot`.

---

### 1. OCI Usage / Cost API pada Akun Always Free atau Trial Baru
- **Gejala**: OCI SDK melempar exception `oci.exceptions.ServiceError` dengan HTTP Status `404 NotAuthorizedOrNotFound` atau `400 InvalidParameter` saat memanggil `request_summarized_usages`.
- **Penyebab**: Akun OCI Always Free murni atau tenancy Trial baru yang belum di-upgrade ke PAYG sering kali belum memiliki compartment billing terisi atau tidak memiliki data agregasi biaya.
- **Solusi Baku**:
  ```python
  try:
      response = usage_client.request_summarized_usages(details)
      # parse response
  except oci.exceptions.ServiceError as exc:
      if exc.status in (404, 401) or "NotAuthorized" in str(exc.message):
          logger.warning("Cost API tidak tersedia pada akun %s (kemungkinan Free Tier). Menggunakan default $0.00", account_id)
          return {"amount": 0.0, "currency": "USD", "is_free_tier": True}
      raise
  ```

---

### 2. Path Kunci Privat `.pem` pada Sistem Operasi Windows
- **Gejala**: OCI SDK gagal membaca private key dengan pesan error `ValueError: Could not deserialize key data` atau `FileNotFoundError`.
- **Penyebab**: Karakter backslash `\` pada path Windows tidak di-*resolve* dengan benar atau relative path dieksekusi dari working directory yang berbeda.
- **Solusi Baku**:
  Selalu gunakan `pathlib.Path` untuk melakukan normalisasi absolute path:
  ```python
  from pathlib import Path

  key_path = Path(raw_key_path).expanduser().resolve()
  if not key_path.exists():
      raise FileNotFoundError(f"File kunci OCI tidak ditemukan di: {key_path}")
  ```

---

### 3. Mengambil Public IP dari Compute Instance OCI
- **Gejala**: Objek `oci.core.models.Instance` tidak memiliki atribut `public_ip`.
- **Penyebab**: Pada arsitektur OCI, Public IP menempel pada VNIC (Virtual Network Interface Card), bukan pada instance secara langsung.
- **Solusi Baku**:
  ```python
  # 1. Ambil list VNIC attachment
  vnic_attachments = compute_client.list_vnic_attachments(
      compartment_id=compartment_id, 
      instance_id=instance_id
  ).data

  public_ip = None
  private_ip = None

  for attachment in vnic_attachments:
      if attachment.lifecycle_state == "ATTACHED":
          vnic = vnet_client.get_vnic(attachment.vnic_id).data
          public_ip = vnic.public_ip
          private_ip = vnic.private_ip
          break
  ```

---

### 4. SQLite Database Lock saat Akses Konkuren
- **Gejala**: Muncul pesan error `sqlite3.OperationalError: database is locked` ketika background worker menulis log metrik bersamaan dengan Telegram bot yang membaca status.
- **Solusi Baku**:
  Aktifkan mode Write-Ahead Logging (WAL) pada SQLite saat inisialisasi koneksi engine:
  ```python
  from sqlalchemy.ext.asyncio import create_async_engine
  from sqlalchemy import event

  engine = create_async_engine("sqlite+aiosqlite:///data/bot.db")

  @event.listens_for(engine.sync_engine, "connect")
  def set_sqlite_pragma(dbapi_connection, connection_record):
      cursor = dbapi_connection.cursor()
      cursor.execute("PRAGMA journal_mode=WAL")
      cursor.execute("PRAGMA synchronous=NORMAL")
      cursor.close()
  ```

---

### 5. Matplotlib GUI Backend Crash pada Lingkungan Headless / Docker
- **Gejala**: `UserWarning: Matplotlib is currently using agg, which is a non-GUI backend` atau error crash X11 saat merender chart di server/container.
- **Solusi Baku**:
  Paksa penggunaan backend non-GUI `Agg` sebelum mengimpor `pyplot`:
  ```python
  import matplotlib
  matplotlib.use("Agg")
  import matplotlib.pyplot as plt
  ```
