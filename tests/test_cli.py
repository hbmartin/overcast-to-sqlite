from click.testing import CliRunner

from overcast_to_sqlite import cli
from overcast_to_sqlite.datastore import Datastore
from overcast_to_sqlite.models import Episode, Feed


def _populate_db(db_path: str) -> None:
    store = Datastore(db_path)
    feed = Feed(
        overcastId=1,
        title="Tech Podcast",
        subscribed=True,
        notifications=False,
        xmlUrl="https://example.com/feed.xml",
        htmlUrl="https://example.com",
    )
    episodes = [
        Episode(
            overcastId=i,
            feedId=1,
            title=f"Episode {i}",
            url=f"https://example.com/{i}",
            overcastUrl=f"https://overcast.fm/+{i}",
            played=True,
            userDeleted=False,
            enclosureUrl=f"https://cdn.example.com/{i}.mp3",
            progress=3600,
            userUpdatedDate="2025-01-02T00:00:00+00:00",
        )
        for i in range(1, 4)
    ]
    store.save_feed_and_episodes(feed, episodes)


def test_stats_command_shows_listening_stats(tmp_path):
    db_path = str(tmp_path / "test.db")
    _populate_db(db_path)

    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        ["stats", db_path],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "Episodes played" in result.output
    assert "3" in result.output
    assert "Tech Podcast" in result.output


def test_stats_command_shows_duration(tmp_path):
    db_path = str(tmp_path / "test.db")
    _populate_db(db_path)

    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        ["stats", db_path],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "3h 0m" in result.output


def test_stats_command_empty_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    Datastore(db_path)

    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        ["stats", db_path],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "Episodes played:      0" in result.output


def test_search_command_no_results(tmp_path):
    db_path = str(tmp_path / "test.db")
    _populate_db(db_path)

    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        ["search", "nonexistent query xyz", db_path],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "No results found" in result.output


def test_search_command_with_extended_data(tmp_path):
    db_path = str(tmp_path / "test.db")
    _populate_db(db_path)

    store = Datastore(db_path)
    store.save_extended_feed_and_episodes(
        {
            "xmlUrl": "https://example.com/feed.xml",
            "title": "Tech Podcast",
            "description": "Technology news and reviews",
        },
        [
            {
                "enclosureUrl": "https://cdn.example.com/1.mp3",
                "feedXmlUrl": "https://example.com/feed.xml",
                "title": "Episode 1",
                "description": "About machine learning",
            },
        ],
    )

    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        ["search", "machine learning", db_path],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "Episode 1" in result.output


def test_format_duration():
    assert cli._format_duration(0) == "0m"  # noqa: SLF001
    assert cli._format_duration(60) == "1m"  # noqa: SLF001
    assert cli._format_duration(3600) == "1h 0m"  # noqa: SLF001
    assert cli._format_duration(3661) == "1h 1m"  # noqa: SLF001
    assert cli._format_duration(90_000) == "25h 0m"  # noqa: SLF001
