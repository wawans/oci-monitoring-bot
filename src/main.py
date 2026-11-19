"""Main application runner connecting bot router, background scheduler, and database."""

import asyncio
import logging
import signal
import sys
from pathlib import Path
from typing import Optional

from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from config.parser import load_accounts_config
from config.settings import get_settings
from src.bot.handlers import (
    billing_command,
    callback_router,
    dispatch_incident_push_alert,
    help_command,
    instances_command,
    settings_command,
    start_command,
    status_command,
)
from src.database.connection import (
    close_db,
    get_bot_setting,
    get_engine,
    get_session,
    get_session_factory,
    init_db,
    sync_accounts_to_db,
)
from src.logging_config import setup_logging
from src.oci_services.billing import BillingService
from src.oci_services.client_factory import OCIClientFactory
from src.oci_services.compute import ComputeService
from src.oci_services.monitoring import MonitoringService
from src.scheduler.detector import IncidentAlert
from src.scheduler.manager import SchedulerManager

logger = logging.getLogger("oci_bot")


def build_telegram_application(
    token: str,
    scheduler_mgr: SchedulerManager,
    client_factory: OCIClientFactory,
    compute_service: ComputeService,
) -> Application:
    """Build and configure python-telegram-bot Application instance."""
    app = Application.builder().token(token).build()

    # Store shared services in bot_data
    app.bot_data["scheduler_manager"] = scheduler_mgr
    app.bot_data["client_factory"] = client_factory
    app.bot_data["compute_service"] = compute_service

    # Register command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("instances", instances_command))
    app.add_handler(CommandHandler("billing", billing_command))
    app.add_handler(CommandHandler("settings", settings_command))

    # Register callback query router
    app.add_handler(CallbackQueryHandler(callback_router))

    return app


async def main_async() -> None:
    """Main asynchronous application entry point."""
    settings = get_settings()
    setup_logging(
        log_level=settings.log_level,
        log_file=settings.log_file_path,
        max_bytes=settings.log_file_max_bytes,
        backup_count=settings.log_file_backup_count,
    )
    logger.info("Starting OCI Multi-Account Telegram Monitoring Bot...")

    # 1. Initialize SQLite Database (WAL mode)
    await init_db(settings.database_url)

    # 2. Load accounts configuration
    accounts = []
    cfg_path = Path(settings.accounts_config_path)
    if cfg_path.is_file():
        try:
            accounts = load_accounts_config(cfg_path)
            logger.info("Loaded %d accounts from %s", len(accounts), cfg_path)
        except Exception as e:
            logger.error("Failed loading accounts config: %s", e)
    else:
        logger.warning(
            "Accounts config not found at %s. Please create it from config/accounts.yaml.example.",
            cfg_path,
        )

    # 3. Synchronize accounts into SQLite database
    if accounts:
        async with get_session() as session:
            await sync_accounts_to_db(accounts, session)

    # 4. Initialize OCI Client Factory & Services
    client_factory = OCIClientFactory()
    client_factory.initialize_clients(accounts)

    compute_service = ComputeService()
    monitoring_service = MonitoringService()
    billing_service = BillingService()

    # Verify OCI credentials handshake
    if client_factory.bundles:
        logger.info("Verifying OCI credential handshakes...")
        handshakes = await client_factory.verify_all_handshakes()
        for acc_id, ok in handshakes.items():
            status_text = "PASSED" if ok else "FAILED"
            logger.info("  Account '%s' Handshake: %s", acc_id, status_text)

    # 5. Check if Telegram credentials are configured
    if not settings.is_telegram_configured:
        logger.warning(
            "TELEGRAM_BOT_TOKEN or TELEGRAM_ADMIN_USER_ID not configured in .env. "
            "Please configure them to start the interactive Telegram bot."
        )
        return

    # 6. Build Telegram Application
    dummy_scheduler = SchedulerManager(
        client_factory, compute_service, monitoring_service, billing_service, get_session_factory()
    )
    application = build_telegram_application(
        settings.telegram_bot_token,
        dummy_scheduler,
        client_factory,
        compute_service,
    )

    # 7. Setup Watchdog Alert Callback (ADR-002: Push to Admin DM)
    async def alert_callback(alert: IncidentAlert) -> None:
        await dispatch_incident_push_alert(
            application.bot,
            settings.telegram_admin_user_id,
            alert,
        )

    # 8. Start Background Scheduler
    # Retrieve persisted intervals or use defaults
    async with get_session() as session:
        stored_m = await get_bot_setting(session, "poll_metrics_interval")
        stored_b = await get_bot_setting(session, "poll_billing_interval")

    m_interval = int(stored_m) if stored_m else settings.default_metrics_interval_minutes
    b_interval = int(stored_b) if stored_b else settings.default_billing_interval_hours

    scheduler_mgr = SchedulerManager(
        client_factory=client_factory,
        compute_service=compute_service,
        monitoring_service=monitoring_service,
        billing_service=billing_service,
        session_factory=get_session_factory(),
        alert_callback=alert_callback,
    )
    application.bot_data["scheduler_manager"] = scheduler_mgr
    scheduler_mgr.start(metrics_interval_minutes=m_interval, billing_interval_hours=b_interval)

    # 9. Start Bot Polling
    logger.info("Bot is now running. Listening for Telegram updates...")
    await application.initialize()
    await application.start()
    if application.updater:
        await application.updater.start_polling()

    # Graceful stop handler
    stop_event = asyncio.Event()

    def _sig_handler(*_: object) -> None:
        logger.info("Shutdown signal received. Stopping gracefully...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _sig_handler)
        except NotImplementedError:
            pass

    await stop_event.wait()

    # Shutdown sequence
    logger.info("Stopping Telegram polling...")
    if application.updater:
        await application.updater.stop()
    await application.stop()
    await application.shutdown()

    logger.info("Stopping background scheduler...")
    scheduler_mgr.shutdown(wait=False)

    logger.info("Closing database engine...")
    await close_db()
    logger.info("OCI Monitoring Bot successfully terminated.")


def main() -> None:
    """CLI entry point."""
    try:
        asyncio.run(main_async())
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
