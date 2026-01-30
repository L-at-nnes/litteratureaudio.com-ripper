import io
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
    # Create a proper UTF-8 stream wrapper for the console handler
    if sys.platform == "win32":
        import os
        os.environ["PYTHONIOENCODING"] = "utf-8"
        # Wrap stderr in a UTF-8 TextIOWrapper to ensure proper encoding
        # This works even when PowerShell defaults to cp1252
        try:
            utf8_stderr = io.TextIOWrapper(
                sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True
            )
            console_handler = logging.StreamHandler(utf8_stderr)
        except AttributeError:
            # Fallback if buffer not available (e.g., IDE console)
            console_handler = logging.StreamHandler()
    else:
        console_handler = logging.StreamHandler()

    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter("%(levelname)s: %(message)s")
    console_handler.setFormatter(console_formatter)

    # Avoid duplicate handlers if main() is called multiple times.
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    return logger

