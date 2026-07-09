import sys
from pathlib import Path

from loguru import logger

LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)

FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | " "{level: <8} | " "{name}:{function}:{line} - " "{message}"
)


def setup_logger() -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        format=CONSOLE_FORMAT,
        level="INFO",
        colorize=True,
        enqueue=True,
    )
    log_file = LOG_DIR / "{time:YYYY-MM-DD}.log"
    logger.add(
        str(log_file),
        format=FILE_FORMAT,
        level="DEBUG",
        rotation="10 MB",
        retention="30 days",
        compression="zip",
        enqueue=True,
    )


setup_logger()
