import sqlite3
from functools import partial
from pathlib import Path

import pytest
from click.testing import CliRunner

from overcast_to_sqlite import cli
from overcast_to_sqlite.datastore import Datastore
from overcast_to_sqlite.models import Episode, Feed, Playlist

_EXTENDED_EPISODE_COLUMNS = (
    "enclosureUrl",
    "feedXmlUrl",
    "title",
    "description",
    "link",
    "itunes:image:href",
    "pubDate",
    "guid",
)
_EXTENDED_EPISODE_SELECT = ", ".join(
    f'"{column}"' for column in _EXTENDED_EPISODE_COLUMNS
)


def _make_extended_feed() -> dict[str, str]:
    return {
        "xmlUrl": "https://example.com/feed-1.xml",
        "title": "Tech Podcast",
        "description": "About technology",
        "link": "https://example.com/feed-1",
        "itunes:image:href": "https://example.com/feed-1.png",
    }


def _make_extended_episode(enclosure_url: str, title: str) -> dict[str, str]:
    return {
        "enclosureUrl": enclosure_url,
        "feedXmlUrl": "https://example.com/feed-1.xml",
        "title": title,
        "description": f"{title} description",
        "link": f"https://example.com/episodes/{title}",
        "itunes:image:href": f"https://example.com/episodes/{title}.png",
        "pubDate": "Thu, 02 Jan 2025 00:00:00 GMT",
        "guid": f"{title}-guid",
    }


def _stored_extended_episodes(db_path: Path) -> list[tuple[str, ...]]:
    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            f"SELECT {_EXTENDED_EPISODE_SELECT} FROM episodes_extended "
            "ORDER BY enclosureUrl",
        ).fetchall()


@pytest.fixture
def legacy_database(tmp_path: Path) -> Path:
    db_path = tmp_path / "legacy.db"
    store = Datastore(str(db_path))
    episode = _make_episode(overcast_id=1, starred=True)
    store.save_feed_and_episodes(feed=_make_feed(), episodes=[episode])
    clean = _make_extended_episode(episode.enclosureUrl, "clean")
    variant = _make_extended_episode(f"{episode.enclosureUrl}?source=rss", "variant")
    store.save_extended_feed_and_episodes(feed=_make_extended_feed(), episodes=[clean])

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE episodes SET enclosureUrl = enclosureUrl || '?source=overcast'",
        )
        conn.execute("DELETE FROM episodes_extended")
        conn.executemany(
            f"INSERT INTO episodes_extended ({_EXTENDED_EPISODE_SELECT}) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                tuple(row[column] for column in _EXTENDED_EPISODE_COLUMNS)
                for row in (variant, clean)
            ],
        )
    return db_path


def _make_feed(overcast_id: int = 1, title: str = "Test Feed") -> Feed:
    return Feed(
        overcastId=overcast_id,
        title=title,
        subscribed=True,
        notifications=False,
        xmlUrl=f"https://example.com/feed-{overcast_id}.xml",
        htmlUrl=f"https://example.com/{overcast_id}",
    )


def _make_episode(
    overcast_id: int,
    feed_id: int = 1,
    *,
    played: bool = True,
    progress: int = 3600,
    title: str = "",
    starred: bool = False,
) -> Episode:
    return Episode(
        overcastId=overcast_id,
        feedId=feed_id,
        title=title or f"Episode {overcast_id}",
        url=f"https://example.com/{overcast_id}",
        overcastUrl=f"https://overcast.fm/+{overcast_id}",
        played=played,
        userDeleted=False,
        enclosureUrl=f"https://cdn.example.com/{overcast_id}.mp3",
        progress=progress,
        userUpdatedDate="2025-01-02T00:00:00+00:00",
        userRecommendedDate="2025-01-03T00:00:00+00:00" if starred else None,
    )


def test_save_and_retrieve_feed(tmp_path):
    db_path = str(tmp_path / "test.db")
    store = Datastore(db_path)
    feed = _make_feed()
    store.save_feed_and_episodes(feed, [])

    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT title, subscribed FROM feeds").fetchone()
    assert row == ("Test Feed", 1)


def test_save_and_retrieve_episode(tmp_path):
    db_path = str(tmp_path / "test.db")
    store = Datastore(db_path)
    feed = _make_feed()
    episode = _make_episode(overcast_id=1)
    store.save_feed_and_episodes(feed, [episode])

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT title, played, progress FROM episodes",
        ).fetchone()
    assert row == ("Episode 1", 1, 3600)


