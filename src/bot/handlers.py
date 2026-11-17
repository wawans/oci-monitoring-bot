"""Telegram bot command handlers, callback query dispatcher, and audit logger."""

import logging
from typing import Any, Optional

from sqlalchemy import desc, select
from telegram import Bot, CallbackQuery, Update
from telegram.ext import ContextTypes

from config.settings import get_settings
from src.bot.charts import generate_cpu_chart
from src.bot.formatters import (
    format_action_confirm_prompt,
    format_action_result,
    format_billing_overview,
    format_help_message,
    format_instance_detail,
    format_settings_menu,
    format_start_message,
    format_status_overview,
)
from src.bot.keyboards import (
    get_action_confirm_keyboard,
    get_instance_actions_keyboard,
    get_instances_keyboard,
    get_main_menu_keyboard,
    get_settings_keyboard,
)
from src.bot.middleware import admin_only
from src.database.connection import get_session, set_bot_setting
from src.database.models import Account, AuditLog, BillingSnapshot, InstanceState, MetricsLog
from src.scheduler.detector import IncidentAlert

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Incident Push Alert Dispatcher (ADR-002)
# -----------------------------------------------------------------------------
async def dispatch_incident_push_alert(
    bot: Bot,
    admin_id: int,
    alert: IncidentAlert,
) -> None:
    """Send real-time incident push notification directly to the Admin DM."""
    if admin_id <= 0:
        logger.warning("Cannot dispatch alert: TELEGRAM_ADMIN_USER_ID not configured.")
        return

    text = (
        f"{alert.title}\n"
        "────────────────────────────\n"
        f"{alert.message}\n\n"
        f"<i>Waktu Deteksi: {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}</i>"
    )

    try:
        await bot.send_message(
            chat_id=admin_id,
            text=text,
            parse_mode="HTML",
        )
        logger.info("Successfully pushed incident alert (%s) to Admin %d", alert.incident_type, admin_id)
    except Exception as e:
        logger.error("Failed to send incident push alert to Admin %d: %s", admin_id, e)


# -----------------------------------------------------------------------------
# Command Handlers
# -----------------------------------------------------------------------------
@admin_only
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    admin_id = get_settings().telegram_admin_user_id
    text = format_start_message(admin_id)
    if update.effective_message:
        await update.effective_message.reply_html(
            text=text,
            reply_markup=get_main_menu_keyboard(),
        )


@admin_only
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    text = format_help_message()
    if update.effective_message:
        await update.effective_message.reply_html(
            text=text,
            reply_markup=get_main_menu_keyboard(),
        )


@admin_only
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status command: Instant overview across all accounts."""
    async with get_session() as session:
        acc_res = await session.execute(select(Account).order_by(Account.name))
        accounts = list(acc_res.scalars().all())

        inst_res = await session.execute(select(InstanceState))
        instances = list(inst_res.scalars().all())

        snap_res = await session.execute(select(BillingSnapshot))
        total_spend = sum(s.amount for s in snap_res.scalars().all())

    text = format_status_overview(accounts, instances, total_spend)
    if update.effective_message:
        await update.effective_message.reply_html(
            text=text,
            reply_markup=get_main_menu_keyboard(),
        )


@admin_only
async def instances_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /instances command: Interactive compute instance browser."""
    async with get_session() as session:
        inst_res = await session.execute(
            select(InstanceState).order_by(InstanceState.display_name)
        )
        instances = list(inst_res.scalars().all())

    if not instances:
        msg = "ℹ️ Belum ada instance yang terdaftar di database. Polling awal sedang berlangsung..."
        if update.effective_message:
            await update.effective_message.reply_html(msg, reply_markup=get_main_menu_keyboard())
        return

    text = "🖥️ <b>Pilih Compute Instance untuk melihat detail & kontrol daya:</b>"
    if update.effective_message:
        await update.effective_message.reply_html(
            text=text,
            reply_markup=get_instances_keyboard(instances),
        )


