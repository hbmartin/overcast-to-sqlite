"""Tests for the optional standalone dataset generator.

Run with the generator dependencies supplied using uv's --with options.
"""

import hashlib
import json
import sqlite3
import tarfile

import pytest

pq = pytest.importorskip("pyarrow.parquet")
pytest.importorskip("bs4")
pytest.importorskip("pypdf")

from scripts import generate_transcript_dataset as exporter  # noqa: E402


@pytest.mark.parametrize(
    ("name", "content", "expected_text", "expected_format"),
    [
        ("episode.txt", b"Alice: Hello\n\nBob: Hi", "Alice: Hello\nBob: Hi", "txt"),
        ("episode.srt", b"Alice: Hello", "Alice: Hello", "txt"),
        (
            "episode.bin",
            b"1\n00:00:01,000 --> 00:00:03,000\nHello &amp; goodbye\n",
            "Hello & goodbye",
            "srt",
        ),
        (
            "episode.vtt",
            b"WEBVTT\n\nNOTE ignored\n\n00:01.000 --> 00:02.000\n<v Alice>Hello</v>\n",
            "Alice: Hello",
            "vtt",
        ),
        (
            "episode.json",
            b'{"segments":[{"body":"Hello","speaker":"Alice"},{"text":"Goodbye"}]}',
            "Alice: Hello\nGoodbye",
            "json",
        ),
        (
            "episode.json",
            b'{"text":"Complete transcript","segments":[]}',
            "Complete transcript",
            "json",
        ),
        (
            "episode.html",
            (
                b"<nav>Navigation</nav><script>secret()</script><main><cite>Alice:</cite>"
                b"<time>00:01</time><p>Hello &amp; goodbye</p></main>"
            ),
            "Alice:\nHello & goodbye",
            "html",
        ),
        (
            "episode.xsl",
            (
                b'<pst:transcripts xmlns:pst="http://podlove.org/simple-transcripts">'
                b"<pst:speech><pst:item>Hello</pst:item><pst:item>Goodbye</pst:item>"
                b"</pst:speech></pst:transcripts>"
            ),
            "Hello\nGoodbye",
            "podlove",
        ),
        ("episode.txt", "Caf\u00e9".encode("utf-16"), "Caf\u00e9", "txt"),
    ],
)
def test_extract_mixed_formats(tmp_path, name, content, expected_text, expected_format):
    path = tmp_path / name
    path.write_bytes(content)
    text, file_format, _method = exporter.extract_text(path, content)
    assert text == expected_text
    assert file_format == expected_format


def test_detect_pdf_from_bytes():
    assert exporter.detect_format(b"%PDF-1.7\n", ".octet-stream")[0] == "pdf"


