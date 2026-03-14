import sqlite3
import textwrap
from pathlib import Path

from click.testing import CliRunner

from overcast_to_sqlite import cli

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
              progress="42"
              enclosureUrl="https://cdn.example.com/episode-1.mp3?source=feed"
              userUpdatedDate="2025-01-02T00:00:00Z"
              userRecommendedDate="2025-01-03T00:00:00Z"
              pubDate="Thu, 02 Jan 2025 00:00:00 GMT"
            />
          </outline>
        </outline>
      </body>
    </opml>
    """,
)


def test_save_load_persists_playlist_feed_and_episode():
    runner = CliRunner()

    with runner.isolated_filesystem():
        Path("overcast.opml").write_text(SAMPLE_OPML)

        result = runner.invoke(
            cli.cli,
            ["save", "overcast.db", "--load", "overcast.opml"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0

        with sqlite3.connect("overcast.db") as connection:
            playlist = connection.execute(
                "SELECT title, smart, sorting, includePodcastIds FROM playlists",
            ).fetchone()
            feed = connection.execute(
                "SELECT title, subscribed, notifications, xmlUrl FROM feeds",
            ).fetchone()
            episode = connection.execute(
                "SELECT title, feedId, played, progress, enclosureUrl FROM episodes",
            ).fetchone()

        assert playlist == ("Morning Queue", 1, "manual", "[101,202]")
        assert feed == ("Example Feed", 1, 0, "https://example.com/feed.xml")
        assert episode == (
            "Episode 1",
            101,
            1,
            42,
            "https://cdn.example.com/episode-1.mp3",
        )