@admin_only
async def billing_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /billing command: MTD spend and run-rate forecast recap."""
    async with get_session() as session:
        acc_res = await session.execute(select(Account).order_by(Account.name))
        accounts = list(acc_res.scalars().all())

        snapshots = {}
        forecasts = {}

        for acc in accounts:
            snap_res = await session.execute(
                select(BillingSnapshot)
                .where(BillingSnapshot.account_id == acc.account_id)
                .order_by(desc(BillingSnapshot.recorded_at))
            )
            latest_snap = snap_res.scalars().first()
            if latest_snap:
                snapshots[acc.account_id] = latest_snap
                # Estimate forecast based on current day
                forecasts[acc.account_id] = latest_snap.amount  # Fallback

    text = format_billing_overview(accounts, snapshots, forecasts)
    if update.effective_message:
        await update.effective_message.reply_html(
            text=text,
            reply_markup=get_main_menu_keyboard(),
        )


@admin_only
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /settings command: Interactive polling interval configuration."""
    scheduler_mgr = context.bot_data.get("scheduler_manager")
    if scheduler_mgr:
        status = scheduler_mgr.get_status()
        current_m = status["metrics_interval_minutes"]
        current_b = status["billing_interval_hours"]
    else:
        current_m = get_settings().default_metrics_interval_minutes
        current_b = get_settings().default_billing_interval_hours

    text = format_settings_menu(current_m, current_b)
    if update.effective_message:
        await update.effective_message.reply_html(
            text=text,
            reply_markup=get_settings_keyboard(current_m, current_b),
        )


