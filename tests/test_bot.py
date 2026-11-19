"""Unit tests for Telegram bot formatters, keyboards, middleware, and push dispatcher."""

from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from telegram import CallbackQuery, Message, Update, User
from telegram.ext import ContextTypes

from config.settings import Settings
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
    callback_router,
    get_instance_by_identifier,
    global_error_handler,
)
from src.bot.keyboards import (
    get_action_confirm_keyboard,
    get_instance_actions_keyboard,
    get_instances_keyboard,
    get_main_menu_keyboard,
    get_settings_keyboard,
)
from src.bot.middleware import admin_only, is_admin
from src.database.models import Account, Base, BillingSnapshot, InstanceState
from src.scheduler.detector import IncidentAlert, IncidentSeverity, IncidentType


class TestFormatters:
    """Tests for HTML message templates and emoji helpers."""

    def test_status_emoji(self) -> None:
        """Verify correct status emoji mapping."""
        assert get_status_emoji("RUNNING") == "🟢"
        assert get_status_emoji("STOPPED") == "🔴"
        assert get_status_emoji("STARTING") == "🟡"
        assert get_status_emoji("TERMINATED") == "⚪"
        assert get_status_emoji(None) == "⚪"

    def test_start_and_help_message(self) -> None:
        """Verify start and help text formatting."""
        start_txt = format_start_message(123456789)
        assert "123456789" in start_txt
        assert "/status" in start_txt

        help_txt = format_help_message()
        assert "Two-Step Confirmation" in help_txt
        assert "/instances" in help_txt

    def test_status_overview(self) -> None:
        """Verify status overview formatting across accounts and instances."""
        acc1 = Account(
            account_id="acc_01",
            name="Prod Singapore",
            account_type="PAYG",
            region="ap-singapore-1",
            tenancy_ocid="ocid1.tenancy..1",
            compartment_id="ocid1.compartment..1",
            monthly_budget=50.0,
        )
        vm1 = InstanceState(
            instance_id="ocid1.instance..1",
            account_id="acc_01",
            region="ap-singapore-1",
            compartment_id="ocid1.compartment..1",
            display_name="prod-api",
            shape="VM.Standard.A1.Flex",
            lifecycle_state="RUNNING",
        )
        vm2 = InstanceState(
            instance_id="ocid1.instance..2",
            account_id="acc_01",
            region="ap-singapore-1",
            compartment_id="ocid1.compartment..1",
            display_name="backup-vm",
            shape="VM.Standard.E2.1.Micro",
            lifecycle_state="STOPPED",
        )

        overview = format_status_overview([acc1], [vm1, vm2], total_spend=12.50)
        assert "Total Akun Terdaftar:</b> 1 akun" in overview
        assert "🟢 1 Aktif" in overview
        assert "🔴 1 Mati" in overview
        assert "$12.50 USD" in overview

    def test_instance_detail(self) -> None:
        """Verify instance detail text formatting."""
        vm = InstanceState(
            instance_id="ocid1.instance..vm",
            account_id="acc_01",
            region="ap-singapore-1",
            compartment_id="ocid1.compartment..1",
            display_name="web-server",
            shape="VM.Standard.A1.Flex",
            public_ip="140.238.1.10",
            private_ip="10.0.0.5",
            lifecycle_state="RUNNING",
            latest_cpu_percent=14.8,
            last_seen=datetime(2026, 11, 17, 12, 0, 0, tzinfo=timezone.utc),
        )
        detail = format_instance_detail(vm, "Prod Account")
        assert "web-server" in detail
        assert "140.238.1.10" in detail
        assert "14.8%" in detail
        assert "RUNNING" in detail

    def test_billing_overview(self) -> None:
        """Verify billing overview and budget breach tags."""
        acc = Account(
            account_id="acc_01",
            name="Prod PAYG",
            account_type="PAYG",
            region="ap-singapore-1",
            tenancy_ocid="ocid1.tenancy..1",
            compartment_id="ocid1.compartment..1",
            monthly_budget=50.0,
        )
        snap = BillingSnapshot(
            account_id="acc_01",
            amount=25.0,
            currency="USD",
            billing_period="2026-11",
        )
        txt = format_billing_overview([acc], {"acc_01": snap}, {"acc_01": 75.0})
        assert "$25.00 USD" in txt
        assert "$75.00 USD" in txt
        assert "Over Budget" in txt

    def test_action_prompts_and_results(self) -> None:
        """Verify power action confirmation and result templates."""
        prompt = format_action_confirm_prompt("prod-db", "STOP")
        assert "prod-db" in prompt
        assert "STOP" in prompt

        success_res = format_action_result("prod-db", "START", success=True)
        assert "Berhasil" in success_res

        fail_res = format_action_result("prod-db", "STOP", success=False, error_msg="Timeout")
        assert "Gagal" in fail_res
        assert "Timeout" in fail_res

    def test_settings_menu(self) -> None:
        """Verify settings menu text."""
        menu = format_settings_menu(current_metrics=10, current_billing=6)
        assert "10 menit" in menu
        assert "6 jam" in menu


