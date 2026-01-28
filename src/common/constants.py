# ====== Logging Constants ===== #
LOG_DIR = r"/logs"
LOG_ROTATION = "100 MB"
LOG_RETENTION = "30 days"
LOG_LEVEL = "DEBUG"
LOG_ENQUEUE = True
LOG_CONSOLE_OUTPUT = True
LOG_COLORIZE = True
LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{extra[tag]: <15}</cyan> | "
    "<level>{message}</level>"
)
