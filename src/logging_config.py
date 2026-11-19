"""Logging configuration with conditional RotatingFileHandler for DEBUG mode."""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, Union


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[Union[Path, str]] = Path("logs/oci_bot.log"),
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
) -> None:
    """Configure root logger with console handler and conditional RotatingFileHandler.

    If log_level is DEBUG and log_file is specified, a RotatingFileHandler will be
    instantiated and attached to write debug logs to disk with detailed file and line
    number information. For any other level (INFO, WARNING, ERROR, CRITICAL), no file
    handler is attached, avoiding file I/O overhead on disk.

    Args:
        log_level: Desired log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_file: Path to destination log file if in DEBUG mode.
        max_bytes: Maximum size per log file before rotation in bytes (default 5MB).
        backup_count: Number of rotated backup files to retain (default 3).
    """
    normalized_level = log_level.strip().upper()
    numeric_level = getattr(logging, normalized_level, logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # 1. Setup StreamHandler (Console Output)
    console_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    console_formatter = logging.Formatter(fmt=console_format, datefmt="%Y-%m-%d %H:%M:%S")

    # Clear existing handlers to prevent duplicates if reconfigured
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        handler.close()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # 2. Conditional RotatingFileHandler (ONLY if DEBUG)
    if normalized_level == "DEBUG" and log_file is not None:
        target_path = Path(log_file)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        file_format = "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s"
        file_formatter = logging.Formatter(fmt=file_format, datefmt="%Y-%m-%d %H:%M:%S")

        file_handler = RotatingFileHandler(
            filename=str(target_path),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
