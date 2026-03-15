import datetime
import sqlite3
from typing import Self

from overcast_to_sqlite import datastore
from overcast_to_sqlite.constants import OVERCAST_ID
from overcast_to_sqlite.datastore import Datastore


class _FixedDateTime(datetime.datetime):
    @classmethod
    def now(cls, tz: datetime.tzinfo | None = None) -> Self:
        return cls(2025, 1, 2, tzinfo=tz or datetime.UTC)


def _feed() -> dict[str, object]:
    return {
        OVERCAST_ID: 1,
        "title": "Example Feed",
    }


def _episode(overcast_id: int, user_updated_date: str) -> dict[str, object]:
    return {
        OVERCAST_ID: overcast_id,
        "enclosureUrl": f"https://example.com/{overcast_id}.mp3",
        "feedId": 1,
        "title": f"Episode {overcast_id}",
        "url": f"https://example.com/{overcast_id}",
        "userUpdatedDate": user_updated_date,
    }


def test_save_feed_and_episodes_filters_when_limit_is_zero(monkeypatch, tmp_path):
    monkeypatch.setenv("OVERCAST_LIMIT_DAYS", "0")

    db_path = tmp_path / "overcast.db"
    store = Datastore(str(db_path))
    monkeypatch.setattr(datastore.datetime, "datetime", _FixedDateTime)

    store.save_feed_and_episodes(
        _feed(),
        [
            _episode(overcast_id=1, user_updated_date="2025-01-01T23:59:59Z"),
            _episode(overcast_id=2, user_updated_date="2025-01-02T00:00:00Z"),
        ],
    )

    with sqlite3.connect(db_path) as connection:
        titles = connection.execute(
            "SELECT title FROM episodes ORDER BY overcastId",
        ).fetchall()

    assert titles == [("Episode 2",)]


def test_cleanup_old_episodes_deletes_rows_when_limit_is_zero(
    monkeypatch,
    tmp_path,
):
    db_path = tmp_path / "overcast.db"
    store = Datastore(str(db_path))
    monkeypatch.setattr(datastore.datetime, "datetime", _FixedDateTime)
    store.save_feed_and_episodes(
        _feed(),
        [
            _episode(
                overcast_id=index,
                user_updated_date="2025-01-01T00:00:00Z",
            )
            for index in range(1, 102)
        ],
    )

    monkeypatch.setenv("OVERCAST_LIMIT_DAYS", "0")

    store.cleanup_old_episodes()

    with sqlite3.connect(db_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]

    assert count == 0
