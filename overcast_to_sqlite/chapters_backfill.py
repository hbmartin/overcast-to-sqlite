from overcast_to_sqlite.chapters import (
    ChapterType,
    extract_description_chapters,
    get_and_extract_pci_chapters,
)
from overcast_to_sqlite.datastore import Datastore
from overcast_to_sqlite.utils import _headers_ua


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
    print(f"Found {found} chapters in {candidates} candidates")
    db.insert_chapters(to_insert)


def backfill_chapters_pci(db: Datastore) -> None:
    candidates = 0
    found = 0
    to_insert = []

    for url, guid, chap_url in db.get_description_no_pci_chapters():
        print(f"Checking {url} => {chap_url}")
        # TODO: parallelize this and save chapters to archive
        candidates += 1
        if (
            chapters := get_and_extract_pci_chapters(chap_url, _headers_ua())
        ) is not None:
            found += 1
            to_insert.extend(
                [(url, guid, ChapterType.PCI.value, *c) for c in chapters],
            )
    print(f"Found {found} chapters in {candidates} candidates")
    db.insert_chapters(to_insert)


if __name__ == "__main__":
    db = Datastore("overcast.db")
    backfill_chapters_pci(db)
