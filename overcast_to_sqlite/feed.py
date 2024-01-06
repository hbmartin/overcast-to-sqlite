from pathlib import Path
from typing import Dict, Tuple, List, Any, Optional
import xml.etree.ElementTree as ET
from datetime import datetime
import requests

from overcast_to_sqlite.constants import (
    ENCLOSURE_URL,
    FEED_XML_URL,
    XML_URL,
    TITLE,
    DESCRIPTION,
)
from overcast_to_sqlite.utils import _parse_date_or_none


def _element_to_dict(element: ET.Element) -> Dict[str, Any]:
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
    xml_url: str, title: str, archive_dir: Optional[Path], verbose: bool
) -> Tuple[Dict, List[Dict]]:
    response = requests.get(xml_url)
    now = datetime.now().isoformat()
    if response.status_code != 200:
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
        with open(archive_dir / f"{title}.xml", "w") as f:
            f.write(xml_string)
    try:
        root = ET.fromstring(xml_string)
    except ET.ParseError:
        print(f"Failed to parse podcast feed {xml_url}.\n{response.headers}")
        return {
            XML_URL: xml_url,
            "lastUpdated": now,
            "errorCode": -1,
        }, []

    if (channel := root.find("./channel")) is None:
        raise ValueError("Could not find channel element")

    return _extract_from_feed_xml(channel, now, xml_url)


def _extract_from_feed_xml(
    channel: ET.Element, now: str, xml_url: str
) -> Tuple[Dict, List[Dict]]:
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
