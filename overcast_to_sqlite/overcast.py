from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from requests import Session

if TYPE_CHECKING:
    from collections.abc import Iterable
    from xml.etree.ElementTree import Element

from .constants import (
    ENCLOSURE_URL,
    INCLUDE_PODCAST_IDS,
    OVERCAST_ID,
    SMART,
    SORTING,
    TITLE,
    USER_REC_DATE,
    XML_URL,
)
from .exceptions import (
    AuthFailedError,
    OpmlFetchError,
    WrongPasswordError,
)
from .models import Episode, Feed, Playlist
from .utils import _parse_date_or_none


def auth_and_save_cookies(email: str, password: str, auth_json: str) -> None:
    """Authenticate to Overcast and save cookies to a JSON file."""
    session = Session()
    response = session.post(
        "https://overcast.fm/login?then=account",
        data={"email": email, "password": password},
        allow_redirects=False,
    )

    if "Incorrect password" in response.text:
        raise WrongPasswordError
    cookies = session.cookies.get_dict()
    if "o" not in cookies:
        raise AuthFailedError

    print("Authenticated successfully. Saving session.")
    auth_json_path = Path(auth_json)
    if auth_json_path.exists():
        auth_data = json.loads(auth_json_path.read_text())
    else:
        auth_data = {}
    auth_data["overcast"] = cookies
    auth_json_path.write_text(json.dumps(auth_data, indent=4) + "\n")


def _session_from_json(auth_json_path: str) -> Session:
    with Path(auth_json_path).open() as f:
        cookies = json.load(f)["overcast"]
        session = Session()
        session.cookies.update(cookies)
        return session


def _session_from_cookie(cookie: str) -> Session:
    session = Session()
    session.cookies.update({"o": cookie, "qr": "-"})
    return session


def fetch_opml(session: Session, archive_dir: Path | None) -> str:
    """Fetch OPML from Overcast and optionally save OPML to an archive directory."""
    response = session.get(
        "https://overcast.fm/account/export_opml/extended",
        timeout=None,
    )
    if not response.ok:
        raise OpmlFetchError(dict(response.headers))
    response_text = response.text
    if archive_dir:
        archive_dir.mkdir(parents=True, exist_ok=True)
        now = int(datetime.now(tz=UTC).timestamp())
        archive_dir.joinpath(f"overcast-{now}.opml").write_text(response_text)
    return response_text


def _iso_date_or_none(dictionary: dict, key: str) -> str | None:
    if key in dictionary:
        return _parse_date_or_none(dictionary[key])
    return None


def extract_playlists_from_opml(root: Element) -> Iterable[Playlist]:
    for playlist in root.findall(
        "./body/outline[@text='playlists']/outline[@type='podcast-playlist']",
    ):
        if INCLUDE_PODCAST_IDS in playlist.attrib:
            yield Playlist(
                title=playlist.attrib[TITLE],
                smart=int(playlist.attrib[SMART]),
                sorting=playlist.attrib[SORTING],
                includePodcastIds=f"[{playlist.attrib[INCLUDE_PODCAST_IDS]}]",
            )


def extract_feed_and_episodes_from_opml(
    root: Element,
) -> Iterable[tuple[Feed, list[Episode]]]:
    for feed_el in root.findall(
        "./body/outline[@text='feeds']/outline[@type='rss']",
    ):
        attribs = feed_el.attrib
        feed = Feed(
            overcastId=int(attribs[OVERCAST_ID]),
            title=attribs[TITLE],
            subscribed=attribs.get("subscribed", "0") == "1",
            notifications=attribs.get("notifications", "0") == "1",
            xmlUrl=attribs[XML_URL],
            htmlUrl=attribs.get("htmlUrl", ""),
            overcastAddedDate=_iso_date_or_none(
                dict(attribs),
                "overcastAddedDate",
            ),
        )
        episodes = []
        for episode_xml in feed_el.findall(
            "./outline[@type='podcast-episode']",
        ):
            ep = episode_xml.attrib
            episodes.append(
                Episode(
                    overcastId=int(ep[OVERCAST_ID]),
                    feedId=feed.overcastId,
                    title=ep.get(TITLE, ""),
                    url=ep.get("url", ""),
                    overcastUrl=ep.get("overcastUrl", ""),
                    played=ep.get("played", "0") == "1",
                    userDeleted=ep.get("userDeleted", "0") == "1",
                    enclosureUrl=ep[ENCLOSURE_URL].split("?")[0],
                    progress=(
                        None
                        if (progress := ep.get("progress")) is None
                        else int(progress)
                    ),
                    userUpdatedDate=_iso_date_or_none(
                        dict(ep),
                        "userUpdatedDate",
                    ),
                    userRecommendedDate=_iso_date_or_none(
                        dict(ep),
                        USER_REC_DATE,
                    ),
                    pubDate=_iso_date_or_none(dict(ep), "pubDate"),
                ),
            )

        yield feed, episodes