def test_save_playlist(tmp_path):
    db_path = str(tmp_path / "test.db")
    store = Datastore(db_path)
    playlist = Playlist(
        title="My Playlist",
        smart=0,
        sorting="manual",
        includePodcastIds="[1,2]",
    )
    store.save_playlist(playlist)

    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT title, smart FROM playlists").fetchone()
    assert row == ("My Playlist", 0)


def test_mark_feed_removed_if_missing(tmp_path):
    db_path = str(tmp_path / "test.db")
    store = Datastore(db_path)
    store.save_feed_and_episodes(_make_feed(overcast_id=1), [])
    store.save_feed_and_episodes(
        _make_feed(overcast_id=2, title="Feed 2"),
        [],
    )

    store.mark_feed_removed_if_missing({1})

    with sqlite3.connect(db_path) as conn:
        removed = conn.execute(
            "SELECT overcastId FROM feeds WHERE dateRemoveDetected IS NOT NULL",
        ).fetchall()
    assert removed == [(2,)]


def test_get_listening_stats(tmp_path):
    db_path = str(tmp_path / "test.db")
    store = Datastore(db_path)
    feed = _make_feed()
    episodes = [
        _make_episode(overcast_id=1, played=True, progress=3600),
        _make_episode(overcast_id=2, played=True, progress=1800),
        _make_episode(overcast_id=3, played=False, progress=0),
    ]
    store.save_feed_and_episodes(feed, episodes)

    listening_stats = store.get_listening_stats()
    assert listening_stats["episodes_played"] == 2
    assert listening_stats["total_progress_seconds"] == 5400
    assert listening_stats["feeds_subscribed"] == 1
    assert listening_stats["feeds_removed"] == 0


def test_get_listening_stats_starred(tmp_path):
    db_path = str(tmp_path / "test.db")
    store = Datastore(db_path)
    feed = _make_feed()
    episodes = [
        _make_episode(overcast_id=1, starred=True),
        _make_episode(overcast_id=2, starred=True),
        _make_episode(overcast_id=3),
    ]
    store.save_feed_and_episodes(feed, episodes)

    listening_stats = store.get_listening_stats()
    assert listening_stats["episodes_starred"] == 2


def test_get_listening_stats_counts_progress_threshold(tmp_path) -> None:
    db_path = str(tmp_path / "test.db")
    store = Datastore(db_path)
    store.save_feed_and_episodes(
        feed=_make_feed(),
        episodes=[
            _make_episode(overcast_id=1, played=False, progress=301),
            _make_episode(overcast_id=2, played=False, progress=299),
        ],
    )

    listening_stats = store.get_listening_stats()
    assert listening_stats["episodes_played"] == 1


def test_get_top_podcasts_by_episodes(tmp_path):
    db_path = str(tmp_path / "test.db")
    store = Datastore(db_path)
    feed1 = _make_feed(overcast_id=1, title="Popular")
    feed2 = _make_feed(overcast_id=2, title="Less Popular")
    store.save_feed_and_episodes(
        feed1,
        [_make_episode(overcast_id=i, feed_id=1) for i in range(1, 6)],
    )
    store.save_feed_and_episodes(
        feed2,
        [_make_episode(overcast_id=i, feed_id=2) for i in range(6, 9)],
    )

    top = store.get_top_podcasts_by_episodes(limit=2)
    assert len(top) == 2
    assert top[0][0] == "Popular"
    assert top[0][1] == 5
    assert top[1][0] == "Less Popular"
    assert top[1][1] == 3


def test_get_top_podcasts_by_time(tmp_path):
    db_path = str(tmp_path / "test.db")
    store = Datastore(db_path)
    feed = _make_feed()
    episodes = [
        _make_episode(overcast_id=1, progress=7200),
        _make_episode(overcast_id=2, progress=3600),
    ]
    store.save_feed_and_episodes(feed, episodes)

    top = store.get_top_podcasts_by_time(limit=1)
    assert len(top) == 1
    assert top[0][0] == "Test Feed"
    assert top[0][1] == 10_800


def test_get_top_podcasts_by_episodes_counts_progress_threshold(tmp_path) -> None:
    db_path = str(tmp_path / "test.db")
    store = Datastore(db_path)
    store.save_feed_and_episodes(
        feed=_make_feed(title="Threshold Feed"),
        episodes=[
            _make_episode(overcast_id=1, played=False, progress=301),
            _make_episode(overcast_id=2, played=False, progress=120),
        ],
    )

    top = store.get_top_podcasts_by_episodes(limit=1)
    assert top == [("Threshold Feed", 1)]


