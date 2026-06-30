from __future__ import annotations

import logging
from pathlib import Path


LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
LOG_FILE = LOG_DIR / "mitsubridge.log"


def setup_logger(name: str = "mitsubridge", debug: bool = False) -> logging.Logger:
    """Create a logger that writes all BLE traffic to logs/mitsubridge.log."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        formatter = logging.Formatter(
            fmt="%(asctime)s.%(msecs)03d %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter("%(message)s"))
        console_handler.setLevel(logging.DEBUG if debug else logging.INFO)
        logger.addHandler(console_handler)

    for handler in logger.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            handler.setLevel(logging.DEBUG if debug else logging.INFO)

    if debug:
        enable_bleak_debug()

    return logger


def enable_bleak_debug() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    bleak_logger = logging.getLogger("bleak")
    bleak_logger.setLevel(logging.DEBUG)
    bleak_logger.propagate = False

    if any(getattr(handler, "_mitsubridge_bleak", False) for handler in bleak_logger.handlers):
        return

    formatter = logging.Formatter(
        fmt="%(asctime)s.%(msecs)03d %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)
    file_handler._mitsubridge_bleak = True  # type: ignore[attr-defined]
    bleak_logger.addHandler(file_handler)