def test_generation_preserves_sources_failures_and_metadata(tmp_path):
    source = tmp_path / "transcripts"
    podcast = source / "Show"
    podcast.mkdir(parents=True)
    content = "Alice: Caf\u00e9\nBob: Hello".encode()
    (podcast / "Episode.txt").write_bytes(content)
    (podcast / "Broken.json").write_text("{invalid}")
    (podcast / ".DS_Store").write_bytes(b"do not publish")
    database = tmp_path / "overcast.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE feeds_extended (xmlUrl TEXT, title TEXT)")
        connection.execute(
            "CREATE TABLE episodes_extended (transcriptDownloadPath TEXT, title TEXT, "
            'feedXmlUrl TEXT, "podcast:transcript:url" TEXT, link TEXT, '
            "pubDate TEXT, enclosureUrl TEXT)",
        )
        connection.execute(
            "INSERT INTO feeds_extended VALUES (?, ?)",
            ("https://example.com/feed.xml", "Original Show"),
        )
        connection.execute(
            "INSERT INTO episodes_extended VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "/old/location/transcripts/Show/Episode.txt",
                "Original Episode",
                "https://example.com/feed.xml",
                "https://example.com/transcript.txt",
                "https://example.com/episode",
                "2026-10-13",
                "https://example.com/audio.mp3",
            ),
        )
    database_before = database.read_bytes()
    output = tmp_path / "dataset"
    summary = exporter.generate_dataset(source, output, database)
    rows = pq.read_table(output / "data/train.parquet").to_pylist()
    assert summary["files"] == len(rows)
    assert summary["extracted"] == 1
    assert summary["failed"] == 1
    assert summary["metadata_matched"] == 1
    assert database.read_bytes() == database_before
    episode = next(row for row in rows if row["raw_path"].endswith("Episode.txt"))
    assert episode["podcast"] == "Original Show"
    assert episode["episode"] == "Original Episode"
    assert episode["source_url"] == "https://example.com/transcript.txt"
    assert episode["sha256"] == hashlib.sha256(content).hexdigest()
    with tarfile.open(output / "raw-transcripts.tar.gz") as archive:
        original = archive.extractfile(episode["raw_path"])
        assert original is not None
        assert original.read() == content
        assert set(archive.getnames()) == {
            "raw/Show/Episode.txt",
            "raw/Show/Broken.json",
        }
        member = archive.getmember(episode["raw_path"])
        assert member.uid == member.gid == member.mtime == 0
        assert member.uname == member.gname == ""
    broken = next(row for row in rows if row["raw_path"].endswith("Broken.json"))
    assert broken["text"] is None
    assert broken["extraction_status"] == "error"
    assert "JSONDecodeError" in broken["extraction_error"]
    assert not (output / "raw/Show/.DS_Store").exists()
    assert "path: data/train.parquet" in (output / "README.md").read_text()
    assert "*.tar.gz filter=lfs" in (output / ".gitattributes").read_text()
    report = json.loads((output / "extraction-report.json").read_text())
    assert report["failures"][0]["raw_path"] == "raw/Show/Broken.json"


def test_generation_rejects_overlapping_paths(tmp_path):
    source = tmp_path / "transcripts"
    source.mkdir()
    (source / "episode.txt").write_text("Transcript")
    with pytest.raises(ValueError, match="must not overlap"):
        exporter.generate_dataset(source, source / "output", None)


def test_generation_rejects_symlinks(tmp_path):
    source = tmp_path / "transcripts"
    source.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("Outside content")
    (source / "episode.txt").symlink_to(outside)
    with pytest.raises(ValueError, match="Symlinked transcript"):
        exporter.generate_dataset(source, tmp_path / "dataset", None)


def test_html_prefers_transcript_container():
    transcript = "Alice: This is the transcript. " * 20
    html = f"<main>Show notes<div id='transcript'>{transcript}</div>More notes</main>"
    text, method = exporter.html_text(html)
    assert text == transcript.strip()
    assert method == "html_transcript"


def test_preserves_transcript_titles_starting_with_dot(tmp_path):
    source = tmp_path / "transcripts"
    source.mkdir()
    transcript = source / ".NET Core.txt"
    transcript.write_text("Transcript")
    (source / ".DS_Store").write_bytes(b"metadata")
    (source / "._.NET Core.txt").write_bytes(b"metadata")
    assert list(exporter.archive_files(source)) == [transcript]


def test_regeneration_removes_stale_bundle_members_and_legacy_output(tmp_path):
    source = tmp_path / "transcripts"
    source.mkdir()
    (source / "first.txt").write_text("First transcript")
    removed = source / "second.txt"
    removed.write_text("Second transcript")
    output = tmp_path / "dataset"
    exporter.generate_dataset(source, output, None)
    legacy_raw = output / "raw"
    legacy_raw.mkdir()
    (legacy_raw / "second.txt").write_text("Old generated copy")
    removed.unlink()
    summary = exporter.generate_dataset(source, output, None)
    assert summary["files"] == 1
    with tarfile.open(output / "raw-transcripts.tar.gz") as archive:
        assert archive.getnames() == ["raw/first.txt"]
    assert not legacy_raw.exists()
    assert (source / "first.txt").read_text() == "First transcript"
    assert pq.read_table(output / "data/train.parquet").num_rows == 1
