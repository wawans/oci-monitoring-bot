"""HTML message templates and visual formatting utilities for Telegram UI."""

from typing import Dict, List, Optional

from src.database.models import Account, BillingSnapshot, InstanceState
from src.scheduler.detector import IncidentAlert, IncidentSeverity


def get_status_emoji(state: Optional[str]) -> str:
    """Return status emoji indicator based on OCI lifecycle state."""
    if not state:
        return "⚪"
    normalized = state.upper()
    if normalized == "RUNNING":
        return "🟢"
    if normalized in {"STOPPED", "CRITICAL"}:
        return "🔴"
    if normalized in {"STARTING", "STOPPING", "PROVISIONING", "TERMINATING"}:
        return "🟡"
    return "⚪"


def format_start_message(admin_id: int) -> str:
    """Return welcome introduction message."""
    return (
        "🤖 <b>OCI Multi-Account Telegram Monitoring Bot</b>\n\n"
        "Sistem pemantauan dan kontrol terpusat untuk multi-akun Oracle Cloud Infrastructure.\n\n"
        "<b>Perintah Utama:</b>\n"
        "• /status — Ringkasan kesehatan seluruh akun & VM\n"
        "• /instances — Navigasi detail VM & kontrol daya\n"
        "• /billing — Rekapitulasi MTD spend & proyeksi forecast\n"
        "• /settings — Ubah interval polling metrik & billing\n"
        "• /help — Panduan penggunaan lengkap\n\n"
        f"🔐 <i>Terautentikasi untuk Admin Telegram ID: <code>{admin_id}</code></i>"
    )


def format_help_message() -> str:
    """Return comprehensive user manual and guidance."""
    return (
        "📖 <b>Panduan Penggunaan OCI Monitoring Bot</b>\n\n"
        "<b>1. Perintah Navigasi:</b>\n"
        "• <code>/status</code>: Menampilkan ikhtisar global seluruh akun terdaftar, jumlah VM aktif, dan status kesehatan sistem.\n"
        "• <code>/instances</code>: Menampilkan daftar VM interaktif. Anda dapat memilih VM untuk melihat Public IP, beban CPU, dan tombol daya.\n"
        "• <code>/billing</code>: Menampilkan akumulasi biaya bulan berjalan (MTD), estimasi run-rate akhir bulan, dan status budget PAYG.\n"
        "• <code>/settings</code>: Mengatur interval polling status (5, 10, 30 menit) dan billing (3, 6, 12 jam) secara langsung.\n\n"
        "<b>2. Fitur Keamanan Daya (Two-Step Confirmation):</b>\n"
        "Setiap aksi Start, Stop, atau Reboot VM mewajibkan dialog konfirmasi inline keyboard sebelum dikirim ke OCI API.\n\n"
        "<b>3. Silent Watchdog:</b>\n"
        "Bot berjalan senyap di latar belakang dan HANYA mengirimkan notifikasi otomatis jika terdeteksi insiden VM mati mendadak, lonjakan CPU > 85%, atau budget terlampaui."
    )


def format_status_overview(
    accounts: List[Account],
    instances: List[InstanceState],
    total_spend: float = 0.0,
) -> str:
    """Format global health overview across all accounts."""
    total_vm = len(instances)
    running_vm = sum(1 for vm in instances if vm.lifecycle_state.upper() == "RUNNING")
    stopped_vm = sum(1 for vm in instances if vm.lifecycle_state.upper() in {"STOPPED", "CRITICAL"})

    lines = [
        "📊 <b>Ikhtisar Status OCI Multi-Akun</b>",
        "────────────────────────────",
        f"🏢 <b>Total Akun Terdaftar:</b> {len(accounts)} akun",
        f"🖥️ <b>Total Instance:</b> {total_vm} (🟢 {running_vm} Aktif | 🔴 {stopped_vm} Mati)",
        f"💰 <b>Total MTD Spend:</b> ${total_spend:.2f} USD",
        "────────────────────────────",
        "<b>Daftar Akun:</b>",
    ]

    for acc in accounts:
        acc_vms = [vm for vm in instances if vm.account_id == acc.account_id]
        acc_running = sum(1 for vm in acc_vms if vm.lifecycle_state.upper() == "RUNNING")
        tier_label = "PAYG" if acc.account_type.upper() == "PAYG" else "Free Tier"
        lines.append(
            f"• <b>{acc.name}</b> ({tier_label})\n"
            f"  └ Region: <code>{acc.region}</code> | VM: {acc_running}/{len(acc_vms)} aktif"
        )

    return "\n".join(lines)


