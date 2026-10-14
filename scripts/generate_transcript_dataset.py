# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "beautifulsoup4>=4.13",
#   "charset-normalizer>=3.4",
#   "pyarrow>=19",
#   "pypdf>=5",
# ]
# ///
"""Build a Hugging Face dataset from the downloaded transcript archive.

Run with uv so the script's optional dependencies are installed automatically.
This script reads SQLite metadata without changing the database and never uploads.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import tarfile
from collections import Counter
from contextlib import closing
from datetime import UTC, datetime
from html import unescape
from pathlib import Path
from typing import TYPE_CHECKING, cast
from xml.etree import ElementTree

import pyarrow as pa
import pyarrow.parquet as pq
from bs4 import BeautifulSoup
from charset_normalizer import from_bytes
from pypdf import PdfReader
from pypdf.errors import PyPdfError

if TYPE_CHECKING:
    from collections.abc import Iterator

type Record = dict[str, str | None]

_TIMING = re.compile(r"^\s*(?:\d+:)?\d{2}:\d{2}[.,]\d+\s*-->\s*", re.MULTILINE)
_SCHEMA = pa.schema(
    [
        pa.field(name, pa.string())
        for name in (
            "id",
            "podcast",
            "episode",
            "text",
            "source_url",
            "feed_url",
            "episode_url",
            "published_at",
            "format",
            "raw_path",
            "sha256",
            "extraction_status",
            "extraction_method",
            "extraction_error",
        )
    ],
)
_BATCH_SIZE = 100
_MIN_HTML_TRANSCRIPT_LENGTH = 200
# This fixed XML namespace identifies Podlove elements; no network request is made.
_PODLOVE_NAMESPACE = "http://podlove.org/simple-transcripts"  # NOSONAR


def normalize_text(text: str) -> str:
    return "\n".join(
        cleaned for line in text.splitlines() if (cleaned := " ".join(line.split()))
    )


def decode_text(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except (UnicodeError,):  # noqa: B013
        if match := from_bytes(content).best():
            return str(match)
        msg = "Could not detect the text encoding"
        raise ValueError(msg) from None


def text_format(text: str, suffix: str) -> str:
    start = text.lstrip()
    if start.startswith("WEBVTT"):
        return "vtt"
    if _TIMING.search(text):
        return "srt"
    if suffix == ".json" or (start.startswith("{") and '"segments"' in start[:2000]):
        return "json"
    if start.startswith("<"):
        return "podlove" if _PODLOVE_NAMESPACE in text[:2000] else "html"
    if "\x00" in text:
        msg = "Unsupported binary content"
        raise ValueError(msg)
    return "txt"


def detect_format(content: bytes, suffix: str) -> tuple[str, str]:
    if content.startswith(b"%PDF-") or suffix.lower() == ".pdf":
        return "pdf", ""
    text = decode_text(content)
    return text_format(text, suffix.lower()), text


def subtitle_blocks(text: str) -> Iterator[list[str]]:
    block: list[str] = []
    for line in text.splitlines():
        if line.strip():
            block.append(line)
        elif block:
            yield block
            block = []
    if block:
        yield block


def subtitle_text(text: str) -> str:
    cues: list[str] = []
    for lines in subtitle_blocks(text):
        if (
            timing_index := next(
                (index for index, line in enumerate(lines) if _TIMING.match(line)),
                None,
            )
        ) is None:
            continue
        cue = " ".join(lines[timing_index + 1 :])
        cue = re.sub(r"<v(?:\.[^ >]+)?\s+([^>]+)>", r"\1: ", cue)
        cue = re.sub(r"<[^>]+>", "", cue)
        if cleaned := normalize_text(unescape(cue)):
            cues.append(cleaned)
    if not cues:
        msg = "No subtitle cues found"
        raise ValueError(msg)
    return "\n".join(cues)


def json_segment_text(segment: object) -> str:
    if not isinstance(segment, dict):
        msg = "A transcript segment is not an object"
        raise TypeError(msg)
    fields = cast("dict[str, object]", segment)
    body = fields.get("body", fields.get("text"))
    if not isinstance(body, str):
        msg = "A transcript segment has no body or text"
        raise TypeError(msg)
    if isinstance(speaker := fields.get("speaker"), str) and speaker:
        return f"{speaker}: {body}"
    return body


def json_text(text: str) -> str:
    data: object = json.loads(text)
    if isinstance(data, dict):
        fields = cast("dict[str, object]", data)
        if isinstance(body := fields.get("text"), str) and body.strip():
            return body
        data = fields.get("segments")
    if isinstance(data, list) and data:
        return "\n".join(json_segment_text(segment) for segment in data)
    msg = "No transcript text or segments found in JSON"
    raise ValueError(msg)


def html_text(text: str) -> tuple[str, str]:
    soup = BeautifulSoup(text, "html.parser")
    for element in soup.select(
        "script, style, nav, header, footer, aside, noscript, form, button, "
        "svg, iframe, time",
    ):
        element.decompose()
    candidates = soup.select(
        '[itemprop="transcript"], [id*="transcript"], [class*="transcript"]',
    )
    if (
        candidates
        and len(
            body := max(
                (element.get_text("\n", strip=True) for element in candidates),
                key=len,
            ),
        )
        >= _MIN_HTML_TRANSCRIPT_LENGTH
    ):
        return body, "html_transcript"
    if article := soup.select_one("article, main, [role='main']"):
        return article.get_text("\n", strip=True), "html_article"
    return soup.get_text("\n", strip=True), "html_body"


def extract_text(path: Path, content: bytes) -> tuple[str, str, str]:
    file_format, text = detect_format(content, path.suffix)
    method = file_format
    match file_format:
        case "pdf":
            text = "\n".join(
                page.extract_text() or "" for page in PdfReader(path).pages
            )
        case "srt" | "vtt":
            text = subtitle_text(text)
        case "json":
            text = json_text(text)
        case "podlove":
            root = ElementTree.fromstring(text)
            text = "\n".join(
                "".join(item.itertext())
                for item in root.iter()
                if item.tag.rsplit("}", 1)[-1] == "item"
            )
        case "html":
            text, method = html_text(text)
    if not (text := normalize_text(text)):
        msg = "No readable transcript text extracted"
        raise ValueError(msg)
    return text, file_format, method


def archive_files(source: Path) -> Iterator[Path]:
    for path in sorted(source.rglob("*")):
        if path.is_file() and not any(
            part in {".DS_Store", ".git", ".cache", "__pycache__"}
            or part.startswith("._")
            for part in path.relative_to(source).parts
        ):
            if path.is_symlink():
                msg = f"Symlinked transcript is not supported: {path}"
                raise ValueError(msg)
            yield path


def load_metadata(database: Path | None) -> dict[str, Record]:
    if database is None:
        return {}
    metadata: dict[str, Record] = {}
    with closing(
        sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True),
    ) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT e.transcriptDownloadPath AS path, e.title AS episode, "
            'f.title AS podcast, e."podcast:transcript:url" AS source_url, '
            "e.feedXmlUrl AS feed_url, e.link AS episode_url, "
            "e.pubDate AS published_at FROM episodes_extended AS e "
            "LEFT JOIN feeds_extended AS f ON f.xmlUrl = e.feedXmlUrl "
            "WHERE e.transcriptDownloadPath IS NOT NULL ORDER BY e.enclosureUrl",
        )
        for row in rows:
            if not isinstance(stored_path := row["path"], str):
                continue
            key = Path(*Path(stored_path).parts[-2:]).as_posix()
            metadata.setdefault(
                key,
                {
                    name: value if isinstance(value := row[name], str) else None
                    for name in (
                        "podcast",
                        "episode",
                        "source_url",
                        "feed_url",
                        "episode_url",
                        "published_at",
                    )
                },
            )
    return metadata


def transcript_record(path: Path, source: Path, metadata: dict[str, Record]) -> Record:
    relative = path.relative_to(source).as_posix()
    content = path.read_bytes()
    record: Record = {
        "id": hashlib.sha256(relative.encode()).hexdigest(),
        "podcast": path.parent.name,
        "episode": path.stem if path.suffix else path.name,
        "text": None,
        "source_url": None,
        "feed_url": None,
        "episode_url": None,
        "published_at": None,
        "format": path.suffix.lstrip(".") or "unknown",
        "raw_path": f"raw/{relative}",
        "sha256": hashlib.sha256(content).hexdigest(),
        "extraction_status": "ok",
        "extraction_method": None,
        "extraction_error": None,
    }
    record.update(
        {key: value for key, value in metadata.get(relative, {}).items() if value},
    )
    try:
        record["text"], record["format"], record["extraction_method"] = extract_text(
            path,
            content,
        )
    except (
        OSError,
        ValueError,
        TypeError,
        ElementTree.ParseError,
        PyPdfError,
    ) as error:
        record["extraction_status"] = "error"
        record["extraction_error"] = f"{type(error).__name__}: {error}"
    return record


def dataset_card(summary: dict[str, object], repo_id: str) -> str:
    return f"""---
