"""Telegram bot layer exposing middleware, formatters, keyboards, and handlers."""

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
    get_status_emoji,
)
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
from src.bot.keyboards import (
    get_action_confirm_keyboard,
    get_instance_actions_keyboard,
    get_instances_keyboard,
    get_main_menu_keyboard,
    get_settings_keyboard,
)
from src.bot.middleware import admin_only, is_admin

__all__ = [
    "admin_only",
    "billing_command",
    "callback_router",
    "dispatch_incident_push_alert",
    "format_action_confirm_prompt",
    "format_action_result",
    "format_billing_overview",
    "format_help_message",
    "format_instance_detail",
    "format_settings_menu",
    "format_start_message",
    "format_status_overview",
    "generate_cpu_chart",
    "get_action_confirm_keyboard",
    "get_instance_actions_keyboard",
    "get_instances_keyboard",
    "get_main_menu_keyboard",
    "get_settings_keyboard",
    "get_status_emoji",
    "help_command",
    "instances_command",
    "is_admin",
    "settings_command",
    "start_command",
    "status_command",
]
