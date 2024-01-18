#!/usr/bin/env python
from pathlib import Path
from time import sleep

import click

from .datastore import Datastore
from .feed import fetch_xml_and_extract
from .overcast import (
    auth_and_save_cookies,
    extract_feed_and_episodes_from_opml,
    extract_playlists_from_opml,
    fetch_opml,
)
from .utils import _archive_path


@click.group
@click.version_option()
def cli() -> None:
    """Save data from Overcast extended OPML to a SQLite database."""


@cli.command()
@click.option(
    "-a",
    "--auth",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False),
    default="auth.json",
    help="Path to save auth cookie, defaults to auth.json",
)
def auth(auth: str) -> None:
    """Save authentication credentials to a JSON file."""
    click.echo("Please login to Overcast")
    click.echo(
        f"Your password is not stored but an auth cookie will be saved to {auth}",
    )
    click.echo()
    email = click.prompt("Email")
    password = click.prompt("Password")
    auth_and_save_cookies(email, password, auth)


@cli.command()
@click.argument(
    "db_path",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False),
    default="overcast.db",
)
@click.option(
    "-a",
    "--auth",
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
def save(db_path: str, auth: str, load: str | None, no_archive: bool, verbose: bool) -> None:
    """Save Overcast info to SQLite database."""
    db = Datastore(db_path)
    ingested_feed_ids = set()
    if load:
        xml = Path(load).read_text()
    else:
        xml = fetch_opml(
            auth,
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
        title = f[0].replace("/", "").replace(":", "").replace('"', "")
        url = f[1]
        feed, episodes = fetch_xml_and_extract(
            url,
            title,
            None if no_archive else _archive_path(db_path, "feeds"),
            verbose,
        )
        if verbose:
            print(f"Extracting {title} with {len(episodes)} episodes")
            print(feed)
        if "errorCode" in feed:
            print(f"Found error: {feed['errorCode']}")
        db.save_extended_feed_and_episodes(feed, episodes)
        if verbose:
            print("...")
        sleep(3)


if __name__ == "__main__":
    cli()
