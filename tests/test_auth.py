import json
import os

import pytest
from click.testing import CliRunner

from overcast_to_sqlite import cli


@pytest.fixture()
def mocked_starred(requests_mock):
    requests_mock.get("https://api.github.com/user", json={"id": 1, "login": "test"})
    m = requests_mock.get("https://api.github.com/user/starred", json=[])
    return m


def test_auth_command():
    runner = CliRunner()
    with runner.isolated_filesystem():
        assert [] == os.listdir(".")
        result = runner.invoke(cli.cli, ["auth"], input="zzz")
        assert result.exit_code == 0
        assert ["auth.json"] == os.listdir(".")
        assert {"github_personal_token": "zzz"} == json.load(open("auth.json"))


def test_auth_file(mocked_starred):
    runner = CliRunner()
    with runner.isolated_filesystem():
        open("auth.json", "w").write(json.dumps({"github_personal_token": "xxx"}))
        result = runner.invoke(
            cli.cli,
            ["starred", "starred.db"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert mocked_starred.called
        assert mocked_starred.last_request.headers["authorization"] == "token xxx"


def test_auth_environment_variable(mocked_starred, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "xyz")
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli.cli,
            ["starred", "starred.db"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert mocked_starred.called
        assert mocked_starred.last_request.headers["authorization"] == "token xyz"