class TestKeyboards:
    """Tests for Inline Keyboard generation."""

    def test_main_menu_keyboard(self) -> None:
        """Verify main navigation keyboard buttons."""
        kb = get_main_menu_keyboard()
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "nav_status" in callbacks
        assert "nav_instances" in callbacks
        assert "nav_billing" in callbacks
        assert "nav_settings" in callbacks

    def test_instances_keyboard(self) -> None:
        """Verify instance list buttons generation."""
        vm = InstanceState(
            instance_id="ocid1.instance..btn_test",
            account_id="acc_01",
            region="ap-tokyo-1",
            compartment_id="comp",
            display_name="tokyo-node",
            shape="VM.Standard.A1.Flex",
            lifecycle_state="RUNNING",
        )
        kb = get_instances_keyboard([vm])
        first_btn = kb.inline_keyboard[0][0]
        assert "tokyo-node" in first_btn.text
        assert first_btn.callback_data == f"vm_detail:{vm.short_id}"
        assert len(first_btn.callback_data.encode("utf-8")) <= 64

    def test_callback_data_64_byte_limit_with_real_ocid(self) -> None:
        """Verify that all keyboard buttons stay strictly within Telegram's 64-byte callback_data limit."""
        real_ocid = (
            "ocid1.instance.oc1.ap-singapore-1.anzwsljrotfoceicgjjopconcmihscpvnkaqesxhyh7qttdddizwvmezvlia"
        )
        vm = InstanceState(
            instance_id=real_ocid,
            account_id="acc_01",
            region="ap-singapore-1",
            compartment_id="comp",
            display_name="production-vm",
            shape="VM.Standard.A1.Flex",
            lifecycle_state="RUNNING",
        )

        keyboards = [
            get_instances_keyboard([vm]),
            get_instance_actions_keyboard(real_ocid, "RUNNING"),
            get_instance_actions_keyboard(real_ocid, "STOPPED"),
            get_action_confirm_keyboard(real_ocid, "START"),
            get_action_confirm_keyboard(real_ocid, "STOP"),
            get_action_confirm_keyboard(real_ocid, "SOFTRESET"),
            get_main_menu_keyboard(),
            get_settings_keyboard(5, 6),
        ]

        for kb in keyboards:
            for row in kb.inline_keyboard:
                for btn in row:
                    cb = str(btn.callback_data or "")
                    assert cb != ""
                    cb_bytes = cb.encode("utf-8")
                    assert len(cb_bytes) <= 64, f"Button callback '{cb}' exceeds 64 bytes: {len(cb_bytes)} bytes"

    def test_instance_actions_keyboard(self) -> None:
        """Verify contextual power action buttons based on instance lifecycle state."""
        # When RUNNING: should show Stop and Reboot
        kb_running = get_instance_actions_keyboard("vm123", "RUNNING")
        running_cbs = [btn.callback_data for row in kb_running.inline_keyboard for btn in row]
        assert "act_prompt:vm123:STOP" in running_cbs
        assert "act_prompt:vm123:SOFTRESET" in running_cbs

        # When STOPPED: should show Start
        kb_stopped = get_instance_actions_keyboard("vm123", "STOPPED")
        stopped_cbs = [btn.callback_data for row in kb_stopped.inline_keyboard for btn in row]
        assert "act_prompt:vm123:START" in stopped_cbs

    def test_action_confirm_keyboard(self) -> None:
        """Verify two-step action confirmation keyboard (ADR-007)."""
        kb = get_action_confirm_keyboard("vm123", "STOP")
        row = kb.inline_keyboard[0]
        assert row[0].callback_data == "act_exec:vm123:STOP"
        assert row[1].callback_data == "vm_detail:vm123"

    def test_settings_keyboard(self) -> None:
        """Verify settings interval keyboard checkmark display."""
        kb = get_settings_keyboard(current_metrics_m=10, current_billing_h=6)
        row_m = kb.inline_keyboard[0]
        row_b = kb.inline_keyboard[1]

        # 10m should have checkmark
        m_texts = {btn.callback_data: btn.text for btn in row_m}
        assert "✅" in m_texts["set_metric:10"]
        assert "✅" not in m_texts["set_metric:5"]

        # 6h should have checkmark
        b_texts = {btn.callback_data: btn.text for btn in row_b}
        assert "✅" in b_texts["set_billing:6"]
        assert "✅" not in b_texts["set_billing:12"]