# -----------------------------------------------------------------------------
# Callback Query Router
# -----------------------------------------------------------------------------
@admin_only
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route all inline keyboard button interactions."""
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()
    data = query.data

    # Main Navigation
    if data == "nav_main":
        admin_id = get_settings().telegram_admin_user_id
        await query.edit_message_text(
            text=format_start_message(admin_id),
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    if data == "nav_status":
        async with get_session() as session:
            acc_res = await session.execute(select(Account).order_by(Account.name))
            accounts = list(acc_res.scalars().all())
            inst_res = await session.execute(select(InstanceState))
            instances = list(inst_res.scalars().all())
            snap_res = await session.execute(select(BillingSnapshot))
            total_spend = sum(s.amount for s in snap_res.scalars().all())

        await query.edit_message_text(
            text=format_status_overview(accounts, instances, total_spend),
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    if data == "nav_instances":
        async with get_session() as session:
            inst_res = await session.execute(
                select(InstanceState).order_by(InstanceState.display_name)
            )
            instances = list(inst_res.scalars().all())

        if not instances:
            await query.edit_message_text(
                text="ℹ️ Belum ada instance yang terdaftar di database.",
                parse_mode="HTML",
                reply_markup=get_main_menu_keyboard(),
            )
            return

        await query.edit_message_text(
            text="🖥️ <b>Pilih Compute Instance untuk melihat detail & kontrol daya:</b>",
            parse_mode="HTML",
            reply_markup=get_instances_keyboard(instances),
        )
        return

    if data == "nav_billing":
        async with get_session() as session:
            acc_res = await session.execute(select(Account).order_by(Account.name))
            accounts = list(acc_res.scalars().all())
            snapshots = {}
            forecasts = {}
            for acc in accounts:
                snap_res = await session.execute(
                    select(BillingSnapshot)
                    .where(BillingSnapshot.account_id == acc.account_id)
                    .order_by(desc(BillingSnapshot.recorded_at))
                )
                latest_snap = snap_res.scalars().first()
                if latest_snap:
                    snapshots[acc.account_id] = latest_snap
                    forecasts[acc.account_id] = latest_snap.amount

        await query.edit_message_text(
            text=format_billing_overview(accounts, snapshots, forecasts),
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    if data == "nav_settings":
        scheduler_mgr = context.bot_data.get("scheduler_manager")
        if scheduler_mgr:
            status = scheduler_mgr.get_status()
            current_m = status["metrics_interval_minutes"]
            current_b = status["billing_interval_hours"]
        else:
            current_m = get_settings().default_metrics_interval_minutes
            current_b = get_settings().default_billing_interval_hours

        await query.edit_message_text(
            text=format_settings_menu(current_m, current_b),
            parse_mode="HTML",
            reply_markup=get_settings_keyboard(current_m, current_b),
        )
        return

    # Instance Detail
    if data.startswith("vm_detail:"):
        instance_id = data.split("vm_detail:")[1]
        async with get_session() as session:
            res = await session.execute(
                select(InstanceState).where(InstanceState.instance_id == instance_id)
            )
            inst = res.scalars().first()
            if not inst:
                await query.edit_message_text("❌ Instance tidak ditemukan di database.")
                return

            acc_res = await session.execute(
                select(Account.name).where(Account.account_id == inst.account_id)
            )
            val = acc_res.scalars().first()
            account_name = str(val) if val else inst.account_id

        await query.edit_message_text(
            text=format_instance_detail(inst, account_name),
            parse_mode="HTML",
            reply_markup=get_instance_actions_keyboard(inst.instance_id, inst.lifecycle_state),
        )
        return

    # Two-Step Power Action Confirmation Prompt (ADR-007)
    if data.startswith("act_prompt:"):
        parts = data.split(":")
        instance_id = parts[1]
        action = parts[2]

        async with get_session() as session:
            res = await session.execute(
                select(InstanceState.display_name).where(InstanceState.instance_id == instance_id)
            )
            val_vm = res.scalars().first()
            vm_name = str(val_vm) if val_vm else instance_id

        await query.edit_message_text(
            text=format_action_confirm_prompt(vm_name, action),
            parse_mode="HTML",
            reply_markup=get_action_confirm_keyboard(instance_id, action),
        )
        return

    # Power Action Execution (ADR-007)
    if data.startswith("act_exec:"):
        parts = data.split(":")
        instance_id = parts[1]
        action = parts[2]

        client_factory = context.bot_data.get("client_factory")
        compute_service = context.bot_data.get("compute_service")

        async with get_session() as session:
            res = await session.execute(
                select(InstanceState).where(InstanceState.instance_id == instance_id)
            )
            inst = res.scalars().first()
            if not inst:
                await query.edit_message_text("❌ Instance tidak ditemukan.")
                return

            account_id = inst.account_id
            vm_name = inst.display_name

        bundle = client_factory.get_bundle(account_id) if client_factory else None
        success = False
        error_msg: Optional[str] = None

        if not bundle or not compute_service:
            error_msg = f"Client bundle tidak ditemukan untuk akun {account_id}"
        else:
            try:
                success = await compute_service.execute_action(bundle, instance_id, action)
            except Exception as e:
                success = False
                error_msg = str(e)

        # Record in AUDIT_LOG
        user_id = update.effective_user.id if update.effective_user else 0
        async with get_session() as session:
            audit = AuditLog(
                user_id=user_id,
                account_id=account_id,
                instance_id=instance_id,
                action=action,
                status="SUCCESS" if success else "FAILED",
            )
            session.add(audit)
            await session.commit()

        await query.edit_message_text(
            text=format_action_result(vm_name, action, success, error_msg),
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    # On-Demand CPU Chart Generation
    if data.startswith("vm_chart:"):
        instance_id = data.split("vm_chart:")[1]

        async with get_session() as session:
            res = await session.execute(
                select(InstanceState).where(InstanceState.instance_id == instance_id)
            )
            inst = res.scalars().first()
            if not inst:
                await query.edit_message_text("❌ Instance tidak ditemukan.")
                return

            # Query historical CPU datapoints from SQLite METRICS_LOG
            metrics_res = await session.execute(
                select(MetricsLog.timestamp, MetricsLog.cpu_percent)
                .where(MetricsLog.instance_id == instance_id)
                .order_by(MetricsLog.timestamp.asc())
            )
            datapoints = [(row[0], float(row[1])) for row in metrics_res.all()]
            vm_name = inst.display_name

        chart_buffer = generate_cpu_chart(datapoints, vm_name, hours=24)

        if update.effective_chat:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=chart_buffer,
                caption=f"📈 Grafik Utilisasi CPU untuk <b>{vm_name}</b> (Histori 24 Jam)",
                parse_mode="HTML",
            )
        return

    # Dynamic Settings Interval Updates
    if data.startswith("set_metric:"):
        new_m = int(data.split(":")[1])
        scheduler_mgr = context.bot_data.get("scheduler_manager")
        if scheduler_mgr:
            scheduler_mgr.reschedule_metrics(new_m)
            async with get_session() as session:
                await set_bot_setting(session, "poll_metrics_interval", str(new_m))
            status = scheduler_mgr.get_status()
            await query.edit_message_text(
                text=format_settings_menu(new_m, status["billing_interval_hours"]),
                parse_mode="HTML",
                reply_markup=get_settings_keyboard(new_m, status["billing_interval_hours"]),
            )
        return

    if data.startswith("set_billing:"):
        new_h = int(data.split(":")[1])
        scheduler_mgr = context.bot_data.get("scheduler_manager")
        if scheduler_mgr:
            scheduler_mgr.reschedule_billing(new_h)
            async with get_session() as session:
                await set_bot_setting(session, "poll_billing_interval", str(new_h))
            status = scheduler_mgr.get_status()
            await query.edit_message_text(
                text=format_settings_menu(status["metrics_interval_minutes"], new_h),
                parse_mode="HTML",
                reply_markup=get_settings_keyboard(status["metrics_interval_minutes"], new_h),
            )
        return