pretty_name: Podcast Transcripts
tags:
  - podcasts
  - transcripts
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/train.parquet
---

# Podcast Transcripts

Downloaded podcast transcripts, with original files and extracted text. Generated
with [overcast-to-sqlite](https://github.com/hbmartin/overcast-to-sqlite) on
{summary['generated_at']}. This snapshot contains {summary['files']} archived files,
of which {summary['extracted']} have extracted text and {summary['failed']} have
extraction errors. `{summary['metadata_matched']}` rows have original source URLs.

## Contents and schema

`data/train.parquet` contains one row per archived file. `raw-transcripts.tar.gz`
preserves all original files under `raw/`, including their directory structure.
Multiple files can describe the same
episode, and identical content can occur in different rows. `train` is a single
collection, not a curated training/evaluation split.

| Column | Meaning |
| --- | --- |
| id | SHA-256 of the relative archive path; stable for a given path |
| podcast / episode | SQLite titles when matched, otherwise directory/filename |
| text | Extracted UTF-8 text; null when extraction fails |
| source_url | Original transcript URL when available |
| feed_url / episode_url | RSS feed and episode page URLs when available |
| published_at | Publication date as recorded in the feed, without date normalization |
| format | Detected content format; extension fallback for extraction failures |
| raw_path | Original file's path inside `raw-transcripts.tar.gz` |
| sha256 | SHA-256 of the original file bytes; usable for deduplication |
| extraction_status | `ok` or `error` |
| extraction_method | Text extraction strategy, including HTML selection strategy |
| extraction_error | Error description when extraction fails |

## Processing and limitations

Formats are detected from content and filename hints, including subtitle content
stored as `.bin` and PDFs stored as `.octet-stream`. Subtitle indices and timing
lines are removed; WebVTT voice labels are retained when present. JSON full text
or segments and Podlove XML items are read. PDFs use embedded text extraction
without OCR. HTML scripts and common navigation elements are removed; transcript
containers are preferred, then article/main content, then the remaining body.
`html_article` and `html_body` rows can include episode notes or other page text.
Plain text preserves speaker labels and any timing markers already in its text.
Whitespace is normalized. No translation, content deduplication, or transcript
accuracy correction is performed. Failed extractions remain as rows with null
text, and their original files remain available. See `extraction-report.json`.

Metadata uses an explicit selection of feed/episode fields from a read-only SQLite
connection. Source URLs and dates are null when no matching metadata is available.

## Loading

```python
from datasets import load_dataset

dataset = load_dataset("{repo_id}", split="train")
readable = dataset.filter(lambda row: row["extraction_status"] == "ok")
```

To download and unpack all original files:

```sh
uvx --from huggingface_hub hf download {repo_id} raw-transcripts.tar.gz \\
  --repo-type dataset --local-dir .
tar -xzf raw-transcripts.tar.gz
```

Each row's `raw_path` points to its file in the extracted `raw/` directory. The
bundle avoids thousands of individual file commits when publishing updates.

## Regeneration

The standalone generator and its dependency declarations are included in
`scripts/generate_transcript_dataset.py`. With the original archive and optional
Overcast SQLite database available, run:

```sh
uv run scripts/generate_transcript_dataset.py archive/transcripts \\
  --database overcast.db --output archive/huggingface/podcast-transcripts \\
  --repo-id {repo_id}
```

Generation is local. Upload the generated output directory to this dataset repo
using `hf upload --repo-type dataset`.

## Licensing and provenance

Transcripts originate from the podcasts identified in each row. Copyright and
any applicable licenses remain with their respective owners; this collection
does not grant a blanket license to the transcript content. The generator code
is covered by the project's Apache-2.0 license, included as `scripts/LICENSE`.
"""


def write_raw_archive(files: list[Path], source: Path, output: Path) -> None:
    archive_path = output / "raw-transcripts.tar.gz"
    temporary_archive = archive_path.with_suffix(".gz.tmp")
    with tarfile.open(temporary_archive, "w:gz", compresslevel=6) as archive:
        for path in files:
            member = tarfile.TarInfo(f"raw/{path.relative_to(source).as_posix()}")
            member.size = path.stat().st_size
            member.mode = 0o644
            with path.open("rb") as content:
                archive.addfile(member, content)
    temporary_archive.replace(archive_path)
    if (raw_directory := output / "raw").is_dir():
        shutil.rmtree(raw_directory)


def generate_dataset(
    source: Path,
    output: Path,
    database: Path | None,
    repo_id: str = "YOUR_USERNAME/podcast-transcripts",
) -> dict[str, object]:
    source, output = source.resolve(), output.resolve()
    if not source.is_dir():
        msg = f"Transcript directory does not exist: {source}"
        raise ValueError(msg)
    if output.is_relative_to(source) or source.is_relative_to(output):
        msg = "Source and output directories must not overlap"
        raise ValueError(msg)
    files = list(archive_files(source))
    if not files:
        msg = "No transcript files found"
        raise ValueError(msg)
    metadata = load_metadata(database)
    (output / "data").mkdir(parents=True, exist_ok=True)
    formats: Counter[str] = Counter()
    methods: Counter[str] = Counter()
    failures: list[Record] = []
    batch: list[Record] = []
    matched = 0
    parquet_path = output / "data/train.parquet"
    temporary_parquet = parquet_path.with_suffix(".parquet.tmp")
    with pq.ParquetWriter(
        temporary_parquet,
        _SCHEMA,
        compression="zstd",
    ) as writer:
        for index, path in enumerate(files, start=1):
            record = transcript_record(path, source, metadata)
            formats[cast("str", record["format"])] += 1
            methods[record["extraction_method"] or "error"] += 1
            matched += bool(record["source_url"])
            if record["extraction_status"] == "error":
                failures.append(
                    {key: record[key] for key in ("raw_path", "extraction_error")},
                )
            batch.append(record)
            if len(batch) >= _BATCH_SIZE:
                writer.write_table(pa.Table.from_pylist(batch, schema=_SCHEMA))
                batch.clear()
            if index % 500 == 0:
                print(f"Processed {index}/{len(files)} transcripts", flush=True)
        if batch:
            writer.write_table(pa.Table.from_pylist(batch, schema=_SCHEMA))
    temporary_parquet.replace(parquet_path)
    print("Bundling original transcripts", flush=True)
    write_raw_archive(files, source, output)
    summary: dict[str, object] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "files": len(files),
        "extracted": len(files) - len(failures),
        "failed": len(failures),
        "metadata_matched": matched,
        "formats": dict(sorted(formats.items())),
        "methods": dict(sorted(methods.items())),
        "failures": failures,
    }
    (output / "extraction-report.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "README.md").write_text(dataset_card(summary, repo_id), encoding="utf-8")
    (output / ".gitattributes").write_text(
        "*.tar.gz filter=lfs diff=lfs merge=lfs -text\n"
        "*.parquet filter=lfs diff=lfs merge=lfs -text\n",
        encoding="utf-8",
    )
    (output / "scripts").mkdir(exist_ok=True)
    script = Path(__file__).resolve()
    shutil.copy2(script, output / "scripts" / script.name)
    if (license_path := script.parent.parent / "LICENSE").is_file():
        shutil.copy2(license_path, output / "scripts/LICENSE")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        default=Path("archive/transcripts"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("archive/huggingface/podcast-transcripts"),
    )
    parser.add_argument(
        "--repo-id",
        default="YOUR_USERNAME/podcast-transcripts",
        help="Hugging Face dataset ID used in the generated loading example",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--database",
        type=Path,
        help="Optional read-only metadata database",
    )
    group.add_argument(
        "--no-database",
        action="store_true",
        help="Use directory/filename metadata only",
    )
    args = parser.parse_args()
    database = args.database
    if database is None and not args.no_database and Path("overcast.db").is_file():
        database = Path("overcast.db")
    try:
        summary = generate_dataset(args.source, args.output, database, args.repo_id)
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(1, f"Dataset generation failed: {error}\n")
    print(
        json.dumps(
            {key: value for key, value in summary.items() if key != "failures"},
            indent=2,
        ),
    )
    print(f"Dataset written to {args.output.resolve()}")


if __name__ == "__main__":
    main()
