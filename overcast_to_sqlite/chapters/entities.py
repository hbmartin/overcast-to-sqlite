import re
from enum import StrEnum, auto
from typing import TypeAlias

PCI = "{https://podcastindex.org/namespace/1.0}"
PSC = "{http://podlove.org/simple-chapters}"

# start time, content title, optional URL, optional image URL
Chapter: TypeAlias = tuple[int, str, str | None, str | None]


class ChapterType(StrEnum):
    DESCRIPTION = auto()
    GEMINI = auto()
    ID3 = auto()
    OPENAI = auto()
    PCI = auto()
    PSC = auto()
    SONNET = auto()


_description_chapter = re.compile(
    pattern=r">?\s?[(\[]?(\d{0,2}:?\d{1,2}:\d{2})[\])]?[\s-]*([^\[(]+?)[$<]",
    flags=re.MULTILINE,
)

_retry_description_chapter = re.compile(
    pattern=r"(\d{0,2}:?\d{1,2}:\d{2})[\])]?[\s-]*([^\[(]+?)(?=\d{1,2}:)",
    flags=re.MULTILINE,
)

_re_url = re.compile(r"(?P<url>https?://\S+)", re.IGNORECASE)
