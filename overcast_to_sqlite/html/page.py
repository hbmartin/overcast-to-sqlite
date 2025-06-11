import html
import re
from pathlib import Path
from html.parser import HTMLParser

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


class HTMLTagFixer(HTMLParser):
    def __init__(self):
        super().__init__()
        self.open_tags = []
        self.output = []
        
    def handle_starttag(self, tag, attrs):
        # Self-closing tags don't need closing tags
        self_closing_tags = {'br', 'hr', 'img', 'input', 'meta', 'link', 'area', 'base', 'col', 'embed', 'source', 'track', 'wbr'}
        
        attr_str = ''.join(f' {name}="{value}"' for name, value in attrs)
        self.output.append(f'<{tag}{attr_str}>')
        
        if tag.lower() not in self_closing_tags:
            self.open_tags.append(tag)
    
    def handle_endtag(self, tag):
        self.output.append(f'</{tag}>')
        if self.open_tags and self.open_tags[-1] == tag:
            self.open_tags.pop()
    
    def handle_data(self, data):
        self.output.append(data)
    
    def handle_entityref(self, name):
        self.output.append(f'&{name};')
    
    def handle_charref(self, name):
        self.output.append(f'&#{name};')
    
    def get_fixed_html(self):
        # Add closing tags for any unclosed tags in reverse order
        for tag in reversed(self.open_tags):
            self.output.append(f'</{tag}>')
        return ''.join(self.output)


def _fix_unclosed_html_tags(html_string: str) -> str:
    """Fix unclosed HTML tags by adding missing closing tags."""
    if not html_string.strip():
        return html_string
        
    fixer = HTMLTagFixer()
    try:
        fixer.feed(html_string)
        return fixer.get_fixed_html()
    except Exception:
        # If parsing fails, return original string
        return html_string


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
        ep[DESCRIPTION] = _fix_unclosed_html_tags(_convert_urls_to_links(ep[DESCRIPTION]))
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