def format_instance_detail(instance: InstanceState, account_name: str) -> str:
    """Format detailed information of a single compute instance."""
    emoji = get_status_emoji(instance.lifecycle_state)
    cpu_str = f"{instance.latest_cpu_percent:.1f}%" if instance.latest_cpu_percent is not None else "N/A"
    public_ip = instance.public_ip or "<i>Tidak ada (Private Only)</i>"
    private_ip = instance.private_ip or "N/A"
    last_seen_str = instance.last_seen.strftime("%Y-%m-%d %H:%M:%S UTC")

    return (
        f"{emoji} <b>Detail Compute Instance</b>\n"
        "────────────────────────────\n"
        f"<b>Nama:</b> <code>{instance.display_name}</code>\n"
        f"<b>Akun:</b> {account_name}\n"
        f"<b>Status:</b> <b>{instance.lifecycle_state}</b>\n"
        f"<b>Shape:</b> <code>{instance.shape}</code>\n"
        f"<b>Region:</b> <code>{instance.region}</code>\n"
        f"<b>Public IP:</b> <code>{public_ip}</code>\n"
        f"<b>Private IP:</b> <code>{private_ip}</code>\n"
        f"<b>Utilisasi CPU Terkini:</b> <b>{cpu_str}</b>\n"
        f"<b>Terakhir Diperbarui:</b> <i>{last_seen_str}</i>\n"
        "────────────────────────────"
    )


def format_billing_overview(
    accounts: List[Account],
    snapshots: Dict[str, BillingSnapshot],
    forecasts: Dict[str, float],
) -> str:
    """Format multi-account billing summary, linear run-rate forecast, and budget status."""
    lines = [
        "💳 <b>Rekapitulasi Tagihan & Proyeksi Biaya</b>",
        "────────────────────────────",
    ]

    total_mtd = 0.0
    total_forecast = 0.0

    for acc in accounts:
        snap = snapshots.get(acc.account_id)
        mtd = snap.amount if snap else 0.0
        forecast = forecasts.get(acc.account_id, 0.0)
        total_mtd += mtd
        total_forecast += forecast

        tier = "PAYG" if acc.account_type.upper() == "PAYG" else "Free Tier"
        budget_str = f"${acc.monthly_budget:.2f}" if acc.monthly_budget > 0 else "N/A"

        status_tag = "🟢 Normal"
        if acc.monthly_budget > 0 and forecast > acc.monthly_budget:
            status_tag = "🔴 <b>Over Budget</b>"

        lines.extend([
            f"🏢 <b>{acc.name}</b> ({tier})",
            f"  • MTD Spend: <b>${mtd:.2f} USD</b>",
            f"  • Run-Rate Forecast: <b>${forecast:.2f} USD</b>",
            f"  • Target Budget: {budget_str} ({status_tag})",
            "",
        ])

    lines.extend([
        "────────────────────────────",
        f"💵 <b>Total Aktual Bulan Ini:</b> ${total_mtd:.2f} USD",
        f"📈 <b>Total Proyeksi Akhir Bulan:</b> ${total_forecast:.2f} USD",
    ])

    return "\n".join(lines)


def format_action_confirm_prompt(display_name: str, action: str) -> str:
    """Format two-step confirmation dialogue for power management actions (ADR-007)."""
    action_icons = {
        "START": "▶️ START (Hidupkan)",
        "STOP": "⏹️ STOP (Matikan)",
        "SOFTRESET": "🔄 SOFTRESET (Reboot)",
    }
    action_label = action_icons.get(action.upper(), action.upper())

    return (
        "⚠️ <b>KONFIRMASI AKSI KONTROL DAYA</b>\n\n"
        f"Apakah Anda yakin ingin mengeksekusi aksi berikut?\n\n"
        f"• <b>Target VM:</b> <code>{display_name}</code>\n"
        f"• <b>Aksi:</b> <b>{action_label}</b>\n\n"
        "<i>Harap pastikan sebelum melanjutkan untuk menghindari pemadaman layanan produksi!</i>"
    )


def format_action_result(
    display_name: str,
    action: str,
    success: bool,
    error_msg: Optional[str] = None,
) -> str:
    """Format result notification after executing a power action."""
    if success:
        return (
            f"✅ <b>Aksi Berhasil Dikirim ke OCI API</b>\n\n"
            f"Aksi <code>{action.upper()}</code> pada instance <b>{display_name}</b> "
            f"telah diterima oleh Oracle Cloud dan sedang diproses."
        )
    return (
        f"❌ <b>Aksi Gagal Dieksekusi</b>\n\n"
        f"Aksi <code>{action.upper()}</code> pada instance <b>{display_name}</b> gagal.\n"
        f"<b>Penyebab:</b> <code>{error_msg or 'Unknown Error'}</code>"
    )


def format_settings_menu(current_metrics: int, current_billing: int) -> str:
    """Format settings menu for polling interval adjustments."""
    return (
        "⚙️ <b>Pengaturan Interval Pemantauan Bot</b>\n\n"
        f"• <b>Interval Status & CPU:</b> <code>{current_metrics} menit</code>\n"
        f"• <b>Interval Billing & Forecast:</b> <code>{current_billing} jam</code>\n\n"
        "Pilih tombol di bawah untuk mengubah jadwal polling secara langsung tanpa restart aplikasi:"
    )
