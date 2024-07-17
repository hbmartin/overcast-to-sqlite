from xml.etree.ElementTree import ElementTree

from .entities import (
    PCI,
    PSC,
    Chapter,
    ChapterType,
)
from .extractors import (
    extract_description_chapters,
    extract_psc_chapters,
    get_and_extract_pci_chapters,
)


def _align_chapters_to_transcripts() -> dict[str, str]:
    pass


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
        chapters[ChapterType.PSC] = extract_psc_chapters(psc_chapters)
    if (description := root.find("./description")) is not None:  # noqa: SIM102
        if (extracted := extract_description_chapters(description.text)) is not None:
            chapters[ChapterType.DESCRIPTION] = extracted
    return chapters
