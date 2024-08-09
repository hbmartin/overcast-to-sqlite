from typing import Any
from xml.etree import ElementTree

from podcast_chapter_tools.entities import PCI, PSC, Chapter
from podcast_chapter_tools.extractors import (
    extract_description_chapters,
    extract_psc_chapters,
    get_and_extract_pci_chapters,
)

from overcast_to_sqlite.constants import ENCLOSURE_URL, FEED_XML_URL, TITLE
from overcast_to_sqlite.utils import _headers_ua, _parse_date_or_none


def _element_to_dict(element: ElementTree.Element) -> dict[str, Any]:
    element_dict = {}
    tag = (
        element.tag.replace("{http://www.itunes.com/dtds/podcast-1.0.dtd}", "itunes:")
        .replace("{https://podcastindex.org/namespace/1.0}", "podcast:")
        .replace(
            "{https://github.com/Podcastindex-org/podcast-namespace/blob/main/docs/1.0.md}",
            "podcast:",
        )
        .replace("{http://a9.com/-/spec/opensearchrss/1.0/}", "openSearch:")
        .replace("{http://fireside.fm/modules/rss/fireside}", "fireside:")
        .replace("{http://podlove.org/simple-chapters}", "psc:")
        .replace("{http://purl.org/dc/elements/1.1/}", "dc:")
        .replace("{http://purl.org/rss/1.0/modules/content/}", "content:")
        .replace("{http://purl.org/rss/1.0/modules/slash/}", "slash:")
        .replace("{http://purl.org/rss/1.0/modules/syndication/}", "sy:")
        .replace("{http://search.yahoo.com/mrss/}", "media:")
        .replace("{http://web.resource.org/cc/}", "cc:")
        .replace("{http://www.georss.org/georss}", "georss:")
        .replace("{http://www.google.com/schemas/play-podcasts/1.0}", "googleplay:")
        .replace("{http://www.rawvoice.com/rawvoiceRssModule/}", "rawvoice:")
        .replace("{http://www.rssboard.org/media-rss}", "rssboard:")
        .replace("{http://www.spotify.com/ns/rss}", "spotify:")
        .replace("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}", "rdf:")
        .replace("{http://www.w3.org/2003/01/geo/wgs84_pos#}", "geo:")
        .replace("{http://www.w3.org/2005/Atom}", "atom:")
        .replace("{https://feed.press/xmlns}", "feedpress:")
        .replace("{https://omny.fm/rss-extensions}", "omny:")
        .replace("{https://schema.acast.com/1.0/}", "acast:")
        .replace("{http://wellformedweb.org/CommentAPI/}", "wfw:")
        .replace("{https://w3id.org/rp/v1}", "radiopublic:")
    )
    if element.text and not element.text.isspace():
        if "date" in tag.lower():
            element_dict[tag] = _parse_date_or_none(element.text) or element.text
        else:
            element_dict[tag] = element.text
    for attr in element.attrib:
        element_dict[f"{tag}:{attr}"] = element.attrib[attr]

    return element_dict


def extract_chapters(
    root: ElementTree.Element,
    *,
    fetch_pci: bool = False,
) -> list[Chapter]:
    chapters: list[Chapter] = []
    if fetch_pci and (el_pci_chapters := root.find(f"./{PCI}chapters")) is not None:
        if (
            chaps := get_and_extract_pci_chapters(
                url=el_pci_chapters.attrib["url"],
                headers=_headers_ua(),
                archive_path_json=None,
            )
        ) is not None:
            chapters.extend(chaps)
    if (psc_chapters := root.find(f"./{PSC}chapters")) is not None:
        if (chaps := extract_psc_chapters(psc_chapters)) is not None:
            chapters.extend(chaps)
    if (description := root.find("./description")) is not None and (
        desc_text := description.text
    ) is not None:
        if (chaps := extract_description_chapters(desc_text)) is not None:
            chapters.extend(chaps)
    return chapters


def extract_ep_attrs(
    xml_url: str,
    element: ElementTree.Element,
) -> None | tuple[dict[str, Any], list[Chapter]]:
    ep_attrs = {FEED_XML_URL: xml_url}
    for ep_el in element:
        ep_attrs.update(_element_to_dict(ep_el))

    if "enclosure:url" in ep_attrs:
        ep_attrs[ENCLOSURE_URL] = ep_attrs.pop("enclosure:url").split("?")[0]
        # Need to figure out how to extract chapters more cheaply, this is expensive
        # to perform across all episodes.
        return ep_attrs, []

    print(f"Skipping episode without enclosure URL: {ep_attrs.get(TITLE)}")
    return None
