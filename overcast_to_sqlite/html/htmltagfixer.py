from html.parser import HTMLParser
from typing import ClassVar


class HTMLTagFixer(HTMLParser):
    SELF_CLOSING_TAGS: ClassVar[set[str]] = {
        "br",
        "hr",
        "img",
        "input",
        "meta",
        "link",
        "area",
        "base",
        "col",
        "embed",
        "source",
        "track",
        "wbr",
    }

    def __init__(self):
        super().__init__()
        self.open_tags = []
        self.output = []

    def handle_starttag(self, tag, attrs):
        # Self-closing tags don't need closing tags
        attr_str = "".join(f' {name}="{value}"' for name, value in attrs)
        self.output.append(f"<{tag}{attr_str}>")

        if tag.lower() not in self.SELF_CLOSING_TAGS:
            self.open_tags.append(tag)

    def handle_endtag(self, tag):
        self.output.append(f"</{tag}>")
        if self.open_tags and self.open_tags[-1] == tag:
            self.open_tags.pop()

    def handle_data(self, data):
        self.output.append(data)

    def handle_entityref(self, name):
        self.output.append(f"&{name};")

    def handle_charref(self, name):
        self.output.append(f"&#{name};")

    def get_fixed_html(self):
        # Add closing tags for any unclosed tags in reverse order
        for tag in reversed(self.open_tags):
            self.output.append(f"</{tag}>")
        return "".join(self.output)
