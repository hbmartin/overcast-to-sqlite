import random
from collections.abc import Mapping
from mimetypes import guess_extension
from pathlib import Path

import dateutil

_user_agents = [
    "Overcast (+http://overcast.fm/; Apple Watch podcast app)",
    "Overcast/2021.22.1 CFNetwork/1240.0.4 Darwin/20.5.0",
    "Overcast/792 CFNetwork/1098.7 Darwin/19.0.0",
    "Overcast/2021.22.1 CFNetwork/978.0.7 Darwin/18.7.0",
    "Podcasts/1410.53 CFNetwork/1111 Darwin/19.0.0 (x86_64)",
    "Podcasts/1410.53 CFNetwork/978.0.7 Darwin/18.7.0",
]


def _headers_ua() -> dict:
    """Return a random User-Agent header to  avoid RSS and transcript download blocking.

    See https://github.com/opawg/user-agents-v2/blob/master/src/apps.json
    """
    return {"User-Agent": random.choice(_user_agents)}


def _parse_date_or_none(date_string: str) -> str | None:
    try:
        return dateutil.parser.parse(date_string).isoformat()
    except ValueError:
        return None


def _archive_path(db_path: str, archive_name: str) -> Path:
    return Path(db_path).parent / "archive" / archive_name


def _sanitize_for_path(s: str) -> str:
    return "".join(c for c in s if c not in ':/\\#-?%*|"<>').strip()


def _file_extension_for_type(headers: Mapping, fallback: str) -> str:
    content_type = fallback.split(";")[0]
    try:
        unsafe_content_type: str | None = headers.get("content-type")
        if (
            unsafe_content_type
            and unsafe_content_type
            not in [
                "application/octet-stream",
                "binary/octet-stream",
            ]
            and not (unsafe_content_type == "text/plain" and fallback != "text/plain")
        ):
            content_type = unsafe_content_type.split(";")[0]
    except KeyError:
        pass
    return guess_extension(content_type) or "." + content_type.split("/")[-1]
