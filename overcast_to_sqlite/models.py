from __future__ import annotations

import dataclasses
from typing import Any


@dataclasses.dataclass
class Playlist:
    title: str
    smart: int
    sorting: str
    includePodcastIds: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class Feed:
    overcastId: int
    title: str
    subscribed: bool
    notifications: bool
    xmlUrl: str
    htmlUrl: str
    overcastAddedDate: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class Episode:
    overcastId: int
    feedId: int
    title: str
    url: str
    overcastUrl: str
    played: bool
    userDeleted: bool
    enclosureUrl: str
    progress: int | None = None
    userUpdatedDate: str | None = None
    userRecommendedDate: str | None = None
    pubDate: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)
