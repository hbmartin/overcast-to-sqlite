import datetime
import sqlite3
from collections.abc import Iterable

from sqlite_utils import Database

from .constants import (
    DESCRIPTION,
    ENCLOSURE_URL,
    EPISODES,
    EPISODES_EXTENDED,
    FEED_ID,
    FEED_XML_URL,
    FEEDS,
    FEEDS_EXTENDED,
    INCLUDE_PODCAST_IDS,
    LAST_UPDATED,
    OVERCAST_ID,
    PLAYLISTS,
    PROGRESS,
    PUB_DATE,
    SMART,
    SORTING,
    TITLE,
    TRANSCRIPT_DL_PATH,
    TRANSCRIPT_TYPE,
    TRANSCRIPT_URL,
    USER_REC_DATE,
    USER_UPDATED_DATE,
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
                {
                    XML_URL: str,
                    TITLE: str,
                    DESCRIPTION: str,
                    LAST_UPDATED: datetime.datetime,
                },
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
                    FEED_ID: int,
                    "title": str,
                    "url": str,
                    "overcastUrl": str,
                    "played": bool,
                    PROGRESS: int,
                    ENCLOSURE_URL: str,
                    USER_UPDATED_DATE: datetime.datetime,
                    USER_REC_DATE: datetime.datetime,
                    PUB_DATE: datetime.datetime,
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
        self.db.create_view(
            "episodes_played",
            (
                "SELECT "
                f"{EPISODES}.{TITLE}, {FEEDS}.{TITLE} as feed, played, progress, "
                f"CASE WHEN {USER_REC_DATE} IS NOT NULL THEN 1 ELSE 0 END AS starred, "
                f"{USER_UPDATED_DATE}, overcastUrl, {ENCLOSURE_URL} "
                f"FROM {EPISODES} "
                f"LEFT JOIN {FEEDS} ON {EPISODES}.{FEED_ID} = {FEEDS}.{OVERCAST_ID} "
                f"WHERE played=1 OR progress>300 ORDER BY {USER_UPDATED_DATE} DESC"
            ),
            ignore=True,
        )
        self.db.create_view(
            "episodes_deleted",
            (
                "SELECT "
                f"{EPISODES}.{TITLE}, {FEEDS}.{TITLE} as feed, played, progress, "
                f"{USER_UPDATED_DATE}, overcastUrl, {ENCLOSURE_URL} "
                f"FROM {EPISODES} "
                f"LEFT JOIN {FEEDS} ON {EPISODES}.{FEED_ID} = {FEEDS}.{OVERCAST_ID} "
                f"WHERE userDeleted=1 AND played=0 ORDER BY {USER_UPDATED_DATE} DESC"
            ),
            ignore=True,
        )
        self.db.create_view(
            "episodes_starred",
            (
                "SELECT "
                f"{EPISODES}.{TITLE}, {FEEDS}.{TITLE} as feed, played, progress, "
                f"{USER_REC_DATE}, {USER_UPDATED_DATE}, overcastUrl, {ENCLOSURE_URL} "
                f"FROM {EPISODES} "
                f"LEFT JOIN {FEEDS} ON {EPISODES}.{FEED_ID} = {FEEDS}.{OVERCAST_ID} "
                f"WHERE {USER_REC_DATE} IS NOT NULL ORDER BY {USER_UPDATED_DATE} DESC"
            ),
            ignore=True,
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
            f"SELECT {FEEDS}.{TITLE}, {FEEDS}.{XML_URL} "
            f"FROM {EPISODES} "
            f"LEFT JOIN {EPISODES_EXTENDED} "
            f"ON {EPISODES}.{ENCLOSURE_URL} = {EPISODES_EXTENDED}.{ENCLOSURE_URL} "
            f"LEFT JOIN {FEEDS} "
            f"ON {EPISODES}.{FEED_ID} = {FEEDS}.{OVERCAST_ID} "
            f"LEFT JOIN {FEEDS_EXTENDED} "
            f"ON {FEEDS}.{XML_URL} = {FEEDS_EXTENDED}.{XML_URL} "
            f"WHERE {EPISODES_EXTENDED}.{ENCLOSURE_URL} IS NULL "
            f"AND ({FEEDS_EXTENDED}.{LAST_UPDATED} IS NULL "
            f"OR {FEEDS_EXTENDED}.{LAST_UPDATED} < {EPISODES}.{PUB_DATE}) "
            f"GROUP BY {FEED_ID};",
        ).fetchall()

    def save_playlist(self, playlist: dict) -> None:
        """Upsert playlist into database."""
        self.db[PLAYLISTS].upsert(playlist, pk=TITLE)

    def transcripts_to_download(
        self,
        starred_only: bool,
    ) -> Iterable[tuple[str, str, str, str, str]]:
        """Find episodes with transcripts to download.

        Yields (title, url, mime_type, enclosure_url, feed_title)
        """
        try:
            self.db.execute(f"SELECT {TRANSCRIPT_URL} FROM {EPISODES_EXTENDED} LIMIT 1")
        except sqlite3.OperationalError:
            raise NoTranscriptsUrlError from None
        try:
            self.db.execute(
                f"SELECT {TRANSCRIPT_DL_PATH} FROM {EPISODES_EXTENDED} LIMIT 1",
            )
        except sqlite3.OperationalError:
            self.db[EPISODES_EXTENDED].add_column(TRANSCRIPT_DL_PATH, str)
        select = (
            f"SELECT {EPISODES_EXTENDED}.{TITLE}, {TRANSCRIPT_URL}, "
            f"{TRANSCRIPT_TYPE}, {EPISODES_EXTENDED}.{ENCLOSURE_URL}, "
            f"{FEEDS_EXTENDED}.{TITLE} FROM {EPISODES_EXTENDED} "
        )
        where = f"WHERE {TRANSCRIPT_DL_PATH} IS NULL AND {TRANSCRIPT_URL} IS NOT NULL"
        query = (
            (
                f"{select} LEFT JOIN {FEEDS_EXTENDED} "
                f"ON {EPISODES_EXTENDED}.{FEED_XML_URL} = {FEEDS_EXTENDED}.{XML_URL} "
                f"{where}"
            )
            if not starred_only
            else (
                f"{select} "
                f"LEFT JOIN {EPISODES} "
                f"ON {EPISODES_EXTENDED}.{ENCLOSURE_URL} = {EPISODES}.{ENCLOSURE_URL} "
                f"LEFT JOIN {FEEDS_EXTENDED} "
                f"ON {EPISODES_EXTENDED}.{FEED_XML_URL} = {FEEDS_EXTENDED}.{XML_URL} "
                f"{where} AND {USER_REC_DATE} IS NOT NULL"
            )
        )

        yield from self.db.execute(query)

    def update_transcript_download_paths(
        self,
        enclosure: str,
        transcript_path: str,
    ) -> None:
        """Update episode with transcript download path."""
        self.db[EPISODES_EXTENDED].update(
            enclosure,
            {TRANSCRIPT_DL_PATH: transcript_path},
        )
