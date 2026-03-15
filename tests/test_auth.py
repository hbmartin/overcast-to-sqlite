import json

from click.testing import CliRunner

from overcast_to_sqlite import cli


def test_auth_command_prompts_and_saves_cookie(monkeypatch):
    captured: dict[str, tuple[str, str, str]] = {}

    def fake_auth_and_save_cookies(email: str, password: str, auth_json: str) -> None:
        captured["args"] = (email, password, auth_json)

    monkeypatch.setattr(cli, "auth_and_save_cookies", fake_auth_and_save_cookies)
    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        ["auth", "--auth", "custom-auth.json"],
        input="listener@example.com\nsuper-secret\n",
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "super-secret" not in result.output
    assert captured["args"] == (
        "listener@example.com",
        "super-secret",
        "custom-auth.json",
    )


def test_auth_and_fetch_uses_cookie_environment_variable(monkeypatch):
    calls: list[tuple[str, str | None]] = []
    fake_session = object()

    def fake_session_from_cookie(cookie: str) -> object:
        calls.append(("cookie", cookie))
        return fake_session

    def fake_fetch_opml(session: object, archive: object) -> str:
        assert session is fake_session
        assert archive is None
        calls.append(("fetch", None))
        return "<opml />"

    monkeypatch.setenv("OVERCAST_COOKIE", "cookie-value")
    monkeypatch.setattr(cli, "_session_from_cookie", fake_session_from_cookie)
    monkeypatch.setattr(
        cli,
        "_session_from_json",
        lambda _auth_path: (_ for _ in ()).throw(
            AssertionError("unexpected auth file"),
        ),
    )
    monkeypatch.setattr(
        cli,
        "_run_auth_flow",
        lambda _auth_path: (_ for _ in ()).throw(AssertionError("unexpected prompt")),
    )
    monkeypatch.setattr(cli, "fetch_opml", fake_fetch_opml)

    assert cli._auth_and_fetch("auth.json", None) == "<opml />"  # noqa: SLF001
    assert calls == [("cookie", "cookie-value"), ("fetch", None)]


def test_auth_and_fetch_creates_missing_auth_file(monkeypatch, tmp_path):
    auth_path = tmp_path / "auth.json"
    calls: list[tuple[str, str]] = []
    fake_session = object()

    def fake_run_auth_flow(path: str) -> None:
        calls.append(("auth", path))
        auth_path.write_text(json.dumps({"overcast": {"o": "cookie", "qr": "-"}}))

    def fake_session_from_json(path: str) -> object:
        calls.append(("session", path))
        assert path == str(auth_path)
        return fake_session

    def fake_fetch_opml(session: object, archive: object) -> str:
        assert session is fake_session
        assert archive is None
        return "<opml />"

    monkeypatch.delenv("OVERCAST_COOKIE", raising=False)
    monkeypatch.setattr(cli, "_run_auth_flow", fake_run_auth_flow)
    monkeypatch.setattr(cli, "_session_from_json", fake_session_from_json)
    monkeypatch.setattr(cli, "fetch_opml", fake_fetch_opml)

    assert cli._auth_and_fetch(str(auth_path), None) == "<opml />"  # noqa: SLF001
    assert calls == [("auth", str(auth_path)), ("session", str(auth_path))]
