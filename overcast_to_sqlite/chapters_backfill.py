from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from podcast_chapter_tools.entities import ChapterType
from podcast_chapter_tools.extractors import (
    extract_description_chapters,
    extract_psc_chapters_from_file,
    get_and_extract_pci_chapters,
)

from overcast_to_sqlite.constants import BATCH_SIZE, CHAPTERS, FEEDS
from overcast_to_sqlite.datastore import Datastore
from overcast_to_sqlite.more_itertools import chunked
from overcast_to_sqlite.utils import _headers_ua, _sanitize_for_path


def backfill_chapters_description(db: Datastore) -> None:
    candidates = 0
    found = 0
    to_insert = []

    for url, guid, description in db.get_description_no_chapters():
        candidates += 1
        if (chapters := extract_description_chapters(description)) is not None:
            found += 1
            to_insert.extend(
                [(url, guid, ChapterType.DESCRIPTION.value, *c) for c in chapters],
            )
    if found > 0:
        print(f"Description chapters: {found} podcasts in {candidates} candidates")
    db.insert_chapters(to_insert)


def backfill_chapters_pci(db: Datastore, chapters_path: Path) -> None:
    candidates = 0
    found = 0
    chapters_path.mkdir(parents=True, exist_ok=True)

    def _get_and_extract(
        podcast: tuple[str, str, str, str],
    ) -> None | list[tuple[str, str, str, int, str, str | None, str | None]]:
        enc_url, guid, title, chap_url = podcast
        try:
            extracted = get_and_extract_pci_chapters(
                url=chap_url,
                headers=_headers_ua(),
                archive_path_json=chapters_path / f"{_sanitize_for_path(title)}.json",
            )
            if extracted is not None:
                return [(enc_url, guid, ChapterType.PCI.value, *c) for c in extracted]
        except Exception as e:  # noqa: BLE001
            print(f"Error fetching PCI chapters for {title}: {e}")
        return None

    no_pci_chapters = list(db.get_no_pci_chapters())
    chunks = chunked(no_pci_chapters, BATCH_SIZE)
    for batch in chunks:
        with ThreadPoolExecutor(max_workers=BATCH_SIZE) as executor:
            to_insert = []
            for result in executor.map(_get_and_extract, batch):
                candidates += 1
                if result is not None:
                    to_insert.extend(result)
                    found += 1
            db.insert_chapters(to_insert)
    if found > 0:
        print(f"PCI chapters: {found} podcasts in {candidates} candidates")


def backfill_chapters_psc(db: Datastore, feeds_root: Path) -> None:
    candidates = 0
    found = 0
    to_insert = []

    for url, guid, feed_title in db.get_no_psc_chapters():
        candidates += 1
        feed_file = feeds_root / f"{_sanitize_for_path(feed_title)}.xml"
        if (chapters := extract_psc_chapters_from_file(feed_file, guid)) is not None:
            found += 1
            to_insert.extend(
                [(url, guid, ChapterType.PSC.value, *c) for c in chapters],
            )
    if found > 0:
        print(f"PSC: {found} chapters in {candidates} candidates")
    db.insert_chapters(to_insert)


def backfill_all_chapters(db_path: str, archive_root: Path) -> None:
    db = Datastore(db_path)
    backfill_chapters_description(db)
    backfill_chapters_pci(db, archive_root / CHAPTERS)
    backfill_chapters_psc(db, archive_root / FEEDS)