def test_search_episodes_empty_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    store = Datastore(db_path)
    results = store.search_episodes("test")
    assert results == []


def test_search_feeds_empty_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    store = Datastore(db_path)
    results = store.search_feeds("test")
    assert results == []


def test_search_chapters_empty_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    store = Datastore(db_path)
    results = store.search_chapters("test")
    assert results == []


def test_search_episodes_with_data(tmp_path):
    db_path = str(tmp_path / "test.db")
    store = Datastore(db_path)
    feed = _make_feed()
    episode = _make_episode(
        overcast_id=1,
        title="Machine Learning Basics",
    )
    store.save_feed_and_episodes(feed, [episode])

    store.save_extended_feed_and_episodes(
        {
            "xmlUrl": "https://example.com/feed-1.xml",
            "title": "Tech Podcast",
            "description": "About technology",
        },
        [
            {
                "enclosureUrl": "https://cdn.example.com/1.mp3",
                "feedXmlUrl": "https://example.com/feed-1.xml",
                "title": "Machine Learning Basics",
                "description": "Learn ML fundamentals",
            },
        ],
    )

    results = store.search_episodes("machine learning")
    assert len(results) >= 1
    assert results[0][0] == "Machine Learning Basics"


def test_search_episodes_quotes_punctuation_heavy_query(tmp_path) -> None:
    db_path = str(tmp_path / "test.db")
    store = Datastore(db_path)

    store.save_extended_feed_and_episodes(
        feed={
            "xmlUrl": "https://example.com/feed.xml",
            "title": "Tech Podcast",
            "description": "About technology",
        },
        episodes=[
            {
                "enclosureUrl": "https://cdn.example.com/1.mp3",
                "feedXmlUrl": "https://example.com/feed.xml",
                "title": "foo-bar",
                "description": "Learn foo-bar fundamentals",
            },
        ],
    )

    results = store.search_episodes("foo-bar")
    assert results == [("foo-bar", "Tech Podcast")]


def test_search_feeds_with_data(tmp_path):
    db_path = str(tmp_path / "test.db")
    store = Datastore(db_path)

    store.save_extended_feed_and_episodes(
        {
            "xmlUrl": "https://example.com/feed.xml",
            "title": "Python Weekly",
            "description": "Weekly Python news",
        },
        [],
    )

    results = store.search_feeds("python")
    assert len(results) >= 1
    assert results[0][0] == "Python Weekly"


def test_get_listening_stats_empty_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    store = Datastore(db_path)

    listening_stats = store.get_listening_stats()
    assert listening_stats["episodes_played"] == 0
    assert listening_stats["total_progress_seconds"] == 0
    assert listening_stats["feeds_subscribed"] == 0
    assert listening_stats["feeds_removed"] == 0
    assert listening_stats["episodes_starred"] == 0


def test_search_methods_return_empty_for_non_positive_limits(tmp_path) -> None:
    db_path = str(tmp_path / "test.db")
    store = Datastore(db_path)

    assert store.get_top_podcasts_by_episodes(limit=0) == []
    assert store.get_top_podcasts_by_time(limit=-1) == []
    assert store.search_episodes("test", limit=0) == []
    assert store.search_feeds("test", limit=-1) == []
    assert store.search_chapters("test", limit=0) == []


@pytest.mark.parametrize("insertion_order", ["clean-first", "query-first"])
@pytest.mark.parametrize(
    "getter_name",
    ["get_recently_played", "get_starred_episodes", "get_deleted_episodes"],
)
def test_episode_getters_preserve_clean_enclosure_metadata(
    tmp_path: Path,
    insertion_order: str,
    getter_name: str,
) -> None:
    db_path = tmp_path / "test.db"
    store = Datastore(str(db_path))
    episode = _make_episode(
        overcast_id=1,
        played=getter_name != "get_deleted_episodes",
        progress=0 if getter_name == "get_deleted_episodes" else 3600,
        starred=True,
    )
    episode.userDeleted = getter_name == "get_deleted_episodes"
    store.save_feed_and_episodes(
        feed=_make_feed(),
        episodes=[episode],
    )
    clean = _make_extended_episode(episode.enclosureUrl, "clean")
    variant = _make_extended_episode(f"{episode.enclosureUrl}?source=rss", "variant")
    variant["pubDate"] = "Fri, 03 Jan 2025 00:00:00 GMT"
    store.save_extended_feed_and_episodes(
        feed=_make_extended_feed(),
        episodes=(
            [clean, variant] if insertion_order == "clean-first" else [variant, clean]
        ),
    )

    expected_row = tuple(clean[column] for column in _EXTENDED_EPISODE_COLUMNS)
    assert _stored_extended_episodes(db_path) == [expected_row]
    before_reads = store.db.conn.total_changes

    def forbid_writes(action: int, *_args: object) -> int:
        return (
            sqlite3.SQLITE_DENY
            if action
            in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE)
            else sqlite3.SQLITE_OK
        )

    store.db.conn.set_authorizer(forbid_writes)
    try:
        results = getattr(store, getter_name)()
        assert getattr(store, getter_name)() == results
    finally:
        store.db.conn.set_authorizer(None)

    assert len(results) == 1
    assert results[0]["description"] == clean["description"]
    assert results[0]["link_"] == clean["link"]
    assert results[0]["image_"] == clean["itunes:image:href"]
    assert results[0]["pubDate"] == clean["pubDate"]
    assert store.db.conn.total_changes == before_reads
    assert _stored_extended_episodes(db_path) == [expected_row]


