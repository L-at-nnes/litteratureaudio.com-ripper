import logging
import sys
from pathlib import Path


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("litteratureaudio")
    logger.setLevel(logging.DEBUG)

    log_file = Path("litteratureaudio.log")
    file_handler = logging.FileHandler(log_file, encoding="utf-8-sig")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(file_formatter)

    # Force UTF-8 on console for Windows (handles French accented characters)
    # On Windows, stdout may default to cp1252 which breaks accented chars
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass  # Python < 3.7 or stdout not a real file

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter("%(levelname)s: %(message)s")
    console_handler.setFormatter(console_formatter)

    # Avoid duplicate handlers if main() is called multiple times.
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    return logger

