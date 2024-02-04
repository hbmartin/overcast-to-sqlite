from pathlib import Path

import dateutil


def _parse_date_or_none(date_string: str) -> str | None:
    try:
        return dateutil.parser.parse(date_string).isoformat()
    except ValueError:
        return None


def _archive_path(db_path: str, archive_name: str) -> Path:
    return Path(db_path).parent / "archive" / archive_name


def _sanitize_for_path(s: str) -> str:
    return "".join(c for c in s if c not in ':/\\#-?%*|"<>').strip()
