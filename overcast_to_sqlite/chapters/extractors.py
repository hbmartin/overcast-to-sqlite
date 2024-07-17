import json
from contextlib import suppress
from pathlib import Path
from xml.etree import ElementTree

import requests

from .entities import (
    PSC,
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
    archive_path_json: Path | None,
) -> None | list[Chapter]:
    if archive_path_json is not None and archive_path_json.exists():
        chapters_json = json.loads(archive_path_json.read_text())
    else:
        response = requests.get(url, headers=headers)
        if not response.ok:
            print(f"⛔️ Error {response.status_code} fetching chapters {url}")
            return None
        chapters_json = response.json()
        if archive_path_json:
            archive_path_json.write_text(json.dumps(chapters_json))

    try:
        return [
            (int(c["startTime"]), c["title"], c.get("url"), c.get("img"))
            for c in chapters_json["chapters"]
        ]
    except (KeyError, ValueError, TypeError):
        print(f"Failed to extract PCI for {url} @ {archive_path_json}")
        return None


def extract_psc_chapters_from_file(feed_file: Path, guid: str) -> None | list[Chapter]:
    if not feed_file.exists():
        print(f"⛔️ File not found {feed_file}")
        return None

    try:
        root = ElementTree.fromstring(feed_file.read_text())
    except ElementTree.ParseError:
        print(f"Failed to parse podcast feed {feed_file}.")
        return None

    if (channel := root.find("./channel")) is None:
        print(f"Failed to find channel podcast feed {feed_file}.")
        return None

    for element in channel:
        if element.tag == "item":
            found_guid = element.find("guid")
            if found_guid is not None and found_guid.text == guid:
                if (psc_chapters := element.find(f"./{PSC}chapters")) is not None:
                    return extract_psc_chapters(psc_chapters)

                print(
                    f"Failed PSC chapters for episode {guid} in {feed_file}",
                )
                return None
    return None


def extract_psc_chapters(psc_chapters: ElementTree.Element) -> None | list[Chapter]:
    """Extract PSC chapters from XML.

    psc_chapters: ElementTree.Element is the element <psc:chapters>.
    """
    try:
        return [
            (_ts_to_secs(c.attrib["start"]), c.attrib["title"], None, None)
            for c in psc_chapters
        ]
    except (KeyError, ValueError, TypeError):
        print(f"Failed to extract PSC chapters {psc_chapters}")
        return None
