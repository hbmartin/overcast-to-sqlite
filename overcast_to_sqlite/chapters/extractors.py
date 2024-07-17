from contextlib import suppress
from pathlib import Path
from xml.etree import ElementTree

import requests

from .entities import (
    Chapter,
    _description_chapter,
    _re_url,
    _retry_description_chapter,
)


def _ts_to_secs(time_string: str) -> int:
    """Convert a time stamp string to seconds."""
    time_parts = time_string.split(".")[0].split(":")
    seconds = int(time_parts[-1])
    if len(time_parts) > 1:
        seconds += 60 * int(time_parts[-2])
    if len(time_parts) > 2:  # noqa: PLR2004
        with suppress(ValueError):
            seconds += 3600 * int(time_parts[-3])
    return seconds


def extract_description_chapters(description: str) -> None | list[Chapter]:
    desc_chapters = _description_chapter.findall(description)
    if len(desc_chapters) > 1:
        return [_extract_desc_ts_and_title(c) for c in desc_chapters]
    if len(desc_chapters) == 1:
        retry_desc_chapters = _retry_description_chapter.findall(
            f"{desc_chapters[0][0]} {desc_chapters[0][1]}",
        )
        if len(retry_desc_chapters) > 1:
            return [_extract_desc_ts_and_title(c) for c in retry_desc_chapters]
    return None


def _extract_desc_ts_and_title(ts_title: tuple[str, str]) -> Chapter:
    title = ts_title[1].strip()
    if "<a" in title and "</a>" not in title:
        title += "</a>"

    url = m[0] if (m := _re_url.search(title)) is not None else None

    return _ts_to_secs(ts_title[0]), title, url, None


def get_and_extract_pci_chapters(
    url: str,
    headers: dict,
    archive: Path | None,
) -> None | list[Chapter]:
    response = requests.get(url, headers=headers)
    if not response.ok:
        print(f"⛔️ Error {response.status_code} fetching chapters {url}")
        return None
    if archive:
        archive.mkdir(parents=True, exist_ok=True)
        # TODO: fix this path
        archive.joinpath(f"{url.split('/')[-1]}.json").write_text(response.text)

    try:
        return [
            (int(c["startTime"]), c["title"], c.get("url"), c.get("img"))
            for c in response.json()["chapters"]
        ]
    except (KeyError, ValueError):
        print(f"Failed to extract PCI {url}\n{response.text}")
        return None


def extract_psc_chapters(psc_chapters: ElementTree.Element) -> None | list[Chapter]:
    try:
        return [
            (_ts_to_secs(c.attrib["start"]), c.attrib["title"], None, None)
            for c in psc_chapters
        ]
    except (KeyError, ValueError):
        print(f"Failed to extract PSC chapters {psc_chapters}")
        return None
