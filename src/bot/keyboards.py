"""Inline Keyboards for Telegram Bot interactive UI and two-step action confirmation."""

from typing import List

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.formatters import get_status_emoji
from src.database.models import InstanceState


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Return persistent main navigation keyboard."""
    buttons = [
        [
            InlineKeyboardButton("📊 Status Global", callback_data="nav_status"),
            InlineKeyboardButton("🖥️ Daftar VM", callback_data="nav_instances"),
        ],
        [
            InlineKeyboardButton("💳 Billing & Forecast", callback_data="nav_billing"),
            InlineKeyboardButton("⚙️ Pengaturan Polling", callback_data="nav_settings"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def get_instances_keyboard(instances: List[InstanceState]) -> InlineKeyboardMarkup:
    """Return list of clickable instance buttons."""
    buttons = []
    for inst in instances:
        emoji = get_status_emoji(inst.lifecycle_state)
        label = f"{emoji} {inst.display_name} ({inst.region})"
        buttons.append([
            InlineKeyboardButton(label, callback_data=f"vm_detail:{inst.instance_id}")
        ])

    # Footer navigation
    buttons.append([
        InlineKeyboardButton("🔄 Refresh", callback_data="nav_instances"),
        InlineKeyboardButton("🔙 Menu Utama", callback_data="nav_main"),
    ])
    return InlineKeyboardMarkup(buttons)


def get_instance_actions_keyboard(
    instance_id: str,
    lifecycle_state: str,
) -> InlineKeyboardMarkup:
    """Return power management and metric actions for a specific instance."""
    normalized = lifecycle_state.upper()
    action_row = []

    if normalized == "STOPPED":
        action_row.append(
            InlineKeyboardButton("▶️ Start", callback_data=f"act_prompt:{instance_id}:START")
        )
    elif normalized == "RUNNING":
        action_row.extend([
            InlineKeyboardButton("⏹️ Stop", callback_data=f"act_prompt:{instance_id}:STOP"),
            InlineKeyboardButton("🔄 Reboot", callback_data=f"act_prompt:{instance_id}:SOFTRESET"),
        ])
    else:
        action_row.append(
            InlineKeyboardButton("⏹️ Force Stop", callback_data=f"act_prompt:{instance_id}:STOP")
        )

    buttons = [
        action_row,
        [InlineKeyboardButton("📈 Lihat Grafik CPU", callback_data=f"vm_chart:{instance_id}")],
        [InlineKeyboardButton("🔙 Kembali ke Daftar VM", callback_data="nav_instances")],
    ]
    return InlineKeyboardMarkup(buttons)


def get_action_confirm_keyboard(
    instance_id: str,
    action: str,
) -> InlineKeyboardMarkup:
    """Return two-step confirmation dialogue buttons (ADR-007)."""
    buttons = [
        [
            InlineKeyboardButton(
                "✅ Ya, Lanjutkan Eksekusi",
                callback_data=f"act_exec:{instance_id}:{action}",
            ),
            InlineKeyboardButton(
                "❌ Batalkan",
                callback_data=f"vm_detail:{instance_id}",
            ),
        ]
    ]
    return InlineKeyboardMarkup(buttons)


def get_settings_keyboard(
    current_metrics_m: int,
    current_billing_h: int,
) -> InlineKeyboardMarkup:
    """Return interactive buttons to adjust polling intervals."""
    # Row 1: Metrics intervals (5, 10, 30 minutes)
    metrics_buttons = []
    for m in [5, 10, 30]:
        label = f"✅ {m}m" if m == current_metrics_m else f"{m}m"
        metrics_buttons.append(
            InlineKeyboardButton(label, callback_data=f"set_metric:{m}")
        )

    # Row 2: Billing intervals (3, 6, 12 hours)
    billing_buttons = []
    for h in [3, 6, 12]:
        label = f"✅ {h}h" if h == current_billing_h else f"{h}h"
        billing_buttons.append(
            InlineKeyboardButton(label, callback_data=f"set_billing:{h}")
        )

    buttons = [
        metrics_buttons,
        billing_buttons,
        [InlineKeyboardButton("🔙 Menu Utama", callback_data="nav_main")],
    ]
    return InlineKeyboardMarkup(buttons)
