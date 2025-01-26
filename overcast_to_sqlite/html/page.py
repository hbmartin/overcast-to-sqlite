import html
import re
from pathlib import Path

from overcast_to_sqlite.constants import DESCRIPTION
from overcast_to_sqlite.datastore import Datastore


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


def generate_html_played(db_path: str, html_output_path: Path) -> None:
    db = Datastore(db_path)
    episodes = db.get_recently_played()
    this_dir = Path(__file__).parent
    page_vars = {
        "title": "Recently Played",
        "style": Path(this_dir / "mvp.css").read_text(),
        "script": Path(this_dir / "search.js").read_text(),
        "episodes": "",
    }
    page_template = (this_dir / "index.html").read_text()
    episode_template = (this_dir / "episode.html").read_text()
    last_user_updated_date = None
    for ep in episodes:
        ep["episode_title"] = html.escape(ep["episode_title"])
        ep[DESCRIPTION] = _convert_urls_to_links(ep[DESCRIPTION])
        user_date = ep["userUpdatedDate"].split("T")[0]
        if last_user_updated_date != user_date:
            page_vars["episodes"] += (
                "<h1><script>document.write("
                f'new Date("{ep["userUpdatedDate"]}").toLocaleDateString()'
                ")</script></h1><hr />"
            )
            last_user_updated_date = user_date
        if ep["starred"] == "1":
            ep["starred"] = "⭐&nbsp;&nbsp;"
        else:
            ep["starred"] = ""
        try:
            page_vars["episodes"] += episode_template.format_map(ep)
        except KeyError as e:
            print(f"Error formatting episode: KeyError {e}")
            print(ep)
    html_output_path.write_text(page_template.format_map(page_vars))
