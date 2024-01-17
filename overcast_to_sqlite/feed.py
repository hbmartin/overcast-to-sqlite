from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import requests

from .constants import (
    DESCRIPTION,
    ENCLOSURE_URL,
    FEED_XML_URL,
    TITLE,
    XML_URL,
)
from .exceptions import NoChannelInFeedError
from .utils import _parse_date_or_none


def _element_to_dict(element: ElementTree.Element) -> dict[str, Any]:
    element_dict = {}
    tag = (
        element.tag.replace("{http://www.itunes.com/dtds/podcast-1.0.dtd}", "itunes:")
        .replace("{https://podcastindex.org/namespace/1.0}", "podcast:")
        .replace(
            "{https://github.com/Podcastindex-org/podcast-namespace/blob/main/docs/1.0.md}",
            "podcast:",
        )
        .replace("{http://www.w3.org/2005/Atom}", "atom:")
        .replace("{http://purl.org/rss/1.0/modules/content/}", "content:")
        .replace("{http://purl.org/rss/1.0/modules/syndication/}", "sy:")
        .replace("{http://web.resource.org/cc/}", "cc:")
        .replace("{http://search.yahoo.com/mrss/}", "media:")
        .replace("{http://www.google.com/schemas/play-podcasts/1.0}", "googleplay:")
        .replace("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}", "rdf:")
        .replace("{http://a9.com/-/spec/opensearchrss/1.0/}", "openSearch:")
        .replace("{http://www.w3.org/2003/01/geo/wgs84_pos#}", "geo:")
        .replace("{http://www.rawvoice.com/rawvoiceRssModule/}", "rawvoice:")
        .replace("{http://www.spotify.com/ns/rss}", "spotify:")
        .replace("{http://fireside.fm/modules/rss/fireside}", "fireside:")
        .replace("{https://feed.press/xmlns}", "feedpress:")
        .replace("{https://schema.acast.com/1.0/}", "acast:")
        .replace("{https://omny.fm/rss-extensions}", "omny:")
        .replace("{{https://w3id.org/rp/v1}", "radiopublic:")
    )
    if element.text and not element.text.isspace():
        if "date" in tag.lower():
            element_dict[tag] = _parse_date_or_none(element.text) or element.text
        else:
            element_dict[tag] = element.text
    for attr in element.attrib:
        element_dict[f"{tag}:{attr}"] = element.attrib[attr]

    return element_dict


def fetch_xml_and_extract(
    xml_url: str,
    title: str,
    archive_dir: Path | None,
    verbose: bool,
) -> tuple[dict, list[dict]]:
    """Fetch XML feed and extract all feed and episode tags and attributes."""
    response = requests.get(xml_url)
    now = datetime.now(tz=timezone.utc).isoformat()
    if not response.ok:
        print(f"Failed to fetch podcast feed {xml_url}.\n{response.headers}")
        return {
            XML_URL: xml_url,
            "lastUpdated": now,
            "errorCode": response.status_code,
        }, []

    xml_string = response.text
    if archive_dir:
        archive_dir.mkdir(parents=True, exist_ok=True)
        if verbose:
            print(f"Saving feed XML to {archive_dir}/{title}.xml")
        archive_dir.joinpath(f"{title}.xml").write_text(xml_string)
    try:
        root = ElementTree.fromstring(xml_string)
    except ElementTree.ParseError:
        print(f"Failed to parse podcast feed {xml_url}.\n{response.headers}")
        return {
            XML_URL: xml_url,
            "lastUpdated": now,
            "errorCode": -1,
        }, []

    if (channel := root.find("./channel")) is None:
        raise NoChannelInFeedError

    return _extract_from_feed_xml(channel, now, xml_url)


def _extract_from_feed_xml(
    channel: ElementTree.Element,
    now: str,
    xml_url: str,
) -> tuple[dict, list[dict]]:
    feed_attrs = {XML_URL: xml_url, "lastUpdated": now}
    episodes = []
    for element in channel:
        if element.tag == "item":
            ep_attrs = {FEED_XML_URL: xml_url}
            for ep_el in element:
                ep_attrs.update(_element_to_dict(ep_el))
            if "enclosure:url" in ep_attrs:
                ep_attrs[ENCLOSURE_URL] = ep_attrs.pop("enclosure:url")
                episodes.append(ep_attrs)
        else:
            feed_attrs.update(_element_to_dict(element))
    feed_attrs[TITLE] = feed_attrs.get(TITLE, "").strip()
    feed_attrs[DESCRIPTION] = feed_attrs.get(DESCRIPTION, "").strip()

    return feed_attrs, episodes
