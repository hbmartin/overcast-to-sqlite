from setuptools import setup
import os

VERSION = "0.1.0"


def get_long_description():
    with open(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "README.md"),
        encoding="utf8",
    ) as fp:
        return fp.read()


setup(
    name="overcast-to-sqlite",
    description="Save data from Overcast extended OPML to a SQLite database",
    long_description=get_long_description(),
    long_description_content_type="text/markdown",
    author="Harold Martin",
    url="https://github.com/hbmartin/overcast-to-sqlite",
    license="Apache License, Version 2.0",
    version=VERSION,
    packages=["overcast_to_sqlite"],
    entry_points="""
        [console_scripts]
        overcast-to-sqlite=overcast_to_sqlite.cli:cli
    """,
    install_requires=["sqlite-utils", "requests", "click", "python-dateutil"],
    extras_require={"test": ["pytest", "requests-mock", "types-python-dateutil", "types-requests"]},
    tests_require=["overcast-to-sqlite[test]"],
)
