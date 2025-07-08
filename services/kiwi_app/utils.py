import uuid
import random

from global_config.logger import get_logger
from global_config.settings import global_settings
from global_utils.utils import datetime_now_utc

kiwi_logger = None

def init_logger(name=None):
    global kiwi_logger
    if kiwi_logger is None:
        # kiwi_logger = 
        return get_logger(
            name=name or "kiwi_app",
            # log_level=global_settings.LOG_LEVEL,
            # log_filename=global_settings.LOG_FILE_NAME,  #  + f".{datetime_now_utc()}.{random.randint(0, 100)}",
            # log_to_file=True,
        )
    return kiwi_logger

def get_kiwi_logger(name=None):
    global kiwi_logger
    if kiwi_logger is None:
        return init_logger(name)
    return kiwi_logger
