"""Security middleware ensuring strict admin user whitelist verification."""

import functools
import logging
from collections.abc import Callable
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

from config.settings import get_settings

logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    """Check if the provided Telegram user ID matches configured TELEGRAM_ADMIN_USER_ID."""
    admin_id = get_settings().telegram_admin_user_id
    return admin_id > 0 and user_id == admin_id


def admin_only(
    handler: Callable[[Update, ContextTypes.DEFAULT_TYPE], Any]
) -> Callable[[Update, ContextTypes.DEFAULT_TYPE], Any]:
    """Decorator guarding bot handlers to allow only authorized admin access."""

    @functools.wraps(handler)
    async def wrapper(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        user = update.effective_user
        admin_id = get_settings().telegram_admin_user_id

        if user is None or admin_id <= 0 or user.id != admin_id:
            user_info = f"ID: {user.id} (@{user.username})" if user else "Unknown User"
            logger.warning("Unauthorized access attempt blocked from %s", user_info)

            # Silently reject or provide clear rejection message
            if update.effective_message:
                await update.effective_message.reply_html(
                    "⛔ <b>Akses Ditolak</b>\n"
                    "Anda tidak memiliki izin otorisasi untuk menggunakan bot monitoring ini."
                )
            elif update.callback_query:
                await update.callback_query.answer("⛔ Akses ditolak.", show_alert=True)
            return None

        return await handler(update, context, *args, **kwargs)

    return wrapper
