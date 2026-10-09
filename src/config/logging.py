import logging
import sys


def setup_logging(level: str = "INFO") -> logging.Logger:
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )

    root_logger.setLevel(getattr(logging, level.upper()))
    root_logger.addHandler(handler)
    return root_logger


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