class TestMiddleware:
    """Tests for Telegram admin authorization security middleware."""

    @patch("src.bot.middleware.get_settings")
    def test_is_admin(self, mock_settings: MagicMock) -> None:
        """Verify is_admin checks against configured admin user ID."""
        mock_settings.return_value = Settings(
            TELEGRAM_BOT_TOKEN="mock_token",
            TELEGRAM_ADMIN_USER_ID=999888777,
        )
        assert is_admin(999888777) is True
        assert is_admin(111222333) is False
        assert is_admin(0) is False

    @patch("src.bot.middleware.get_settings")
    async def test_admin_only_decorator(self, mock_settings: MagicMock) -> None:
        """Verify admin_only permits admin and rejects unauthorized users."""
        mock_settings.return_value = Settings(
            TELEGRAM_BOT_TOKEN="mock_token",
            TELEGRAM_ADMIN_USER_ID=999888777,
        )

        inner_mock = AsyncMock(return_value="OK")
        guarded_handler = admin_only(inner_mock)

        # Case 1: Authorized admin user
        admin_update = MagicMock(spec=Update)
        admin_user = MagicMock(spec=User)
        admin_user.id = 999888777
        admin_update.effective_user = admin_user
        admin_context = MagicMock()

        result = await guarded_handler(admin_update, admin_context)
        assert result == "OK"
        inner_mock.assert_called_once()

        # Case 2: Unauthorized stranger
        inner_mock.reset_mock()
        stranger_update = MagicMock(spec=Update)
        stranger_user = MagicMock(spec=User)
        stranger_user.id = 123456
        stranger_user.username = "intruder"
        stranger_update.effective_user = stranger_user
        stranger_msg = AsyncMock(spec=Message)
        stranger_update.effective_message = stranger_msg
        stranger_update.callback_query = None

        result_blocked = await guarded_handler(stranger_update, admin_context)
        assert result_blocked is None
        inner_mock.assert_not_called()
        stranger_msg.reply_html.assert_called_once()
        args, kwargs = stranger_msg.reply_html.call_args
        msg_text = args[0] if args else kwargs.get("text", "")
        assert "Akses Ditolak" in msg_text


DBFixture = tuple[async_sessionmaker[AsyncSession], Any]


