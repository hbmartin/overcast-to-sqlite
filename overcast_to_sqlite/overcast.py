import json
from pathlib import Path
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, Optional, Tuple, List, Any, Iterable

from requests import Session
from overcast_to_sqlite.constants import (
    OVERCAST_ID,
    INCLUDE_PODCAST_IDS,
    TITLE,
    SMART,
    SORTING,
)
from overcast_to_sqlite.utils import _parse_date_or_none


def auth_and_save_cookies(email: str, password: str, auth_json_path: str) -> None:
    session = Session()
    response = session.post(
        "https://overcast.fm/login?then=account",
        data={"email": email, "password": password},
        allow_redirects=False,
    )

    if "Incorrect password" in response.text:
        raise Exception("Incorrect password")
    cookies = session.cookies.get_dict()
    if "o" not in cookies:
        raise Exception("Failed to authenticate")

    print("Authenticated successfully. Saving session.")
    if Path(auth_json_path).exists():
        auth_data = json.load(open(auth_json_path))
    else:
        auth_data = {}
    auth_data["overcast"] = cookies
    open(auth_json_path, "w").write(json.dumps(auth_data, indent=4) + "\n")


def load_cookies(auth_json_path: str) -> Session:
    with open(auth_json_path) as f:
        cookies = json.load(f)["overcast"]
        print(f"Loaded auth cookie: {cookies} ...")
        session = Session()
        session.cookies.update(cookies)
        return session


def fetch_opml(auth_json_path: str, archive_dir: Optional[Path], verbose: bool) -> str:
    session = load_cookies(auth_json_path)
    if verbose:
        print("Fetching latest OPML from Overcast")
    response = session.get(
        "https://overcast.fm/account/export_opml/extended", timeout=None
    )
    if response.status_code != 200:
        raise Exception(f"Failed to fetch OPML.\n{response.headers}")
    response_text = response.text
    if archive_dir:
        archive_dir.mkdir(parents=True, exist_ok=True)
        now = int(datetime.utcnow().timestamp())
        if verbose:
            print(f"Saving OPML {now} to {archive_dir}")
        with open(archive_dir / f"overcast-{now}.opml", "w") as f:
            f.write(response_text)
    return response_text


def _iso_date_or_none(dictionary: Dict, key: str) -> Optional[str]:
    if key in dictionary:
        return _parse_date_or_none(dictionary[key])
    else:
        return None


def extract_playlists_from_opml(xml_string: str) -> Iterable[Dict]:
    root = ET.fromstring(xml_string)
    for playlist in root.findall(
        "./body/outline[@text='playlists']/outline[@type='podcast-playlist']"
    ):
        if INCLUDE_PODCAST_IDS in playlist.attrib:
            yield {
                TITLE: playlist.attrib[TITLE],
                SMART: int(playlist.attrib[SMART]),
                SORTING: playlist.attrib[SORTING],
                INCLUDE_PODCAST_IDS: f"[{playlist.attrib[INCLUDE_PODCAST_IDS]}]",
            }


def extract_feed_and_episodes_from_opml(
    xml_string: str,
) -> Iterable[Tuple[Dict, List[Dict]]]:
    root = ET.fromstring(xml_string)
    for feed in root.findall("./body/outline[@text='feeds']/outline[@type='rss']"):
        episodes = []
        feed_attrs: Dict[str, Any] = feed.attrib.copy()
        feed_attrs[OVERCAST_ID] = int(feed_attrs[OVERCAST_ID])
        feed_attrs["subscribed"] = feed_attrs.get("subscribed", False) == "1"
        feed_attrs["notifications"] = feed_attrs.get("notifications", False) == "1"
        feed_attrs["overcastAddedDate"] = _iso_date_or_none(
            feed_attrs, "overcastAddedDate"
        )
        del feed_attrs["type"]
        del feed_attrs["text"]

        for episode_xml in feed.findall("./outline[@type='podcast-episode']"):
            ep_attrs: Dict[str, Any] = episode_xml.attrib.copy()
            ep_attrs[OVERCAST_ID] = int(ep_attrs[OVERCAST_ID])
            ep_attrs["feedId"] = feed_attrs["overcastId"]
            ep_attrs["played"] = ep_attrs.get("played", False) == "1"
            ep_attrs["userDeleted"] = ep_attrs.get("userDeleted", False) == "1"
            ep_attrs["progress"] = (
                None
                if (progress := ep_attrs.get("progress", None)) is None
                else int(progress)
            )
            ep_attrs["userUpdatedDate"] = _iso_date_or_none(ep_attrs, "userUpdatedDate")
            ep_attrs["userRecommendedDate"] = _iso_date_or_none(
                ep_attrs, "userRecommendedDate"
            )
            ep_attrs["pubDate"] = _iso_date_or_none(ep_attrs, "pubDate")
            del ep_attrs["type"]

            episodes.append(ep_attrs)

        yield feed_attrs, episodes