def test_query_only_duplicates_keep_earliest_metadata_on_repeated_ingestion(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "test.db"
    store = Datastore(str(db_path))
    url = "https://cdn.example.com/1.mp3"
    earliest = _make_extended_episode(f"{url}?source=first", "earliest")
    later = _make_extended_episode(f"{url}?source=second", "later")
    unrelated = _make_extended_episode("https://cdn.example.com/2.mp3", "unrelated")
    store.save_extended_feed_and_episodes(
        feed=_make_extended_feed(),
        episodes=[earliest, unrelated, later],
    )
    expected = [
        tuple(
            {**earliest, "enclosureUrl": url}[column]
            for column in _EXTENDED_EPISODE_COLUMNS
        ),
        tuple(unrelated[column] for column in _EXTENDED_EPISODE_COLUMNS),
    ]
    assert _stored_extended_episodes(db_path) == expected

    store.save_extended_feed_and_episodes(
        feed=_make_extended_feed(),
        episodes=[{**earliest, "title": "replacement"}, later, unrelated],
    )
    assert _stored_extended_episodes(db_path) == expected
    store.save_extended_feed_and_episodes(
        feed=_make_extended_feed(),
        episodes=[_make_extended_episode(url, "clean-arriving-later")],
    )
    store.clean_enclosure_urls()
    store.clean_enclosure_urls()
    assert _stored_extended_episodes(db_path) == expected


def test_legacy_database_open_and_getters_leave_urls_unchanged(
    legacy_database: Path,
) -> None:
    before = _stored_extended_episodes(legacy_database)
    store = Datastore(str(legacy_database))
    before_reads = store.db.conn.total_changes

    assert store.get_recently_played() == []
    assert store.get_starred_episodes() == []
    assert store.get_deleted_episodes() == []

    assert store.db.conn.total_changes == before_reads
    assert _stored_extended_episodes(legacy_database) == before
    with sqlite3.connect(legacy_database) as conn:
        assert conn.execute("SELECT enclosureUrl FROM episodes").fetchone() == (
            "https://cdn.example.com/1.mp3?source=overcast",
        )


@pytest.mark.parametrize("command", ["save", "extend"])
def test_ingestion_commands_repair_legacy_urls_without_new_episodes(
    legacy_database: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
) -> None:
    monkeypatch.delenv("OVERCAST_LIMIT_DAYS", raising=False)

    def forbid_fetch(**_kwargs: object) -> None:
        pytest.fail("No feed downloads should be needed after legacy URL cleanup")

    monkeypatch.setattr(cli, "fetch_xml_and_extract", forbid_fetch)
    args = [command, str(legacy_database), "--no-archive"]
    if command == "save":
        opml_path = legacy_database.with_suffix(".opml")
        opml_path.write_text('<opml version="2.0"><body/></opml>')
        args.extend(["--load", str(opml_path)])
    result = CliRunner().invoke(cli.cli, args, catch_exceptions=False)

    assert result.exit_code == 0
    if command == "extend":
        assert "Extending 0 feeds" in result.output
    clean = _make_extended_episode("https://cdn.example.com/1.mp3", "clean")
    assert _stored_extended_episodes(legacy_database) == [
        tuple(clean[column] for column in _EXTENDED_EPISODE_COLUMNS),
    ]
    store = Datastore(str(legacy_database))
    assert store.get_recently_played()[0]["description"] == clean["description"]
    assert store.get_starred_episodes()[0]["link_"] == clean["link"]
    with sqlite3.connect(legacy_database) as conn:
        assert conn.execute("SELECT enclosureUrl FROM episodes").fetchone() == (
            clean["enclosureUrl"],
        )


@pytest.mark.parametrize("cleanup_path", ["existing", "new-batch"])
def test_cleanup_rolls_back_deletion_and_url_updates_on_failure(
    legacy_database: Path,
    cleanup_path: str,
) -> None:
    store = Datastore(str(legacy_database))
    store.db.execute(
        "UPDATE episodes_extended SET enclosureUrl = enclosureUrl || '?source=second' "
        "WHERE title = 'clean'",
    )
    before = _stored_extended_episodes(legacy_database)
    store.db.execute(
        "CREATE TRIGGER reject_url_update BEFORE UPDATE ON episodes_extended "
        "BEGIN SELECT RAISE(ABORT, 'normalization failed'); END",
    )

    cleanup = (
        store.clean_enclosure_urls
        if cleanup_path == "existing"
        else partial(
            store.save_extended_feed_and_episodes,
            feed=_make_extended_feed(),
            episodes=[],
        )
    )
    with pytest.raises(sqlite3.IntegrityError, match="normalization failed"):
        cleanup()

    assert not store.db.conn.in_transaction
    assert _stored_extended_episodes(legacy_database) == before
    with sqlite3.connect(legacy_database) as conn:
        assert conn.execute("SELECT enclosureUrl FROM episodes").fetchone() == (
            "https://cdn.example.com/1.mp3?source=overcast",
        )
    assert len(store.search_episodes("description")) == len(before)

    store.db.execute("DROP TRIGGER reject_url_update")
    store.clean_enclosure_urls()
    assert len(_stored_extended_episodes(legacy_database)) == 1
    assert len(store.search_episodes("variant description")) == 1
    assert store.search_episodes("clean description") == []


def test_cleanup_preserves_caller_transaction(legacy_database: Path) -> None:
    before = _stored_extended_episodes(legacy_database)
    store = Datastore(str(legacy_database))
    store.db.conn.execute("BEGIN")
    store.db.conn.execute("UPDATE feeds SET title = 'uncommitted title'")

    store.clean_enclosure_urls()

    assert store.db.conn.in_transaction
    assert store.db.execute("SELECT title FROM feeds").fetchone() == (
        "uncommitted title",
    )
    assert _stored_extended_episodes(legacy_database) == before
    store.db.conn.rollback()
    assert _stored_extended_episodes(legacy_database) == before
    assert store.db.execute("SELECT title FROM feeds").fetchone() == ("Test Feed",)


def test_get_recently_played_normalizes_query_param_extended_url(tmp_path) -> None:
    db_path = str(tmp_path / "test.db")
    store = Datastore(db_path)
    store.save_feed_and_episodes(
        feed=_make_feed(),
        episodes=[_make_episode(overcast_id=1)],
    )
    store.save_extended_feed_and_episodes(
        feed={
            "xmlUrl": "https://example.com/feed-1.xml",
            "title": "Tech Podcast",
            "description": "About technology",
            "link": "https://example.com/feed-1",
            "itunes:image:href": "https://example.com/feed-1.png",
        },
        episodes=[
            {
                "enclosureUrl": "https://cdn.example.com/1.mp3?source=feed",
                "feedXmlUrl": "https://example.com/feed-1.xml",
                "title": "Episode 1",
                "description": "Query parameter enclosure URL",
                "link": "https://example.com/episodes/1",
                "itunes:image:href": "https://example.com/episodes/1.png",
                "pubDate": "Thu, 02 Jan 2025 00:00:00 GMT",
            },
        ],
    )

    with sqlite3.connect(db_path) as conn:
        urls = conn.execute(
            "SELECT enclosureUrl FROM episodes_extended ORDER BY rowid",
        ).fetchall()

    results = store.get_recently_played()

    assert len(results) == 1
    assert results[0]["episode_title"] == "Episode 1"
    assert urls == [("https://cdn.example.com/1.mp3",)]


def test_get_recently_played_falls_back_to_episode_url_for_missing_links(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "test.db")
    store = Datastore(db_path)
    store.save_feed_and_episodes(
        feed=_make_feed(),
        episodes=[_make_episode(overcast_id=1)],
    )
    store.save_extended_feed_and_episodes(
        feed={
            "xmlUrl": "https://example.com/feed-1.xml",
            "title": "Tech Podcast",
            "description": "About technology",
            "itunes:image:href": "https://example.com/feed-1.png",
        },
        episodes=[
            {
                "enclosureUrl": "https://cdn.example.com/1.mp3",
                "feedXmlUrl": "https://example.com/feed-1.xml",
                "title": "Episode 1",
                "description": "Missing feed and episode links",
                "itunes:image:href": "https://example.com/episodes/1.png",
                "pubDate": "Thu, 02 Jan 2025 00:00:00 GMT",
            },
        ],
    )

    results = store.get_recently_played()

    assert results[0]["link_"] == "https://example.com/1"


def test_clean_enclosure_urls_skips_deduplication_without_query_params(
    monkeypatch,
    tmp_path,
) -> None:
    db_path = str(tmp_path / "test.db")
    store = Datastore(db_path)
    store.save_extended_feed_and_episodes(
        feed={
            "xmlUrl": "https://example.com/feed-1.xml",
            "title": "Tech Podcast",
            "description": "About technology",
        },
        episodes=[
            {
                "enclosureUrl": "https://cdn.example.com/1.mp3",
                "feedXmlUrl": "https://example.com/feed-1.xml",
                "title": "Episode 1",
                "description": "Clean enclosure URL",
            },
        ],
    )

    def fail_deduplicate() -> None:
        msg = "Deduplication should be skipped when no query parameters exist"
        raise AssertionError(msg)

    monkeypatch.setattr(
        store,
        "_deduplicate_extended_enclosure_urls",
        fail_deduplicate,
    )

    store.clean_enclosure_urls()


def test_ensure_episode_download_column(tmp_path: Path) -> None:
    db_path = str(tmp_path / "test.db")
    store = Datastore(db_path)

    assert store.ensure_episode_download_column() is True
    assert store.ensure_episode_download_column() is False

    with sqlite3.connect(db_path) as conn:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(episodes)")]
    assert "enclosureDownloadPath" in columns


def test_audio_to_download_filters_recorded_and_null_enclosures(tmp_path: Path) -> None:
    db_path = str(tmp_path / "test.db")
    store = Datastore(db_path)
    store.save_feed_and_episodes(
        feed=_make_feed(),
        episodes=[_make_episode(overcast_id=i) for i in range(1, 4)],
    )
    store.ensure_episode_download_column()
    store.update_audio_download_path(overcast_id=2, audio_path="/audio/2.mp3")
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE episodes SET enclosureUrl = NULL WHERE overcastId = 3")

    rows = list(store.audio_to_download(starred_only=False))

    assert rows == [(1, "Episode 1", "https://cdn.example.com/1.mp3", "Test Feed")]


def test_audio_to_download_starred_only(tmp_path: Path) -> None:
    db_path = str(tmp_path / "test.db")
    store = Datastore(db_path)
    store.save_feed_and_episodes(
        feed=_make_feed(),
        episodes=[
            _make_episode(overcast_id=1),
            _make_episode(overcast_id=2, starred=True),
        ],
    )
    store.ensure_episode_download_column()

    rows = list(store.audio_to_download(starred_only=True))

    assert rows == [(2, "Episode 2", "https://cdn.example.com/2.mp3", "Test Feed")]


def test_update_audio_download_path(tmp_path: Path) -> None:
    db_path = str(tmp_path / "test.db")
    store = Datastore(db_path)
    store.save_feed_and_episodes(
        feed=_make_feed(),
        episodes=[_make_episode(overcast_id=1)],
    )
    store.ensure_episode_download_column()

    store.update_audio_download_path(overcast_id=1, audio_path="/audio/1.mp3")

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT enclosureDownloadPath FROM episodes WHERE overcastId = 1",
        ).fetchone()
    assert row == ("/audio/1.mp3",)
    assert list(store.audio_to_download(starred_only=False)) == []


def test_save_feed_and_episodes_preserves_existing_html_url_when_missing(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "test.db")
    store = Datastore(db_path)
    store.save_feed_and_episodes(feed=_make_feed(), episodes=[])
    store.save_feed_and_episodes(
        feed=Feed(
            overcastId=1,
            title="Test Feed",
            subscribed=True,
            notifications=False,
            xmlUrl="https://example.com/feed-1.xml",
            htmlUrl=None,
        ),
        episodes=[],
    )

    with sqlite3.connect(db_path) as conn:
        html_url = conn.execute(
            "SELECT htmlUrl FROM feeds WHERE overcastId = 1",
        ).fetchone()

    assert html_url == ("https://example.com/1",)
