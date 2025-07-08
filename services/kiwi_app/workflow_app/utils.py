import random
import uuid

from global_config.logger import get_logger
from global_config.settings import global_settings
from global_utils.utils import datetime_now_utc

from kiwi_app.utils import get_kiwi_logger  # get_kiwi_logger as auth_logger

workflow_logger = get_logger(
    name="kiwi_app.workflow",
    # log_filename=global_settings.LOG_FILE_NAME,  #  + f".{datetime_now_utc()}.{random.randint(0, 100)}",
    # log_level=global_settings.LOG_LEVEL,
    # log_filename=global_settings.LOG_FILE_NAME + f".{datetime_now_utc()}.{random.randint(0, 100)}",
    # log_to_file=True,
)


# workflow_logger = get_logger(
#     name="kiwi_app.workflow",
#     log_level=global_settings.LOG_LEVEL,
#     log_filename=global_settings.LOG_FILE_NAME + f".{uuid.uuid4()}",
#      log_to_file=True,
# )

