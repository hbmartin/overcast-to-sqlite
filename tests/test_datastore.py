import sqlite3

from overcast_to_sqlite.datastore import Datastore
from overcast_to_sqlite.models import Episode, Feed, Playlist


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
