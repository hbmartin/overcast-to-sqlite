# overcast-to-sqlite

[![PyPI](https://img.shields.io/pypi/v/overcast-to-sqlite.svg)](https://pypi.org/project/overcast-to-sqlite/)
[![Lint](https://github.com/hbmartin/overcast-to-sqlite/actions/workflows/lint.yml/badge.svg)](https://github.com/hbmartin/overcast-to-sqlite/actions/workflows/lint.yml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![ty](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ty/main/assets/badge/v0.json)](https://github.com/astral-sh/ty)
[![Versions](https://img.shields.io/pypi/pyversions/overcast-to-sqlite.svg)](https://pypi.python.org/pypi/overcast-to-sqlite)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/hbmartin/overcast-to-sqlite)
[![twitter](https://img.shields.io/badge/@hmartin-00aced.svg?logo=twitter&logoColor=black)](https://twitter.com/hmartin)

Save listening history and feed/episode info from Overcast to a SQLite database. Try exploring your podcast listening habits with [Datasette](https://datasette.io/)!

If you simply want a page showing your recently listened episodes, try out the sister project [overcast-to-pages](https://github.com/hbmartin/overcast-to-pages-template).

- [How to install](#how-to-install)
- [Commands](#commands)
- [Authentication](#authentication)
- [Fetching and saving updates](#fetching-and-saving-updates)
- [Extending and saving full feeds](#extending-and-saving-full-feeds)
- [Downloading transcripts](#downloading-transcripts)
- [Downloading chapters](#downloading-chapters)
- [Generating HTML pages](#generating-html-pages)
- [Running all commands](#running-all-commands)
- [Listening statistics](#listening-statistics)
- [Searching](#searching)
- [Database schema](#database-schema)
- [See also](#see-also)
- [Development](#development)

## How to install

Run it once without installing:

    $ uvx overcast-to-sqlite

Install it permanently if you want `overcast-to-sqlite` available for later commands:

    $ uv tool install overcast-to-sqlite

## Commands

| Command | Description |
|---------|-------------|
| `auth` | Save authentication credentials to a JSON file |
| `save` | Fetch and save Overcast playlists, feeds, and episodes |
| `extend` | Download XML feeds and extract all tags and attributes |
| `transcripts` | Download available transcripts for episodes |
| `chapters` | Download and store available chapters for episodes |
| `html` | Generate HTML pages for played, starred, and deleted episodes |
| `all` | Run save, extend, transcripts, and chapters sequentially |
| `stats` | Show listening statistics |
| `search` | Search episodes, feeds, and chapters using full-text search |

Run `overcast-to-sqlite --help` for a full list of options.

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

By default, it will use the cookie from `auth.json` if present. You can point to a different location using `-a`:

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

The `transcripts` command downloads available transcripts for episodes.

The `save` and `extend` commands MUST be run prior to this.

Episodes with a "podcast:transcript:url" value will be downloaded from that URL and the download's location will then be stored in "transcriptDownloadPath".

    $ overcast-to-sqlite transcripts

By default this will save transcripts to `archive/transcripts/<feed title>/<episode title>`.

A different path can be set with the `-p`/`--path` flag.

It also supports the `-v` flag to print additional information.

There is also a `-s` flag to only download transcripts for starred episodes.

## Downloading chapters

The `chapters` command downloads and stores available chapters for episodes. The `save` and `extend` commands MUST be run prior to this.

    $ overcast-to-sqlite chapters

By default, chapters are archived to `archive/` adjacent to the database file. A different path can be set with the `-p`/`--path` flag.

## Generating HTML pages

The `html` command generates static HTML pages for recently played, starred, and deleted episodes.

    $ overcast-to-sqlite html

This produces three files: `overcast-played.html`, `overcast-starred.html`, and `overcast-deleted.html` in the same directory as the database file.

A different output directory can be set with the `-o`/`--output` flag:

    $ overcast-to-sqlite html -o /path/to/output/

The directory passed to `--output` is created if it does not already exist.

## Running all commands

The `all` command runs `save`, `extend`, `transcripts`, and `chapters` sequentially in a single invocation:

    $ overcast-to-sqlite all

It supports the same `-a`/`--auth` and `-v`/`--verbose` flags as `save`.

## Listening statistics

The `stats` command shows a summary of your listening habits:

    $ overcast-to-sqlite stats

This displays total episodes played, total listening time, starred episodes, subscribed/removed feeds, and top podcasts ranked by episode count and listening time.

## Searching

The `search` command performs full-text search across episodes, feeds, and chapters. The `save` and `extend` commands must be run prior to this.

    $ overcast-to-sqlite search "machine learning"

Results are grouped by category (episodes, feeds, chapters). Use `--limit` / `-l` to control the maximum results per category (default: 20).

    $ overcast-to-sqlite search "interview" -l 5

## Database schema

### Core tables

| Table | Primary Key | Description |
|-------|------------|-------------|
| `feeds` | `overcastId` | Podcast feed metadata from Overcast |
| `episodes` | `overcastId` | Episode metadata and listening history |
| `playlists` | `title` | User-created playlists |
| `feeds_extended` | `xmlUrl` | Full RSS feed metadata (from `extend`) |
| `episodes_extended` | `enclosureUrl` | Full episode metadata from RSS (from `extend`) |
| `chapters` | (auto) | Episode chapter markers (from `chapters`) |

### Key columns

**feeds**: `overcastId`, `title`, `subscribed`, `overcastAddedDate`, `notifications`, `xmlUrl`, `htmlUrl`, `dateRemoveDetected`

**episodes**: `overcastId`, `feedId` (FK to feeds), `title`, `url`, `overcastUrl`, `played`, `progress` (seconds), `enclosureUrl`, `userUpdatedDate`, `userRecommendedDate` (starred date), `pubDate`, `userDeleted`

**feeds_extended**: `xmlUrl` (FK to feeds), `title`, `description`, `lastUpdated`, `link`, `guid`, plus dynamic columns from RSS XML

**episodes_extended**: `enclosureUrl` (FK to episodes), `feedXmlUrl` (FK to feeds_extended), `title`, `description`, `link`, `guid`, plus dynamic columns from RSS XML

**chapters**: `enclosureUrl` (FK to episodes), `guid`, `source`, `time` (seconds), `content`, `url`, `image`

### Views

| View | Description |
|------|-------------|
| `episodes_played` | Episodes where `played=1` or `progress > 300` |
| `episodes_starred` | Episodes with a `userRecommendedDate` |
| `episodes_deleted` | Episodes marked deleted but not played |

### Full-text search indexes

FTS5 indexes are available on:
- `feeds_extended` (`title`, `description`)
- `episodes_extended` (`title`, `description`)
- `chapters` (`content`)

These are queried by the `search` command, or directly via SQL with `MATCH` syntax.

## See also

- [Datasette](https://datasette.io/)
- [Podcast Transcript Convert](https://github.com/hbmartin/podcast-transcript-convert/)
- [Overcast Parser](https://github.com/hbmartin/overcast_parser)
- [Podcast Archiver](https://github.com/janw/podcast-archiver)

## Development

Pull requests are very welcome! For major changes, please open an issue first to discuss what you would like to change.

### Setup

```bash
git clone git@github.com:hbmartin/overcast-to-sqlite.git
cd overcast-to-sqlite
uv sync --dev
uv run overcast-to-sqlite all -v
```

### Code Formatting and Linting

```bash
uv run black overcast_to_sqlite
uv run ruff check overcast_to_sqlite --fix
uv run pyrefly check overcast_to_sqlite
uv run ty check overcast_to_sqlite
uv run pytest tests/
```

This project is linted and formatted with [ruff](https://docs.astral.sh/ruff/). Type checking is done with [pyrefly](https://github.com/facebook/pyrefly) and [ty](https://github.com/astral-sh/ty).

## Authors

* [Harold Martin](https://www.linkedin.com/in/harold-martin-98526971/) - harold.martin at gmail
