import html
import re
from pathlib import Path

from overcast_to_sqlite.constants import DESCRIPTION
from overcast_to_sqlite.datastore import Datastore
from overcast_to_sqlite.html.htmltagfixer import HTMLTagFixer


def _convert_urls_to_links(text: str) -> str:
    # Regular expression for matching URLs
    url_pattern = r"(https?://\S+)"

    # Split the text into a list, separating <a> tags from other content
    parts = re.split(r"(<a\s+[^>]*>.*?</a>)", text, flags=re.IGNORECASE | re.DOTALL)

    result = []
    for part in parts:
        if part.strip().startswith("<a"):
            # If this part is an <a> tag, add it to the result without modification
            result.append(part)
        else:
            # For non-<a> tag parts, convert URLs to links
            converted = re.sub(url_pattern, r'<a href="\1">\1</a>', part)
            result.append(converted)

    return "".join(result)


def _fix_unclosed_html_tags(html_string: str) -> str:
    """Fix unclosed HTML tags by adding missing closing tags."""
    if not html_string.strip():
        return html_string

    fixer = HTMLTagFixer()
    try:
        fixer.feed(html_string)
        return fixer.get_fixed_html()
    except Exception:  # noqa: BLE001
        return html_string


def _generate_html_episodes(
    episodes: list[dict[str, str]],
    title: str,
    html_output_path: Path,
    date_field: str = "userUpdatedDate",
) -> None:
    """Generate HTML for any list of episodes."""
    this_dir = Path(__file__).parent
    page_vars = {
        "title": title,
        "style": Path(this_dir / "mvp.css").read_text(),
        "script": Path(this_dir / "search.js").read_text(),
        "episodes": "",
    }
    page_template = (this_dir / "index.html").read_text()
    episode_template = (this_dir / "episode.html").read_text()
    last_user_updated_date = None

    for ep in episodes:
        ep["episode_title"] = html.escape(ep["episode_title"])
        ep[DESCRIPTION] = _fix_unclosed_html_tags(
            _convert_urls_to_links(ep[DESCRIPTION]),
        )
        user_date = ep[date_field].split("T")[0] if ep.get(date_field) else ""
        if last_user_updated_date != user_date and user_date:
            page_vars["episodes"] += (
                "<h1><script>document.write("
                f'new Date("{ep[date_field]}").toLocaleDateString()'
                ")</script></h1><hr />"
            )
            last_user_updated_date = user_date

        if ep.get("starred") == "1":
            ep["starred"] = "⭐&nbsp;&nbsp;"

        try:
            page_vars["episodes"] += episode_template.format_map(ep)
        except KeyError as e:
            print(f"Error formatting episode: KeyError {e}")
            print(ep)
    html_output_path.write_text(page_template.format_map(page_vars))


def generate_html_played(db_path: str, html_output_path: Path) -> None:
    db = Datastore(db_path)
    episodes = db.get_recently_played()
    _generate_html_episodes(episodes, "Recently Played", html_output_path)


def generate_html_starred(db_path: str, html_output_path: Path) -> None:
    db = Datastore(db_path)
    episodes = db.get_starred_episodes()
    _generate_html_episodes(
        episodes,
        "Starred Episodes",
        html_output_path,
        date_field="userRecDate",
    )


def generate_html_deleted(db_path: str, html_output_path: Path) -> None:
    db = Datastore(db_path)
    episodes = db.get_deleted_episodes()
    _generate_html_episodes(
        episodes,
        "Deleted Episodes",
        html_output_path,
        show_starred_icon=False,
    )
