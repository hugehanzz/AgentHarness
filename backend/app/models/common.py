from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import get_settings


def app_now() -> datetime:
    timezone_name = get_settings().app_timezone
    return datetime.now(ZoneInfo(timezone_name)).replace(tzinfo=None)
