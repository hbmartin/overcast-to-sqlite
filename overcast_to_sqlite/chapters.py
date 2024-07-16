import re
from enum import StrEnum, auto
from typing import TypeAlias
from xml.etree.ElementTree import ElementTree

import requests

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


def _align_chapters_to_transcripts(
    chapters: dict[ChapterType, str],
    transcripts: dict[str, str],
) -> dict[str, str]:
    pass


def _ts_to_secs(time_string: str) -> int:
    """Converts a time stamp string to seconds."""
    time_parts = time_string.split(".")[0].split(":")
    seconds = int(time_parts[-1])
    if len(time_parts) > 1:
        seconds += 60 * int(time_parts[-2])
    if len(time_parts) > 2:
        try:
            seconds += 3600 * int(time_parts[-3])
        except ValueError:
            pass
    return seconds


def get_and_extract_pci_chapters(url: str, headers: dict) -> None | list[Chapter]:
    response = requests.get(url, headers=headers)
    if not response.ok:
        print(f"⛔️ Error {response.status_code} fetching chapters {url}")
        return None
    return [
        (int(c["startTime"]), c["title"], c.get("url"), c.get("img"))
        for c in response.json()["chapters"]
    ]


def _extract_desc_ts_and_title(ts_title: tuple[str, str]) -> Chapter:
    title = ts_title[1].strip()
    url = None
    if "<a" in title and "</a>" not in title:
        title += "</a>"
    if (m := _re_url.search(title)) is not None:
        url = m[0]
    return _ts_to_secs(ts_title[0]), title, url, None


def extract_chapters(
    root: ElementTree,
    headers: dict,
) -> dict[ChapterType, list[Chapter]]:
    chapters = {}
    if (el_pci_chapters := root.find(f"./{PCI}chapters")) is not None:
        chapters[ChapterType.PCI] = get_and_extract_pci_chapters(
            url=el_pci_chapters.attrib["url"],
            headers=headers,
        )
    if (psc_chapters := root.find(f"./{PSC}chapters")) is not None:
        chapters[ChapterType.PSC] = [
            (_ts_to_secs(c.attrib["start"]), c.attrib["title"], None, None)
            for c in psc_chapters
        ]
    if (description := root.find("./description")) is not None:
        if (extracted := extract_description_chapters(description.text)) is not None:
            chapters[ChapterType.DESCRIPTION] = extracted
    return chapters


def extract_description_chapters(description: str) -> None | list[Chapter]:
    desc_chapters = _description_chapter.findall(description)
    if len(desc_chapters) > 1:
        return [_extract_desc_ts_and_title(c) for c in desc_chapters]
    elif len(desc_chapters) == 1:
        retry_desc_chapters = _retry_description_chapter.findall(
            f"{desc_chapters[0][0]} {desc_chapters[0][1]}",
        )
        if len(retry_desc_chapters) > 1:
            return [_extract_desc_ts_and_title(c) for c in retry_desc_chapters]
    return None
