import os
from pathlib import Path

from overcast_to_sqlite.datastore import Datastore


def generate_html_played(db_path: str, html_output_path: Path) -> None:
    db = Datastore(db_path)
    episodes = db.get_recently_played()
    print("__file__ attribute:", __file__)
    print(os.path.abspath(__file__))
    this_dir = Path(__file__).parent
    page_vars = {
        "title": "Recently Played",
        "css_path": this_dir / "mvp.css",
        "episodes": "",
    }
    page_template = (this_dir / "index.html").read_text()
    episode_template = (this_dir / "episode.html").read_text()
    for ep in episodes:
        print(ep)
        page_vars["episodes"] += episode_template.format_map(ep)
    html_output_path.write_text(page_template.format_map(page_vars))
