#!/usr/bin/env python
from pathlib import Path

import click
import requests

from .constants import TITLE
from .datastore import Datastore
from .feed import fetch_xml_and_extract
from .overcast import (
    auth_and_save_cookies,
    extract_feed_and_episodes_from_opml,
    extract_playlists_from_opml,
    fetch_opml,
)
from .utils import (
    _archive_path,
    _file_extension_for_type,
    _headers_from_auth,
    _sanitize_for_path,
)


@click.group
@click.version_option()
def cli() -> None:
    """Save listening history and feed/episode info from Overcast to SQLite."""


@cli.command()
@click.option(
    "-a",
    "--auth",
    "auth_path",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False),
    default="auth.json",
    help="Path to save auth cookie, defaults to auth.json",
)
def auth(auth_path: str) -> None:
    """Save authentication credentials to a JSON file."""
    click.echo("Please login to Overcast")
    click.echo(
        f"Your password is not stored but an auth cookie will be saved to {auth_path}",
    )
    click.echo()
    email = click.prompt("Email")
    password = click.prompt("Password")
    auth_and_save_cookies(email, password, auth_path)


@cli.command()
@click.argument(
    "db_path",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False),
    default="overcast.db",
)
@click.option(
    "-a",
    "--auth",
    "auth_path",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=True),
    default="auth.json",
    help="Path to auth.json file",
)
@click.option(
    "--load",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=True, exists=True),
    help="Load OPML from this file instead of the API",
)
@click.option("-na", "--no-archive", is_flag=True)
@click.option("-v", "--verbose", is_flag=True)
def save(
    db_path: str,
    auth_path: str,
    load: str | None,
    no_archive: bool,
    verbose: bool,
) -> None:
    """Save Overcast info to SQLite database."""
    db = Datastore(db_path)
    ingested_feed_ids = set()
    if load:
        xml = Path(load).read_text()
    else:
        if not Path(auth_path).exists():
            auth(auth_path)
        print("🔉Fetching latest OPML from Overcast")
        xml = fetch_opml(
            auth_path,
            None if no_archive else _archive_path(db_path, "overcast"),
        )

    for playlist in extract_playlists_from_opml(xml):
        if verbose:
            print(f"▶️Saving playlist: {playlist['title']}")
        db.save_playlist(playlist)
    for feed, episodes in extract_feed_and_episodes_from_opml(xml):
        if len(episodes) == 0:
            if verbose:
                print(f"⚠️Skipping {feed[TITLE]} (no episodes)")
            continue
        if verbose:
            print(f"⤵️Saving {feed[TITLE]} (latest: {episodes[0][TITLE]})")
        ingested_feed_ids.add(feed["overcastId"])
        db.save_feed_and_episodes(feed, episodes)

    db.mark_feed_removed_if_missing(ingested_feed_ids)


@cli.command()
@click.argument(
    "db_path",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False),
    default="overcast.db",
)
@click.option("-na", "--no-archive", is_flag=True)
@click.option("-v", "--verbose", is_flag=True)
@click.option(
    "-a",
    "--auth",
    "auth_path",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=True),
    default="auth.json",
    help="Path to auth.json file",
)
def extend(
    db_path: str,
    no_archive: bool,
    verbose: bool,
    auth_path: str,
) -> None:
    """Download XML feed and extract all feed and episode tags and attributes."""
    db = Datastore(db_path)
    feeds_to_extend = db.get_feeds_to_extend()
    print(f"➡️Extending {len(feeds_to_extend)} feeds")

    for f in feeds_to_extend:
        title = _sanitize_for_path(f[0])
        url = f[1]
        feed, episodes = fetch_xml_and_extract(
            xml_url=url,
            title=title,
            archive_dir=None if no_archive else _archive_path(db_path, "feeds"),
            verbose=verbose,
            headers=_headers_from_auth(auth_path),
        )
        if len(episodes) == 0:
            if verbose:
                print(f"⚠️Skipping {title} (no episodes)")
            continue
        if verbose:
            print(f"⏩️Extending {title} (latest: {episodes[0][TITLE]})")
        if "errorCode" in feed:
            print(f"⛔️Found error: {feed['errorCode']}")
        db.save_extended_feed_and_episodes(feed, episodes)


@cli.command()
@click.argument(
    "db_path",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False),
    default="overcast.db",
)
@click.option(
    "-p",
    "--path",
    "archive_path",
    type=click.Path(file_okay=False, dir_okay=True, allow_dash=False),
)
@click.option("-s", "--starred-only", is_flag=True)
@click.option("-v", "--verbose", is_flag=True)
@click.option(
    "-a",
    "--auth",
    "auth_path",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=True),
    default="auth.json",
    help="Path to auth.json file",
)
def transcripts(
    db_path: str,
    archive_path: str | None,
    starred_only: bool,
    verbose: bool,
    auth_path: str,
) -> None:
    """Download available transcripts for all or starred episodes."""
    db = Datastore(db_path)

    transcripts_path = (
        Path(archive_path) if archive_path else _archive_path(db_path, "transcripts")
    )

    if not transcripts_path.exists():
        transcripts_path.mkdir(parents=True)
        print(f"🗂️Created {transcripts_path}")

    if db.ensure_transcript_columns():
        print("⚠️No transcript URLs found in database, please run `extend`")

    total = 0
    current_feed = None
    for title, url, mimetype, enclosure, feed_title in db.transcripts_to_download(
        starred_only,
    ):
        if current_feed != feed_title:
            current_feed = feed_title
            if verbose:
                print(f"🔽️Downloading transcripts for feed {feed_title}")
        if verbose:
            print(f"⬇️Downloading {title} @ {url}")
        try:
            response = requests.get(url, headers=_headers_from_auth(auth_path))
        except requests.exceptions.RequestException as e:
            print(f"⛔ Error downloading {url}: {e}")
            continue
        if not response.ok:
            print(f"⛔ Error code {response.status_code} downloading {url}")
            if verbose:
                print(response.headers)
                print(response.text)
            continue
        feed_path = transcripts_path / _sanitize_for_path(feed_title)
        feed_path.mkdir(exist_ok=True)
        file_ext = _file_extension_for_type(response.headers, mimetype)
        file_path = feed_path / (_sanitize_for_path(title) + file_ext)
        with file_path.open(mode="wb") as file:
            file.write(response.content)
            db.update_transcript_download_paths(
                enclosure,
                str(file_path.absolute()),
            )
            total += 1
    print(f"↘️Downloaded {total} transcripts")


@cli.command("all")
@click.pass_context
@click.argument(
    "db_path",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False),
    default="overcast.db",
)
@click.option(
    "-a",
    "--auth",
    "auth_path",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=True),
    default="auth.json",
    help="Path to auth.json file",
)
@click.option("-v", "--verbose", is_flag=True)
def save_extend_download(
    ctx: click.core.Context,
    db_path: str,
    auth_path: str,
    verbose: bool,
) -> None:
    ctx.invoke(
        save,
        db_path=db_path,
        auth_path=auth_path,
        load=None,
        no_archive=False,
        verbose=verbose,
    )
    ctx.invoke(
        extend,
        db_path=db_path,
        no_archive=False,
        verbose=verbose,
        auth_path=auth_path,
    )
    ctx.invoke(
        transcripts,
        db_path=db_path,
        archive_path=None,
        starred_only=False,
        verbose=verbose,
        auth_path=auth_path,
    )


if __name__ == "__main__":
    cli()
