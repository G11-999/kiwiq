
from datetime import datetime, timezone
from functools import partial
from global_config.logger import get_logger

auth_logger = get_logger('kiwi_app.auth')

datetime_now_utc = partial(datetime.now, timezone.utc)

