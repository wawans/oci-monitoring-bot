"""Unit tests for conditional RotatingFileHandler and logging configuration."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Generator

import pytest

from config.settings import Settings
from src.logging_config import setup_logging


@pytest.fixture(autouse=True)
def clean_root_logger() -> Generator[None, None, None]:
    """Ensure root logger handlers are cleanly restored before and after each test."""
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    yield
    # Close and remove any added handlers
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    for handler in original_handlers:
        root.addHandler(handler)
    root.setLevel(original_level)


class TestConditionalLogging:
    """Test suite for setup_logging function and conditional RotatingFileHandler."""

    def test_setup_logging_info_does_not_create_file(self, tmp_path: Path) -> None:
        """When LOG_LEVEL is INFO, no file or folder should be created on disk."""
        target_log_file = tmp_path / "logs" / "oci_bot.log"
        setup_logging(log_level="INFO", log_file=target_log_file)

        logger = logging.getLogger("test_info")
        logger.info("Informational message")
        logger.warning("Warning message")

        # Verify no file or directory was created on disk
        assert not target_log_file.exists()
        assert not (tmp_path / "logs").exists()

        # Verify no RotatingFileHandler is attached
        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, RotatingFileHandler)]
        assert len(file_handlers) == 0

    def test_setup_logging_warning_does_not_create_file(self, tmp_path: Path) -> None:
        """When LOG_LEVEL is WARNING or ERROR, no file handler should be attached."""
        target_log_file = tmp_path / "warning.log"
        setup_logging(log_level="WARNING", log_file=target_log_file)

        logger = logging.getLogger("test_warn")
        logger.warning("Warning message")

        assert not target_log_file.exists()
        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, RotatingFileHandler)]
        assert len(file_handlers) == 0

    def test_setup_logging_debug_creates_file_and_records_logs(self, tmp_path: Path) -> None:
        """When LOG_LEVEL is DEBUG, RotatingFileHandler must be created and record logs."""
        target_log_file = tmp_path / "sub_dir" / "debug.log"
        setup_logging(log_level="DEBUG", log_file=target_log_file)

        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, RotatingFileHandler)]
        assert len(file_handlers) == 1
        assert root.level == logging.DEBUG

        # Write debug log message
        logger = logging.getLogger("test_debug")
        test_message = "Diagnostic execution marker 42"
        logger.debug(test_message)

        # Flush handler
        for h in file_handlers:
            h.flush()

        assert target_log_file.exists()
        content = target_log_file.read_text(encoding="utf-8")
        assert test_message in content
        assert "[DEBUG]" in content
        assert "test_debug" in content
        # Verify line number format (filename:lineno) is present
        assert "test_logging.py:" in content

    def test_setup_logging_rotation_triggers(self, tmp_path: Path) -> None:
        """RotatingFileHandler should rotate files when maxBytes is exceeded."""
        target_log_file = tmp_path / "rotate.log"
        # 100 bytes max per file, 2 backups
        setup_logging(
            log_level="DEBUG",
            log_file=target_log_file,
            max_bytes=100,
            backup_count=2,
        )

        logger = logging.getLogger("test_rotation")
        # Write enough lines to exceed 100 bytes multiple times
        for i in range(25):
            logger.debug("Line number %03d: logging some verbose test payload text", i)

        root = logging.getLogger()
        for h in root.handlers:
            h.flush()

        # Check that primary log file and at least one rotated backup exists
        assert target_log_file.exists()
        backup_file_1 = tmp_path / "rotate.log.1"
        assert backup_file_1.exists()

    def test_settings_log_configuration(self) -> None:
        """Settings model should validate and expose log configuration options."""
        custom_settings = Settings(
            LOG_LEVEL="debug",
            LOG_FILE_PATH="custom_logs/bot.log",
            LOG_FILE_MAX_BYTES=1048576,
            LOG_FILE_BACKUP_COUNT=5,
        )
        assert custom_settings.log_level == "debug"
        assert custom_settings.log_file_path == Path("custom_logs/bot.log")
        assert custom_settings.log_file_max_bytes == 1048576
        assert custom_settings.log_file_backup_count == 5
