# overcast-to-sqlite

[![PyPI](https://img.shields.io/pypi/v/overcast-to-sqlite.svg)](https://pypi.org/project/overcast-to-sqlite/)
[![Lint](https://github.com/hbmartin/overcast-to-sqlite/actions/workflows/lint.yml/badge.svg)](https://github.com/hbmartin/overcast-to-sqlite/actions/workflows/lint.yml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Code style: black](https://img.shields.io/badge/🐧️-black-000000.svg)](https://github.com/psf/black)
[![Checked with pytype](https://img.shields.io/badge/🦆-pytype-437f30.svg)](https://google.github.io/pytype/)
[![Versions](https://img.shields.io/pypi/pyversions/overcast-to-sqlite.svg)](https://pypi.python.org/pypi/overcast-to-sqlite)
[![discord](https://img.shields.io/discord/823971286308356157?logo=discord&label=&color=323338)](https://discord.gg/EE7Hx4Kbny)
[![twitter](https://img.shields.io/badge/@hmartin-00aced.svg?logo=twitter&logoColor=black)](https://twitter.com/hmartin)

Save listening history and feed/episode info from Overcast to a SQLite database. Try exploring your podcast listening habits with [Datasette](https://datasette.io/)!

- [How to install](#how-to-install)
- [Authentication](#authentication)
- [Fetching and saving updates](#fetching-and-saving-updates)
- [Extending and saving full feeds](#extending-and-saving-full-feeds)
- [Downloading transcripts](#downloading-transcripts)

## How to install

    $ pip install overcast-to-sqlite

Or to upgrade:

    $ pip install --upgrade overcast-to-sqlite

## Authentication

Run this command to login to Overcast (note: neither your password nor email are saved, only the auth cookie):

    $ overcast-to-sqlite auth

This will create a file called `auth.json` in your current directory containing the required value. To save the file at a different path or filename, use the `--auth=myauth.json` option.

If you do not wish to save this information you can manually download the "All data" file [from the Overcast account page](https://overcast.fm/account) and pass it into the save command as described below.

## Fetching and saving updates

The `save` command retrieves all Overcast info and stores playlists, podcast feeds, and episodes in their respective tables with a primary key `overcastId`. 

    $ overcast-to-sqlite save

By default, this saves to `overcast.db` but this can be manually set.

    $ overcast-to-sqlite save someother.db

By default, it will attempt to use the info in `auth.json` file is present it will use the cookie from that file. You can point to a different location using `-a`:

    $ overcast-to-sqlite save -a /path/to/auth.json

Alternately, you can skip authentication by passing in an OPML file you downloaded from Overcast:

    $ overcast-to-sqlite save --load /path/to/overcast.opml

By default, the save command will save any OPML file it downloads adjacent to the database file in `archive/overcast/`. You can disable this behavior with `--no-archive` or `-na`.

For increased reporting verbosity, use the `-v` flag.

## Extending and saving full feeds

The `extend` command that will download the XML files for all feeds you are subscribed to and extract tags and attributes. These are stored in separate tables `feeds_extended` and `episodes_extended` with primary keys `xmlUrl` and  `enclosureUrl` respectively. (See points 4 and 5 below for more information.)

    $ overcast-to-sqlite extend

Like the save command, this will attempt to archive feeds to `archive/feeds/` by default. This can be disabled with `--no-archive` or `-na`.

It also supports the `-v` flag to print additional information.

There are a few caveats for this functionality:

1. The first time this is invoked will require downloading and parsing an XML file for each feed you are subscribed to. (Subsequent invocations only require  this for new episodes loaded by `save`) Because this command may take a long time to run if you have many feeds, it is recommended to use the `-v` flag to observe progress.
2. This will increase the size of your database by approximately 2 MB per feed, so may result in a large file if you subscribe to many feeds.
3. Certain feeds may not load due to e.g. authentication, rate limiting, or other issues. These will be logged to the console and the feed will be skipped. Likewise, an episode may appear in your episodes table but not in the extended information if it is no longer available.
4. The `_extended` tables use URLs as their primary key. This may potentially lead to unjoinable / orphaned episodes if the enclosure URL (i.e. URL of the audio file) has changed since Overcast stored it.
5. There is no guarantee of which columns will be present in these tables aside from URL, title, and description. This command attempts to capture and normalize all XML tags contained in the feed so it is likely that many columns will be created and only a few rows will have values for uncommon tags/attributes.

Any suggestions for improving on these caveats are welcome, please [open an issue](https://github.com/hbmartin/overcast-to-sqlite/issues)!

## Downloading transcripts

The `transcripts` command that will download the transcripts if available.

The `save` and `extend` commands MUST be run prior to this.

Episodes with a "podcast:transcript:url" value will be downloaded from that URL and the download's location will then be stored in "transcriptDownloadPath". 

    $ overcast-to-sqlite transcripts

Like previous commands, by default this will save transcripts to `archive/transcripts/<feed title>/<episode title>` by default.

A different path can be set with the `-p`/`--path` flag.

It also supports the `-v` flag to print additional information.

There is also a `-s` flag to only download transcripts for starred episodes.