class TestHandlers:
    """Tests for bot handlers, short_id resolution, and error handling."""

    @pytest.fixture
    async def db_session(self, tmp_path: Path) -> AsyncGenerator[DBFixture, None]:
        db_file = tmp_path / "test_handler.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as session:
            acc = Account(
                account_id="acc_singapore",
                name="Singapore PAYG",
                account_type="PAYG",
                region="ap-singapore-1",
                tenancy_ocid="ocid1.tenancy..singapore",
                compartment_id="ocid1.compartment..singapore",
                monthly_budget=100.0,
            )
            vm = InstanceState(
                instance_id="ocid1.instance.oc1.ap-singapore-1.anzwsljrotfoceicgjjopconcmihscpvnkaqesxhyh7qttdddizwvmezvlia",
                account_id="acc_singapore",
                region="ap-singapore-1",
                compartment_id="ocid1.compartment..singapore",
                display_name="prod-singapore-vm",
                shape="VM.Standard.A1.Flex",
                lifecycle_state="RUNNING",
            )
            session.add(acc)
            session.add(vm)
            await session.commit()

        yield session_factory, engine
        await engine.dispose()

    async def test_get_instance_by_identifier(self, db_session: DBFixture) -> None:
        """Verify get_instance_by_identifier resolves both full OCID and 12-char short_id."""
        session_factory, _ = db_session
        long_ocid = "ocid1.instance.oc1.ap-singapore-1.anzwsljrotfoceicgjjopconcmihscpvnkaqesxhyh7qttdddizwvmezvlia"

        async with session_factory() as session:
            # 1. Lookup by full OCID
            inst_full = await get_instance_by_identifier(session, long_ocid)
            assert inst_full is not None
            assert inst_full.instance_id == long_ocid
            assert inst_full.display_name == "prod-singapore-vm"

            # 2. Lookup by short_id (12 chars)
            short_id = inst_full.short_id
            assert len(short_id) == 12
            inst_short = await get_instance_by_identifier(session, short_id)
            assert inst_short is not None
            assert inst_short.instance_id == long_ocid

            # 3. Lookup non-existent id
            inst_none = await get_instance_by_identifier(session, "non_existent_id")
            assert inst_none is None

    async def test_global_error_handler(self) -> None:
        """Verify global_error_handler logs unhandled errors and notifies user without crashing."""
        update = MagicMock(spec=Update)
        msg = AsyncMock(spec=Message)
        update.effective_message = msg
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.error = ValueError("Simulated unexpected failure")

        await global_error_handler(update, context)
        msg.reply_text.assert_called_once()
        args, _ = msg.reply_text.call_args
        assert "kesalahan internal" in args[0]

        # Case when update has no message
        update_empty = MagicMock(spec=Update)
        update_empty.effective_message = None
        await global_error_handler(update_empty, context)

    @patch("src.bot.handlers.get_settings")
    @patch("src.bot.middleware.get_settings")
    async def test_callback_router_vm_detail_with_short_id(
        self,
        mock_mid_settings: MagicMock,
        mock_hand_settings: MagicMock,
        db_session: DBFixture,
    ) -> None:
        """Verify callback_router resolves vm_detail query using 12-char short_id."""
        session_factory, _ = db_session
        settings = Settings(
            TELEGRAM_BOT_TOKEN="mock_token",
            TELEGRAM_ADMIN_USER_ID=999888777,
        )
        mock_mid_settings.return_value = settings
        mock_hand_settings.return_value = settings

        long_ocid = "ocid1.instance.oc1.ap-singapore-1.anzwsljrotfoceicgjjopconcmihscpvnkaqesxhyh7qttdddizwvmezvlia"
        vm = InstanceState(instance_id=long_ocid)
        short_id = vm.short_id

        update = MagicMock(spec=Update)
        user = MagicMock(spec=User)
        user.id = 999888777
        update.effective_user = user
        query = AsyncMock(spec=CallbackQuery)
        query.data = f"vm_detail:{short_id}"
        update.callback_query = query
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        with patch("src.bot.handlers.get_session", side_effect=session_factory):
            await callback_router(update, context)

        query.answer.assert_called_once()
        query.edit_message_text.assert_called_once()
        call_kwargs = query.edit_message_text.call_args.kwargs
        assert "prod-singapore-vm" in call_kwargs.get("text", "")

