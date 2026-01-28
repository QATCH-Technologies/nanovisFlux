import sys
from pathlib import Path

import constants
from loguru import logger


def setup_logger(
    log_dir: str,
    level: str,
    console_output: bool,
):
    """
    Configures the nanovisFlux-wide logger.

    Args:
        console_output (bool): If True, prints logs to stdout/stderr.
        log_dir (str): Directory where log files will be saved.
        level (str): Minimum log level to capture (DEBUG, INFO, WARNING, ERROR).
    """
    logger.remove()
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_path / "nanovisFlux-{time:YYYY-MM-DD_HH-mm-ss}.log",
        format=constants.LOG_FORMAT,
        level=level,
        rotation=constants.LOG_ROTATION,
        retention=constants.LOG_RETENTION,
        enqueue=constants.LOG_ENQUEUE,
    )

    if console_output:
        logger.add(
            sys.stderr,
            format=constants.LOG_FORMAT,
            level=level,
            colorize=constants.LOG_COLORIZE,
            enqueue=constants.LOG_ENQUEUE,
        )
    return logger.bind(tag="Global")


log = setup_logger(
    log_dir=constants.LOG_DIR,
    level=constants.LOG_LEVEL,
    console_output=constants.LOG_CONSOLE_OUTPUT,
)


def get_logger(tag_name: str):
    """
    Returns a logger instance bound to a specific tag.
    """
    return logger.bind(tag=tag_name)
