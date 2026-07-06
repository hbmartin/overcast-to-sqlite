import sqlite3

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
            userRecommendedDate="2025-01-03T00:00:00+00:00" if i == 2 else None,
        )
        for i in range(1, 4)
    ]
    store.save_feed_and_episodes(feed, episodes)


def _mock_audio_urls(
    requests_mock,
    episode_ids: tuple[int, ...] = (1, 2, 3),
    content_type: str = "audio/mpeg",
) -> None:
    for i in episode_ids:
        requests_mock.get(
            f"https://cdn.example.com/{i}.mp3",
            content=f"audio {i}".encode(),
            headers={"content-type": content_type},
        )


def _download_paths(db_path: str) -> dict[int, str | None]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT overcastId, enclosureDownloadPath FROM episodes",
        ).fetchall()
    return dict(rows)


def test_audio_downloads_and_records_paths(tmp_path, requests_mock):
    db_path = str(tmp_path / "test.db")
    _populate_db(db_path)
    _mock_audio_urls(requests_mock)

    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        ["audio", db_path, "-p", str(tmp_path / "audio")],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    for i in range(1, 4):
        file_path = tmp_path / "audio" / "Tech Podcast" / f"Episode {i}.mp3"
        assert file_path.read_bytes() == f"audio {i}".encode()
    assert not list((tmp_path / "audio").rglob("*.part"))
    assert all(path is not None for path in _download_paths(db_path).values())


def test_audio_starred_only(tmp_path, requests_mock):
    db_path = str(tmp_path / "test.db")
    _populate_db(db_path)
    _mock_audio_urls(requests_mock, episode_ids=(2,))

    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        ["audio", db_path, "-p", str(tmp_path / "audio"), "-s"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert requests_mock.call_count == 1
    assert requests_mock.last_request.url == "https://cdn.example.com/2.mp3"
    paths = _download_paths(db_path)
    assert paths[2] is not None
    assert paths[1] is None
    assert paths[3] is None


def test_audio_skips_already_downloaded(tmp_path, requests_mock):
    db_path = str(tmp_path / "test.db")
    _populate_db(db_path)
    store = Datastore(db_path)
    store.ensure_episode_download_column()
    store.update_audio_download_path(overcast_id=1, audio_path="/existing/1.mp3")
    _mock_audio_urls(requests_mock, episode_ids=(2, 3))

    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        ["audio", db_path, "-p", str(tmp_path / "audio")],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    requested_urls = {request.url for request in requests_mock.request_history}
    assert requested_urls == {
        "https://cdn.example.com/2.mp3",
        "https://cdn.example.com/3.mp3",
    }
    assert _download_paths(db_path)[1] == "/existing/1.mp3"


def test_audio_http_error_skips_episode(tmp_path, requests_mock):
    db_path = str(tmp_path / "test.db")
    _populate_db(db_path)
    requests_mock.get("https://cdn.example.com/1.mp3", status_code=404)
    _mock_audio_urls(requests_mock, episode_ids=(2, 3))

    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        ["audio", db_path, "-p", str(tmp_path / "audio")],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "⛔ Error code 404" in result.output
    paths = _download_paths(db_path)
    assert paths[1] is None
    assert paths[2] is not None
    assert paths[3] is not None


def test_audio_default_path(tmp_path, requests_mock):
    db_path = str(tmp_path / "test.db")
    _populate_db(db_path)
    _mock_audio_urls(requests_mock)

    runner = CliRunner()
    result = runner.invoke(cli.cli, ["audio", db_path], catch_exceptions=False)

    assert result.exit_code == 0
    for i in range(1, 4):
        file_path = tmp_path / "archive" / "audio" / "Tech Podcast" / f"Episode {i}.mp3"
        assert file_path.exists()


def test_audio_extension_falls_back_to_url_type(tmp_path, requests_mock):
    db_path = str(tmp_path / "test.db")
    _populate_db(db_path)
    _mock_audio_urls(requests_mock, content_type="application/octet-stream")

    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        ["audio", db_path, "-p", str(tmp_path / "audio")],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    for i in range(1, 4):
        assert (tmp_path / "audio" / "Tech Podcast" / f"Episode {i}.mp3").exists()
