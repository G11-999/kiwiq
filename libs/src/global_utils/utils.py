from functools import partial
from datetime import datetime, timezone

datetime_now_utc = partial(datetime.now, timezone.utc)
