import datetime
from typing import Dict, List, Set
from sqlite_utils import Database

from overcast_to_sqlite.constants import (
    DESCRIPTION,
    ENCLOSURE_URL,
    EPISODES,
    EPISODES_EXTENDED,
    FEEDS,
    FEEDS_EXTENDED,
    FEED_XML_URL,
    OVERCAST_ID,
    PLAYLISTS,
    TITLE,
    XML_URL,
    INCLUDE_PODCAST_IDS,
    SMART,
    SORTING,
)


class Datastore:
    def __init__(self, db_path: str):
        self.db = Database(db_path)
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
                [TITLE, DESCRIPTION], create_triggers=True
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
                    "userRecommendedDate": datetime.datetime,
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
                ["title", "description"], create_triggers=True
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

    def save_feed_and_episodes(self, feed: Dict, episodes: List[Dict]) -> None:
        self.db[FEEDS].upsert(feed, pk=OVERCAST_ID)
        self.db[EPISODES].upsert_all(episodes, pk=OVERCAST_ID)

    def save_extended_feed_and_episodes(self, feed: Dict, episodes: List[Dict]) -> None:
        self.db[FEEDS_EXTENDED].upsert(feed, pk=XML_URL, alter=True)
        self.db[EPISODES_EXTENDED].insert_all(
            episodes, pk=ENCLOSURE_URL, ignore=True, alter=True
        )

    def mark_feed_removed_if_missing(self, ingested_feed_ids: Set[int]) -> None:
        stored_feed_ids = self.db.execute(
            f"SELECT {OVERCAST_ID} FROM {FEEDS} WHERE dateRemoveDetected IS null"
        ).fetchall()
        stored_feed_ids = set([x[0] for x in stored_feed_ids])
        deleted_ids = stored_feed_ids - ingested_feed_ids

        now = datetime.datetime.now().isoformat()
        for feed_id in deleted_ids:
            self.db[FEEDS].update(feed_id, {"dateRemoveDetected": now})

    def get_feeds_to_extend(self) -> List[str]:
        """Find feeds with episodes not represented in episodes_extended"""
        feeds_to_extend = self.db.execute(
            "SELECT feeds.title, feeds.xmlUrl "
            "FROM episodes "
            "LEFT JOIN episodes_extended ON episodes.enclosureUrl = episodes_extended.enclosureUrl "
            "LEFT JOIN feeds ON episodes.feedId = feeds.overcastId "
            "LEFT JOIN feeds_extended ON feeds.xmlUrl = feeds_extended.xmlUrl "
            "WHERE episodes_extended.enclosureUrl IS NULL "
            "AND (feeds_extended.lastUpdated IS NULL OR feeds_extended.lastUpdated < episodes.pubDate) "
            "GROUP BY feedId;"
        ).fetchall()
        return feeds_to_extend

    def save_playlist(self, playlist):
        self.db[PLAYLISTS].upsert(playlist, pk=TITLE)
