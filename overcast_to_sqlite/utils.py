from pathlib import Path

from typing import Optional

import dateutil


def _parse_date_or_none(date_string: str) -> Optional[str]:
    try:
        return dateutil.parser.parse(date_string).isoformat()
    except ValueError:
        return None


def archive_path(db_path: str, archive_name: str) -> Path:
    return Path(db_path).parent / "archive" / archive_name
