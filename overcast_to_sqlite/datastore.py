import datetime
import sqlite3
from typing import Iterable

from sqlite_utils import Database

from .constants import (
    DESCRIPTION,
    ENCLOSURE_DL_PATH,
    ENCLOSURE_URL,
    EPISODES,
    EPISODES_EXTENDED,
    FEEDS,
    FEEDS_EXTENDED,
    FEED_XML_URL,
    INCLUDE_PODCAST_IDS,
    OVERCAST_ID,
    PLAYLISTS,
    SMART,
    SORTING,
    TITLE,
    TRANSCRIPT_DL_PATH,
    TRANSCRIPT_TYPE,
    TRANSCRIPT_URL,
    USER_REC_DATE,
    XML_URL,
)
from .exceptions import NoTranscriptsUrlError


class Datastore:
    """Object responsible for all database interactions."""

    def __init__(self, db_path: str) -> None:
        """Instantiate and ensure tables exist with expected columns."""
        self.db: Database = Database(db_path)
        self._prepare_db()

    def _prepare_db(self) -> None:
        if FEEDS not in self.db.table_names():
            self.db[FEEDS].create(
                {
                    OVERCAST_ID: int,
                    "title": str,
                    "subscribed": bool,
                    "overcastAddedDate": datetime.datetime,
                    "notifications": bool,
                    XML_URL: str,
                    "htmlUrl": str,
                    "dateRemoveDetected": datetime.datetime,
                },
                pk=OVERCAST_ID,
                # not_null={"overcastId", "title", "xmlUrl"},
            )
        if FEEDS_EXTENDED not in self.db.table_names():
            self.db[FEEDS_EXTENDED].create(
                {XML_URL: str, TITLE: str, DESCRIPTION: str},
                pk=XML_URL,
                foreign_keys=[(XML_URL, FEEDS, XML_URL)],
                # not_null={"xmlUrl"},
            )
            self.db[FEEDS_EXTENDED].enable_fts(
                [TITLE, DESCRIPTION],
                create_triggers=True,
            )
        if EPISODES not in self.db.table_names():
            self.db[EPISODES].create(
                {
                    OVERCAST_ID: int,
                    "feedId": int,
                    "title": str,
                    "url": str,
                    "overcastUrl": str,
                    "played": bool,
                    "progress": int,
                    ENCLOSURE_URL: str,
                    "userUpdatedDate": datetime.datetime,
                    USER_REC_DATE: datetime.datetime,
                    "pubDate": datetime.datetime,
                    "userDeleted": bool,
                },
                pk="overcastId",
                foreign_keys=[(OVERCAST_ID, FEEDS, OVERCAST_ID)],
                # not_null={"overcastId", "feedId", "title", "enclosureUrl"},
            )
        if EPISODES_EXTENDED not in self.db.table_names():
            self.db[EPISODES_EXTENDED].create(
                {
                    ENCLOSURE_URL: str,
                    FEED_XML_URL: str,
                    "title": str,
                    "description": str,
                },
                pk=ENCLOSURE_URL,
                foreign_keys=[
                    (ENCLOSURE_URL, EPISODES, ENCLOSURE_URL),
                    (FEED_XML_URL, FEEDS_EXTENDED, XML_URL),
                ],
                # not_null={"enclosureUrl"},
            )
            self.db[EPISODES_EXTENDED].enable_fts(
                ["title", "description"],
                create_triggers=True,
            )
        if PLAYLISTS not in self.db.table_names():
            self.db[PLAYLISTS].create(
                {
                    TITLE: str,
                    SMART: int,
                    SORTING: str,
                    INCLUDE_PODCAST_IDS: str,
                },
                pk=TITLE,
                # not_null={"enclosureUrl"},
            )

    def save_feed_and_episodes(
        self,
        feed: dict,
        episodes: list[dict],
    ) -> None:
        """Upsert feed and episodes into database."""
        self.db[FEEDS].upsert(feed, pk=OVERCAST_ID)
        self.db[EPISODES].upsert_all(episodes, pk=OVERCAST_ID)

    def save_extended_feed_and_episodes(
        self,
        feed: dict,
        episodes: list[dict],
    ) -> None:
        """Upsert feed info (with new columns) and insert episodes (ignore existing)."""
        self.db[FEEDS_EXTENDED].upsert(feed, pk=XML_URL, alter=True)
        self.db[EPISODES_EXTENDED].insert_all(
            episodes,
            pk=ENCLOSURE_URL,
            ignore=True,
            alter=True,
        )

    def mark_feed_removed_if_missing(
        self,
        ingested_feed_ids: set[int],
    ) -> None:
        """Set feeds as removed at now if they are not in the ingested feed ids."""
        stored_feed_ids = self.db.execute(
            f"SELECT {OVERCAST_ID} FROM {FEEDS} WHERE dateRemoveDetected IS null",
        ).fetchall()
        stored_feed_ids = {x[0] for x in stored_feed_ids}
        deleted_ids = stored_feed_ids - ingested_feed_ids

        now = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
        for feed_id in deleted_ids:
            self.db[FEEDS].update(feed_id, {"dateRemoveDetected": now})

    def get_feeds_to_extend(self) -> list[str]:
        """Find feeds with episodes not represented in episodes_extended."""
        return self.db.execute(
            "SELECT feeds.title, feeds.xmlUrl "
            "FROM episodes "
            "LEFT JOIN episodes_extended "
            "ON episodes.enclosureUrl = episodes_extended.enclosureUrl "
            "LEFT JOIN feeds ON episodes.feedId = feeds.overcastId "
            "LEFT JOIN feeds_extended ON feeds.xmlUrl = feeds_extended.xmlUrl "
            "WHERE episodes_extended.enclosureUrl IS NULL "
            "AND (feeds_extended.lastUpdated IS NULL "
            "OR feeds_extended.lastUpdated < episodes.pubDate) "
            "GROUP BY feedId;",
        ).fetchall()

    def save_playlist(self, playlist: dict) -> None:
        """Upsert playlist into database."""
        self.db[PLAYLISTS].upsert(playlist, pk=TITLE)

    def ensure_download_columns(self) -> None:
        """Ensure download columns exist in episodes_extended."""
        try:
            self.db.execute(f"SELECT {ENCLOSURE_DL_PATH} FROM {EPISODES_EXTENDED};")
        except sqlite3.OperationalError as err:
            print(err)
            print(vars(err))
            self.db[EPISODES_EXTENDED].add_column(ENCLOSURE_DL_PATH, str)

    def transcripts_to_download(
        self, starred_only: bool
    ) -> Iterable[tuple[str, str, str, str, str]]:
        try:
            self.db.execute(f"SELECT {TRANSCRIPT_URL} FROM {EPISODES_EXTENDED} LIMIT 1")
        except sqlite3.OperationalError:
            raise NoTranscriptsUrlError
        try:
            self.db.execute(
                f"SELECT {TRANSCRIPT_DL_PATH} FROM {EPISODES_EXTENDED} LIMIT 1"
            )
        except sqlite3.OperationalError:
            self.db[EPISODES_EXTENDED].add_column(TRANSCRIPT_DL_PATH, str)
        query = (
            f"SELECT {EPISODES_EXTENDED}.{TITLE}, {TRANSCRIPT_URL}, {TRANSCRIPT_TYPE}, "
            + f"{EPISODES_EXTENDED}.{ENCLOSURE_URL}, {FEEDS_EXTENDED}.{TITLE} "
            + f"FROM {EPISODES_EXTENDED} "
            + f"LEFT JOIN {FEEDS_EXTENDED} ON {EPISODES_EXTENDED}.{FEED_XML_URL} = {FEEDS_EXTENDED}.{XML_URL} "
            + f"WHERE {TRANSCRIPT_DL_PATH} IS NULL AND {TRANSCRIPT_URL} IS NOT NULL"
            if not starred_only
            else f"SELECT {EPISODES_EXTENDED}.{TITLE}, {TRANSCRIPT_URL}, {TRANSCRIPT_TYPE}, "
            + f"{EPISODES_EXTENDED}.{ENCLOSURE_URL}, {FEEDS_EXTENDED}.{TITLE} "
            + f"FROM {EPISODES_EXTENDED} "
            + f"LEFT JOIN {EPISODES} ON {EPISODES_EXTENDED}.{ENCLOSURE_URL} = {EPISODES}.{ENCLOSURE_URL} "
            + f"LEFT JOIN {FEEDS_EXTENDED} ON {EPISODES_EXTENDED}.{FEED_XML_URL} = {FEEDS_EXTENDED}.{XML_URL} "
            + f"WHERE {USER_REC_DATE} IS NOT NULL AND {TRANSCRIPT_DL_PATH} IS NULL AND {TRANSCRIPT_URL} IS NOT NULL"
        )

        for title, url, trans_type, enclosureUrl, feed_title in self.db.execute(query):
            yield title, url, trans_type, enclosureUrl, feed_title

    def update_transcript_download_paths(
        self, enclosure: str, transcript_path: str
    ) -> None:
        self.db[EPISODES_EXTENDED].update(
            enclosure, {TRANSCRIPT_DL_PATH: transcript_path}
        )
