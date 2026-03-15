import textwrap
from xml.etree import ElementTree

from overcast_to_sqlite.models import Episode, Feed, Playlist
from overcast_to_sqlite.overcast import (
    extract_feed_and_episodes_from_opml,
    extract_playlists_from_opml,
)

SAMPLE_OPML = textwrap.dedent(
    """\
    <?xml version="1.0" encoding="UTF-8"?>
    <opml version="2.0">
      <body>
        <outline text="playlists">
          <outline
            type="podcast-playlist"
            title="Morning Queue"
            smart="1"
            sorting="manual"
            includePodcastIds="101,202"
          />
          <outline
            type="podcast-playlist"
            title="No IDs Playlist"
            smart="0"
            sorting="newest"
          />
        </outline>
        <outline text="feeds">
          <outline
            type="rss"
            text="Example Feed"
            title="Example Feed"
            overcastId="101"
            xmlUrl="https://example.com/feed.xml"
            htmlUrl="https://example.com"
            subscribed="1"
            notifications="0"
            overcastAddedDate="2025-01-01T00:00:00Z"
          >
            <outline
              type="podcast-episode"
              overcastId="1001"
              title="Episode 1"
              url="https://example.com/episode-1"
              overcastUrl="https://overcast.fm/+episode1"
              played="1"
              progress="3600"
              enclosureUrl="https://cdn.example.com/episode-1.mp3?source=feed"
              userUpdatedDate="2025-01-02T00:00:00Z"
              userRecommendedDate="2025-01-03T00:00:00Z"
              pubDate="Thu, 02 Jan 2025 00:00:00 GMT"
            />
            <outline
              type="podcast-episode"
              overcastId="1002"
              title="Episode 2"
              url="https://example.com/episode-2"
              overcastUrl="https://overcast.fm/+episode2"
              enclosureUrl="https://cdn.example.com/episode-2.mp3"
              played="0"
              userDeleted="1"
              userUpdatedDate="2025-01-03T00:00:00Z"
              pubDate="Fri, 03 Jan 2025 00:00:00 GMT"
            />
          </outline>
          <outline
            type="rss"
            text="Empty Feed"
            title="Empty Feed"
            overcastId="202"
            xmlUrl="https://example.com/empty.xml"
            htmlUrl="https://example.com/empty"
            subscribed="0"
          />
        </outline>
      </body>
    </opml>
    """,
)


def test_extract_playlists_returns_playlist_dataclass():
    root = ElementTree.fromstring(SAMPLE_OPML)
    playlists = list(extract_playlists_from_opml(root))

    assert len(playlists) == 1
    assert isinstance(playlists[0], Playlist)
    assert playlists[0].title == "Morning Queue"
    assert playlists[0].smart == 1
    assert playlists[0].sorting == "manual"
    assert playlists[0].includePodcastIds == "[101,202]"


def test_extract_playlists_skips_without_podcast_ids():
    root = ElementTree.fromstring(SAMPLE_OPML)
    playlists = list(extract_playlists_from_opml(root))
    assert len(playlists) == 1


def test_extract_feeds_returns_feed_dataclass():
    root = ElementTree.fromstring(SAMPLE_OPML)
    feeds = list(extract_feed_and_episodes_from_opml(root))

    assert len(feeds) == 2
    feed, _ = feeds[0]
    assert isinstance(feed, Feed)
    assert feed.overcastId == 101
    assert feed.title == "Example Feed"
    assert feed.subscribed is True
    assert feed.notifications is False
    assert feed.xmlUrl == "https://example.com/feed.xml"
    assert feed.htmlUrl == "https://example.com"
    assert feed.overcastAddedDate is not None


def test_extract_episodes_returns_episode_dataclass():
    root = ElementTree.fromstring(SAMPLE_OPML)
    feeds = list(extract_feed_and_episodes_from_opml(root))

    _, episodes = feeds[0]
    assert len(episodes) == 2

    ep1 = episodes[0]
    assert isinstance(ep1, Episode)
    assert ep1.overcastId == 1001
    assert ep1.feedId == 101
    assert ep1.title == "Episode 1"
    assert ep1.played is True
    assert ep1.progress == 3600
    assert ep1.userRecommendedDate is not None


def test_episode_enclosure_url_strips_query_params():
    root = ElementTree.fromstring(SAMPLE_OPML)
    feeds = list(extract_feed_and_episodes_from_opml(root))

    _, episodes = feeds[0]
    assert episodes[0].enclosureUrl == "https://cdn.example.com/episode-1.mp3"


def test_episode_boolean_conversion():
    root = ElementTree.fromstring(SAMPLE_OPML)
    feeds = list(extract_feed_and_episodes_from_opml(root))

    _, episodes = feeds[0]
    assert episodes[0].played is True
    assert episodes[0].userDeleted is False
    assert episodes[1].played is False
    assert episodes[1].userDeleted is True


def test_empty_feed_yields_no_episodes():
    root = ElementTree.fromstring(SAMPLE_OPML)
    feeds = list(extract_feed_and_episodes_from_opml(root))

    _, episodes = feeds[1]
    assert episodes == []


def test_unsubscribed_feed_parsed():
    root = ElementTree.fromstring(SAMPLE_OPML)
    feeds = list(extract_feed_and_episodes_from_opml(root))

    feed, _ = feeds[1]
    assert feed.subscribed is False


def test_playlist_to_dict():
    playlist = Playlist(
        title="Test",
        smart=0,
        sorting="manual",
        includePodcastIds="[1,2]",
    )
    d = playlist.to_dict()
    assert d == {
        "title": "Test",
        "smart": 0,
        "sorting": "manual",
        "includePodcastIds": "[1,2]",
    }


def test_feed_to_dict():
    feed = Feed(
        overcastId=1,
        title="Test",
        subscribed=True,
        notifications=False,
        xmlUrl="https://example.com/feed.xml",
        htmlUrl="https://example.com",
    )
    d = feed.to_dict()
    assert d["overcastId"] == 1
    assert d["title"] == "Test"
    assert d["overcastAddedDate"] is None


def test_episode_to_dict():
    episode = Episode(
        overcastId=1,
        feedId=1,
        title="Test",
        url="https://example.com",
        overcastUrl="https://overcast.fm/+test",
        played=True,
        userDeleted=False,
        enclosureUrl="https://cdn.example.com/test.mp3",
        progress=3600,
    )
    d = episode.to_dict()
    assert d["overcastId"] == 1
    assert d["progress"] == 3600
    assert d["userUpdatedDate"] is None
