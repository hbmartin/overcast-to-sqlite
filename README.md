# overcast-to-sqlite

[![PyPI](https://img.shields.io/pypi/v/overcast-to-sqlite.svg)](https://pypi.org/project/overcast-to-sqlite/)
[![Tests](https://github.com/dogsheep/github-to-sqlite/workflows/Test/badge.svg)](https://github.com/dogsheep/github-to-sqlite/actions?query=workflow%3ATest)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/hbmartin/overcast-to-sqlite/blob/main/LICENSE)

Save data from GitHub to a SQLite database.

<!-- toc -->

- [How to install](#how-to-install)
- [Authentication](#authentication)
- [Fetching issues for a repository](#fetching-issues-for-a-repository)

<!-- tocstop -->

## How to install

    $ pip install overcast-to-sqlite

## Authentication

Create a GitHub personal access token: https://github.com/settings/tokens

Run this command and paste in your new token:

    $ github-to-sqlite auth

This will create a file called `auth.json` in your current directory containing the required value. To save the file at a different path or filename, use the `--auth=myauth.json` option.

As an alternative to using an `auth.json` file you can add your access token to an environment variable called `GITHUB_TOKEN`.

## Fetching issues for a repository

The `issues` command retrieves all of the issues belonging to a specified repository.

    $ github-to-sqlite issues github.db simonw/datasette

If an `auth.json` file is present it will use the token from that file. It works without authentication for public repositories but you should be aware that GitHub have strict IP-based rate limits for unauthenticated requests.

You can point to a different location of `auth.json` using `-a`:

    $ github-to-sqlite issues github.db simonw/datasette -a /path/to/auth.json

You can use the `--issue` option one or more times to load specific issues:

    $ github-to-sqlite issues github.db simonw/datasette --issue=1

Example: [issues table](https://github-to-sqlite.dogsheep.net/github/issues)

