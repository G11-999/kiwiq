import random
import uuid

from datetime import datetime, timezone
from functools import partial
from global_config.logger import get_logger
from global_utils import datetime_now_utc
from global_config.settings import global_settings

from kiwi_app.utils import get_kiwi_logger  # get_kiwi_logger as auth_logger

auth_logger = get_logger(
    name="kiwi_app.auth",
    # log_filename=global_settings.LOG_FILE_NAME,  #  + f".{datetime_now_utc()}.{random.randint(0, 100)}",
    # log_level=global_settings.LOG_LEVEL,
    # log_filename=global_settings.LOG_FILE_NAME + f".{datetime_now_utc()}.{random.randint(0, 100)}",
    # log_to_file=True,
)

# auth_logger = get_logger(
#     name="kiwi_app.auth",
#     log_level=global_settings.LOG_LEVEL,
#     log_filename=global_settings.LOG_FILE_NAME + f".{uuid.uuid4()}",
#     # log_dir=,
#     # log_to_console=,
#     log_to_file=True,
# )
