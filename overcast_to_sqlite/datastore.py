# mypy: disable-error-code="union-attr"

import datetime
import os
import sqlite3
from collections.abc import Iterable

from sqlite_utils import Database

from .constants import (
    CHAPTERS,
    CONTENT,
    DESCRIPTION,
    ENCLOSURE_URL,
    EPISODES,
    EPISODES_EXTENDED,
    FEED_ID,
    FEED_XML_URL,
    FEEDS,
    FEEDS_EXTENDED,
    GUID,
    IMAGE,
    INCLUDE_PODCAST_IDS,
    LAST_UPDATED,
    LINK,
    OVERCAST_ID,
    PLAYLISTS,
    PROGRESS,
    PUB_DATE,
    SMART,
    SORTING,
    SOURCE,
    TIME,
    TITLE,
    TRANSCRIPT_DL_PATH,
    TRANSCRIPT_TYPE,
    TRANSCRIPT_URL,
    URL,
    USER_REC_DATE,
    USER_UPDATED_DATE,
    XML_URL,
)

_DEFAULT_EPISODE_LIMIT = 100


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
                    TITLE: str,
                    "subscribed": bool,
                    "overcastAddedDate": datetime.datetime,
                    "notifications": bool,
                    XML_URL: str,
                    "htmlUrl": str,
                    "dateRemoveDetected": datetime.datetime,
                },
                pk=OVERCAST_ID,
            )
        if FEEDS_EXTENDED not in self.db.table_names():
            self.db[FEEDS_EXTENDED].create(
                {
                    XML_URL: str,
                    TITLE: str,
                    DESCRIPTION: str,
                    LAST_UPDATED: datetime.datetime,
                    LINK: str,
                    GUID: str,
                },
                pk=XML_URL,
                foreign_keys=[(XML_URL, FEEDS, XML_URL)],
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
                    TITLE: str,
                    URL: str,
                    "overcastUrl": str,
                    "played": bool,
                    PROGRESS: int,
                    ENCLOSURE_URL: str,
                    USER_UPDATED_DATE: datetime.datetime,
                    USER_REC_DATE: datetime.datetime,
                    PUB_DATE: datetime.datetime,
                    "userDeleted": bool,
                },
                pk=OVERCAST_ID,
                foreign_keys=[(OVERCAST_ID, FEEDS, OVERCAST_ID)],
            )
        if EPISODES_EXTENDED not in self.db.table_names():
            self.db[EPISODES_EXTENDED].create(
                {
                    ENCLOSURE_URL: str,
                    FEED_XML_URL: str,
                    TITLE: str,
                    DESCRIPTION: str,
                    LINK: str,
                    GUID: str,
                },
                pk=ENCLOSURE_URL,
                foreign_keys=[
                    (ENCLOSURE_URL, EPISODES, ENCLOSURE_URL),
                    (FEED_XML_URL, FEEDS_EXTENDED, XML_URL),
                ],
            )
            self.db[EPISODES_EXTENDED].enable_fts(
                [TITLE, DESCRIPTION],
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
            )
        if CHAPTERS not in self.db.table_names():
            self.db[CHAPTERS].create(
                {
                    ENCLOSURE_URL: str,
                    GUID: str,
                    SOURCE: str,
                    TIME: int,
                    CONTENT: str,
                    URL: str,
                    IMAGE: str,
                },
                foreign_keys=[
                    (ENCLOSURE_URL, EPISODES, ENCLOSURE_URL),
                ],
            )
            self.db[CHAPTERS].enable_fts(
                [CONTENT],
                create_triggers=True,
            )
            self.db[CHAPTERS].create_index([ENCLOSURE_URL, GUID, SOURCE])
        self.db.create_view(
            "episodes_played",
            (
                "SELECT "
                f"{EPISODES}.{TITLE}, {FEEDS}.{TITLE} as feed, played, progress, "
                f"CASE WHEN {USER_REC_DATE} IS NOT NULL THEN 1 ELSE 0 END AS starred, "
                f"{USER_UPDATED_DATE}, {EPISODES}.{URL}, {ENCLOSURE_URL} "
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
                f"{USER_UPDATED_DATE}, {EPISODES}.{URL}, {ENCLOSURE_URL} "
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
                f"{USER_REC_DATE}, {EPISODES}.{URL}, {ENCLOSURE_URL} "
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
        limit_days = None
        try:
            if env_limit := os.getenv("OVERCAST_LIMIT_DAYS") is not None:
                limit_days = int(env_limit)
        except ValueError:
            pass

        if limit_days:
            cutoff_date = datetime.datetime.now(tz=datetime.UTC) - datetime.timedelta(
                days=int(limit_days),
            )
            episodes = [
                episode
                for episode in episodes
                if episode.get(USER_UPDATED_DATE)
                and datetime.datetime.fromisoformat(
                    episode[USER_UPDATED_DATE].replace("Z", "+00:00"),
                )
                >= cutoff_date
            ]

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

        now = datetime.datetime.now(tz=datetime.UTC).isoformat()
        for feed_id in deleted_ids:
            self.db[FEEDS].update(feed_id, {"dateRemoveDetected": now})

    def get_feeds_to_extend(self) -> list[tuple[str, str]]:
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

    def ensure_transcript_columns(self) -> bool:
        """Ensure transcript columns exist in database.

        Returns bool indicating if columns were added.
        """
        columns_added = False
        try:
            self.db.execute(f"SELECT {TRANSCRIPT_URL} FROM {EPISODES_EXTENDED} LIMIT 1")
        except sqlite3.OperationalError:
            self.db[EPISODES_EXTENDED].add_column(TRANSCRIPT_DL_PATH, str)
            columns_added = True
        try:
            self.db.execute(
                f"SELECT {TRANSCRIPT_DL_PATH} FROM {EPISODES_EXTENDED} LIMIT 1",
            )
        except sqlite3.OperationalError:
            self.db[EPISODES_EXTENDED].add_column(TRANSCRIPT_DL_PATH, str)
            columns_added = True
        return columns_added

    # TRANSCRIPTS

    def transcripts_to_download(
        self,
        *,
        starred_only: bool,
    ) -> Iterable[tuple[str, str, str, str, str]]:
        """Find episodes with transcripts to download.

        Yields (title, url, mime_type, enclosure_url, feed_title)
        """
        select = (
            f"SELECT {EPISODES_EXTENDED}.{TITLE}, {TRANSCRIPT_URL}, "
            f"{TRANSCRIPT_TYPE}, {EPISODES_EXTENDED}.{ENCLOSURE_URL}, "
            f"{FEEDS_EXTENDED}.{TITLE} FROM {EPISODES_EXTENDED} "
        )
        where = f"WHERE {TRANSCRIPT_DL_PATH} IS NULL AND {TRANSCRIPT_URL} IS NOT NULL"
        order = f"ORDER BY {FEEDS_EXTENDED}.{TITLE} ASC"
        query = (
            (
                f"{select} LEFT JOIN {FEEDS_EXTENDED} "
                f"ON {EPISODES_EXTENDED}.{FEED_XML_URL} = {FEEDS_EXTENDED}.{XML_URL} "
                f"{where} {order}"
            )
            if not starred_only
            else (
                f"{select} "
                f"LEFT JOIN {EPISODES} "
                f"ON {EPISODES_EXTENDED}.{ENCLOSURE_URL} = {EPISODES}.{ENCLOSURE_URL} "
                f"LEFT JOIN {FEEDS_EXTENDED} "
                f"ON {EPISODES_EXTENDED}.{FEED_XML_URL} = {FEEDS_EXTENDED}.{XML_URL} "
                f"{where} AND {USER_REC_DATE} IS NOT NULL {order}"
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

    # CHAPTERS
    def insert_chapters(
        self,
        chapters: list[tuple[str, str, str, int, str, str | None, str | None]],
    ) -> None:
        """Insert chapters into the chapters DB table."""
        self.db.conn.executemany(
            f"INSERT INTO {CHAPTERS} "
            f"({ENCLOSURE_URL}, {GUID}, {SOURCE}, {TIME}, {CONTENT}, {URL}, {IMAGE}) "
            "VALUES (?, ?, ?, ?, ?, ?, ?);",
            chapters,
        )
        self.db.conn.commit()

    def get_description_no_chapters(self) -> Iterable[tuple[str, str, str]]:
        """Find episodes with no chapters."""
        yield from self.db.execute(
            f"SELECT {EPISODES_EXTENDED}.{ENCLOSURE_URL}, {EPISODES_EXTENDED}.{GUID}, "
            f"{DESCRIPTION} "
            f"FROM {EPISODES_EXTENDED} "
            f"LEFT JOIN {CHAPTERS} "
            f"ON {EPISODES_EXTENDED}.{ENCLOSURE_URL} = {CHAPTERS}.{ENCLOSURE_URL} "
            f"WHERE {CHAPTERS}.{ENCLOSURE_URL} IS NULL "
            f"AND {DESCRIPTION} IS NOT NULL;",
        )

    def get_no_pci_chapters(self) -> Iterable[tuple[str, str, str, str]]:
        """Find episodes with no PCI type chapters."""
        yield from self.db.execute(
            f"SELECT {EPISODES_EXTENDED}.{ENCLOSURE_URL}, {EPISODES_EXTENDED}.{GUID}, "
            f'{EPISODES_EXTENDED}.{TITLE}, "podcast:chapters:url"'
            f"FROM {EPISODES_EXTENDED} "
            f"LEFT JOIN {CHAPTERS} "
            f"ON {EPISODES_EXTENDED}.{ENCLOSURE_URL} = {CHAPTERS}.{ENCLOSURE_URL} "
            f"WHERE {CHAPTERS}.{ENCLOSURE_URL} IS NULL "
            'AND "podcast:chapters:url" IS NOT NULL '
            f"AND ({CHAPTERS}.{SOURCE} IS NULL OR {CHAPTERS}.{SOURCE} != 'pci');",
        )

    def get_no_psc_chapters(self) -> Iterable[tuple[str, str, str]]:
        """Find episodes with no PCI type chapters."""
        yield from self.db.execute(
            f"SELECT {EPISODES_EXTENDED}.{ENCLOSURE_URL}, {EPISODES_EXTENDED}.{GUID}, "
            f"{FEEDS_EXTENDED}.{TITLE} "
            f"FROM {EPISODES_EXTENDED} "
            f"LEFT JOIN {CHAPTERS} "
            f"ON {EPISODES_EXTENDED}.{ENCLOSURE_URL} = {CHAPTERS}.{ENCLOSURE_URL} "
            f"LEFT JOIN {FEEDS_EXTENDED} "
            f"ON {EPISODES_EXTENDED}.{FEED_XML_URL} = {FEEDS_EXTENDED}.{XML_URL} "
            f"WHERE {CHAPTERS}.{ENCLOSURE_URL} IS NULL "
            'AND "psc:chapters:version" IS NOT NULL '
            f"AND ({CHAPTERS}.{SOURCE} IS NULL OR {CHAPTERS}.{SOURCE} != 'psc');",
        )

    def get_recently_played(self) -> list[dict[str, str]]:
        """Retrieve a list of recently played episodes with metadata."""
        self.db.execute(
            f"UPDATE {EPISODES} "
            f"SET {ENCLOSURE_URL} = "
            f"substr({ENCLOSURE_URL}, 1, instr({ENCLOSURE_URL}, '?') - 1) "
            f"WHERE {ENCLOSURE_URL} LIKE '%?%'",
        )
        self.db.conn.commit()

        self.db.execute(
            f"""
            DELETE FROM {EPISODES_EXTENDED} WHERE rowid IN (
                SELECT t1.rowid
                FROM {EPISODES_EXTENDED} t1
                JOIN (
                    SELECT
                        substr({ENCLOSURE_URL}, 1, instr({ENCLOSURE_URL}, '?') - 1)
                        AS base_url,
                        MIN(rowid) AS min_rowid
                    FROM {EPISODES_EXTENDED}
                    WHERE {ENCLOSURE_URL} LIKE '%?%'
                    GROUP BY base_url
                ) t2 ON
                substr(t1.{ENCLOSURE_URL}, 1, instr(t1.{ENCLOSURE_URL}, '?') - 1)
                = t2.base_url
                WHERE  t1.rowid > t2.min_rowid
            )
            """,
        )
        self.db.conn.commit()

        self.db.execute(
            f"UPDATE OR IGNORE {EPISODES_EXTENDED} "
            f"SET {ENCLOSURE_URL} = "
            f"substr({ENCLOSURE_URL}, 1, instr({ENCLOSURE_URL}, '?') - 1) "
            f"WHERE {ENCLOSURE_URL} LIKE '%?%'",
        )
        self.db.conn.commit()

        fields = [
            f"{EPISODES}.{TITLE}",
            f"{EPISODES}.{URL}",
            f"{FEEDS_EXTENDED}.{TITLE} as feed_title",
            f"{FEEDS_EXTENDED}.'itunes:image:href' as image_",
            f"{FEEDS_EXTENDED}.link as link_",
            f"coalesce({EPISODES_EXTENDED}.description, "
            "'No description') as description",
            f"{EPISODES_EXTENDED}.pubDate as pubDate",
            f"{EPISODES_EXTENDED}.'itunes:image:href' as 'images.'",
            f"{EPISODES_EXTENDED}.link as 'links.'",
            f"{USER_UPDATED_DATE}",
            "starred",
        ]
        query = (
            "SELECT "
            + ", ".join(fields[:-1])
            + (
                f", CASE WHEN {USER_REC_DATE} IS NOT NULL THEN 1 ELSE 0 END AS starred "
                f"FROM {EPISODES} "
                f"JOIN {EPISODES_EXTENDED} ON "
                f"{EPISODES}.{ENCLOSURE_URL} = {EPISODES_EXTENDED}.{ENCLOSURE_URL} "
                f"JOIN {FEEDS_EXTENDED} "
                f"ON {EPISODES_EXTENDED}.{FEED_XML_URL} = {FEEDS_EXTENDED}.{XML_URL} "
                f"WHERE played=1 OR progress>300 ORDER BY {USER_UPDATED_DATE} DESC "
                f"LIMIT {_DEFAULT_EPISODE_LIMIT}"
            )
        )

        results = self.db.execute(query).fetchall()
        return [
            {
                fields[i].split(" ")[-1].replace("s.", "_").replace("'", ""): v
                for (i, v) in enumerate(result)
                if v is not None
            }
            for result in results
        ]

    def cleanup_old_episodes(self) -> None:
        """Delete episodes older than OVERCAST_LIMIT_DAYS.

        Only deletes if more than 100 episodes exist.
        """
        limit_days = None
        try:
            if env_limit := os.getenv("OVERCAST_LIMIT_DAYS") is not None:
                limit_days = int(env_limit)
        except ValueError:
            pass

        if not limit_days:
            return

        episode_count = self.db.execute(f"SELECT COUNT(*) FROM {EPISODES}").fetchone()[
            0
        ]
        if episode_count <= _DEFAULT_EPISODE_LIMIT:
            return

        cutoff_date = datetime.datetime.now(tz=datetime.UTC) - datetime.timedelta(
            days=int(limit_days),
        )
        cutoff_iso = cutoff_date.isoformat()

        self.db.execute(
            f"DELETE FROM {EPISODES} WHERE {USER_UPDATED_DATE} < ?",
            [cutoff_iso],
        )
        self.db.conn.commit()
