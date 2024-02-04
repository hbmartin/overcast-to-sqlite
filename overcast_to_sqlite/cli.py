#!/usr/bin/env python

from pathlib import Path

import click
import requests

from overcast_to_sqlite.exceptions import NoTranscriptsUrlError

from .datastore import Datastore
from .feed import fetch_xml_and_extract
from .overcast import (
    auth_and_save_cookies,
    extract_feed_and_episodes_from_opml,
    extract_playlists_from_opml,
    fetch_opml,
)
from .utils import _archive_path, _file_extension_for_type, _sanitize_for_path


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
        xml = fetch_opml(
            auth_path,
            None if no_archive else _archive_path(db_path, "overcast"),
            verbose,
        )

    for playlist in extract_playlists_from_opml(xml):
        if verbose:
            print(f"Extracting playlist: {playlist['title']}")
        db.save_playlist(playlist)
    for feed, episodes in extract_feed_and_episodes_from_opml(xml):
        if verbose:
            print(f"Extracting {feed['title']} with {len(episodes)} episodes")
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
def extend(db_path: str, no_archive: bool, verbose: bool) -> None:
    """Download XML feed and extract all feed and episode tags and attributes."""
    db = Datastore(db_path)
    feeds_to_extend = db.get_feeds_to_extend()
    if verbose:
        print(f"Found {len(feeds_to_extend)} feeds to extend")
    for f in feeds_to_extend:
        title = _sanitize_for_path(f[0])
        url = f[1]
        feed, episodes = fetch_xml_and_extract(
            url,
            title,
            None if no_archive else _archive_path(db_path, "feeds"),
            verbose,
        )
        if verbose:
            print(f"Extracting {title} with {len(episodes)} episodes")
        if "errorCode" in feed:
            print(f"⛔️ Found error: {feed['errorCode']}")
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
def transcripts(
    db_path: str,
    archive_path: str,
    starred_only: bool,
    verbose: bool,
) -> None:
    """Download available transcripts for all or starred episodes."""
    db = Datastore(db_path)

    transcripts_path = (
        Path(archive_path) if archive_path else _archive_path(db_path, "transcripts")
    )

    if not transcripts_path.exists():
        transcripts_path.mkdir(parents=True)
        if verbose:
            print(f"Created {transcripts_path}")

    try:
        for title, url, mimetype, enclosure, feed_title in db.transcripts_to_download(
            starred_only,
        ):
            if verbose:
                print(f"Downloading {title} from {url}")
            response = requests.get(url)
            if not response.ok:
                print(f"⛔ Error downloading {title} @ {url}: {response.status_code}")
                if verbose:
                    print(response.headers)
                    print(response.text)
                continue
            feed_path = transcripts_path / _sanitize_for_path(feed_title)
            if not feed_path.exists():
                feed_path.mkdir(parents=True)
            file_ext = _file_extension_for_type(response.headers, mimetype)
            file_path = feed_path / (_sanitize_for_path(title) + file_ext)
            with file_path.open(mode="wb") as file:
                file.write(response.content)
                db.update_transcript_download_paths(
                    enclosure,
                    str(file_path.absolute()),
                )
    except NoTranscriptsUrlError:
        print("🤔 No transcript URLs found in database, running extend command")
        extend(db_path, no_archive=False, verbose=verbose)
        print("🔁 Please re-run the download command")


if __name__ == "__main__":
    cli()
