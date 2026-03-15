from click.testing import CliRunner

from overcast_to_sqlite import cli
from overcast_to_sqlite.html import page


def test_generate_html_played_renders_starred_prefix_for_integer_values(
    monkeypatch,
    tmp_path,
):
    html_output_path = tmp_path / "played.html"

    class _FakeDatastore:
        def __init__(self, _db_path: str) -> None:
            pass

        def get_recently_played(self) -> list[dict[str, object]]:
            return [
                {
                    "description": "First description",
                    "episode_title": "Starred Episode",
                    "feed_title": "Example Feed",
                    "image_": "https://example.com/cover-1.jpg",
                    "link_": "https://example.com/starred",
                    "pubDate": "2025-01-02T00:00:00Z",
                    "starred": 1,
                    "userUpdatedDate": "2025-01-02T00:00:00Z",
                },
                {
                    "description": "Second description",
                    "episode_title": "Plain Episode",
                    "feed_title": "Example Feed",
                    "image_": "https://example.com/cover-2.jpg",
                    "link_": "https://example.com/plain",
                    "pubDate": "2025-01-02T00:00:00Z",
                    "starred": 0,
                    "userUpdatedDate": "2025-01-02T00:00:00Z",
                },
            ]

    monkeypatch.setattr(page, "Datastore", _FakeDatastore)

    page.generate_html_played("ignored.db", html_output_path)

    html_output = html_output_path.read_text()

    assert "⭐&nbsp;&nbsp;Starred Episode" in html_output
    assert "⭐&nbsp;&nbsp;Plain Episode" not in html_output
    assert "Plain Episode" in html_output


def test_generate_html_deleted_hides_starred_prefix_when_disabled(
    monkeypatch,
    tmp_path,
):
    html_output_path = tmp_path / "deleted.html"

    class _FakeDatastore:
        def __init__(self, _db_path: str) -> None:
            pass

        def get_deleted_episodes(self) -> list[dict[str, object]]:
            return [
                {
                    "description": "Deleted description",
                    "episode_title": "Deleted Episode",
                    "feed_title": "Example Feed",
                    "image_": "https://example.com/cover.jpg",
                    "link_": "https://example.com/deleted",
                    "pubDate": "2025-01-02T00:00:00Z",
                    "starred": "1",
                    "userUpdatedDate": "2025-01-02T00:00:00Z",
                },
            ]

    monkeypatch.setattr(page, "Datastore", _FakeDatastore)

    page.generate_html_deleted("ignored.db", html_output_path)

    html_output = html_output_path.read_text()

    assert "Deleted Episode" in html_output
    assert "⭐&nbsp;&nbsp;" not in html_output


def test_html_command_creates_output_directory(monkeypatch, tmp_path):
    db_path = tmp_path / "overcast.db"
    output_dir = tmp_path / "generated-html"
    runner = CliRunner()
    calls: list[tuple[str, object]] = []

    db_path.write_text("")

    def fake_generate_played(_db_path: str, html_output_path) -> None:
        calls.append(("played", html_output_path))

    def fake_generate_starred(_db_path: str, html_output_path) -> None:
        calls.append(("starred", html_output_path))

    def fake_generate_deleted(_db_path: str, html_output_path) -> None:
        calls.append(("deleted", html_output_path))

    monkeypatch.setattr(cli, "generate_html_played", fake_generate_played)
    monkeypatch.setattr(cli, "generate_html_starred", fake_generate_starred)
    monkeypatch.setattr(cli, "generate_html_deleted", fake_generate_deleted)

    result = runner.invoke(
        cli.cli,
        ["html", str(db_path), "--output", str(output_dir)],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert output_dir.is_dir()
    assert calls == [
        ("played", output_dir / "overcast-played.html"),
        ("starred", output_dir / "overcast-starred.html"),
        ("deleted", output_dir / "overcast-deleted.html"),
    ]
