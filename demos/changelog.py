from pathlib import Path

from bs4 import BeautifulSoup

from overcast_to_sqlite.utils import _sanitize_for_path

keywords = [
    "richard hendricks",
    "erlich",
    "bachman",
    "gilfoyle",
    "dinesh",
    "jared dunn",
    "monica hall",
    "bighetti",
    "russ hanneman",
    "tres commas",
    "gavin belson",
    "laurie bream",
    "pied piper",
    " hooli",
    "peter gregory",
    "jack barker",
    "jian yang",
    "seefood",
    "not hotdog",
    "carla walsh",
    "ron laflamme",
    "dan melcher",
    "ben feldman",
    "raviga",
    "endframe",
    "bachmanity",
    "russfest",
    "coderag",
    "code/rag",
]


def main():
    pods = [
        _sanitize_for_path(x)
        for x in [
            "Founders Talk: Startups, CEOs, Leadership",
            "Go Time: Golang, Software Engineering",
            "JS Party: JavaScript, CSS, Web Development",
            "Practical AI: Machine Learning, Data Science",
            "Ship It! SRE, Platform Engineering, DevOps",
            "The Changelog: Software Development, Open Source",
        ]
    ]
    total_quotes = 0
    sv_quotes = {}
    for pod in pods:
        print(pod)
        sv_quotes[pod] = {}
        search_path = Path(f"archive/transcripts/{pod}")
        if search_path.exists():
            files = [*search_path.iterdir()]
            n_files = len(files)
            print(f"Found {n_files} files")
            for file in files:
                ep_name = str(file).split("/")[-1][:-5]
                content = file.read_text()
                soup = BeautifulSoup(content, "html.parser")
                body = soup.find("body")
                children = body.findChildren()
                children = [
                    (children[i], children[i + 1]) for i in range(0, len(children), 2)
                ]

                prev_child = None
                add_next = False
                for child in children:
                    lowercase_string = child[1].text.lower()
                    contains_word = any(word in lowercase_string for word in keywords)
                    if not contains_word and "silicon valley" in lowercase_string:
                        contains_word = any(
                            word in lowercase_string
                            for word in ["tv", "the show", "hbo"]
                        )
                    if contains_word:
                        total_quotes += 1
                        add_next = True
                        if ep_name not in sv_quotes[pod]:
                            sv_quotes[pod][ep_name] = []
                        if prev_child is not None:
                            sv_quotes[pod][ep_name].append(prev_child)
                            prev_child = None
                        sv_quotes[pod][ep_name].append(child)
                    elif add_next:
                        sv_quotes[pod][ep_name].append(child)
                        sv_quotes[pod][ep_name].append(("<hr />", ""))
                        add_next = False
                        prev_child = child
                    else:
                        prev_child = child

    html = f'<!DOCTYPE html><html><head><title>Changelog ❤️ Silicon Valley ({total_quotes} times!)</title><meta charset="utf-8"></head><body>'
    for pod in pods:
        if pod in sv_quotes:
            html += f"<h1>{pod}</h1>"
            for ep in sv_quotes[pod]:
                html += f"<h2>{ep}</h2>"
                for quote in sv_quotes[pod][ep]:
                    html += str(quote[0])
                    html += str(quote[1])
    html += "</body></html>"
    Path("big-head.html").write_text(html)


if __name__ == "__main__":
    main()
