# -*- coding: utf-8 -*-

import logging


DEFAULT_FORMATTER = logging.Formatter(
    '%(asctime)s: %(levelname)s (%(name)s): %(message)s', # Log format string
    '%a, %d %b %Y %H:%M:%S %Z' # Date format string (HTTP-compatible when GMT)
)

DEFAULT_HANDLER = logging.StreamHandler()
DEFAULT_HANDLER.setFormatter(DEFAULT_FORMATTER)
DEFAULT_HANDLER.setLevel(logging.DEBUG)


def getLogger(*args, **kwargs):
    logger = logging.getLogger(*args, **kwargs)
    logger.handlers = [DEFAULT_HANDLER]
    logger.propagate = 0
    logger.setLevel(logging.DEBUG)
    return logger