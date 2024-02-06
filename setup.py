from setuptools import setup
import os

VERSION = "0.3.0"


def get_long_description():
    with open(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "README.md"),
        encoding="utf8",
    ) as fp:
        return fp.read()


setup(
    name="overcast-to-sqlite",
    description="Save listening history and feed/episode info from Overcast to a SQLite database.",
    long_description=get_long_description(),
    long_description_content_type="text/markdown",
    author="Harold Martin",
    author_email="Harold.Martin@gmail.com",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Framework :: Datasette",
        "Intended Audience :: End Users/Desktop",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Typing :: Typed",
    ],
    url="https://github.com/hbmartin/overcast-to-sqlite",
    license="Apache License, Version 2.0",
    version=VERSION,
    packages=["overcast_to_sqlite"],
    keywords=["overcast", "sqlite", "datasette"],
    entry_points={
        "console_scripts": ["overcast-to-sqlite=overcast_to_sqlite.cli:cli"],
    },
    install_requires=["sqlite-utils", "requests", "click", "python-dateutil"],
    extras_require={
        "test": ["pytest", "requests-mock"],
        "lint": ["ruff", "pyroma", "pytype", "types-python-dateutil", "types-requests"],
    },
    tests_require=["overcast-to-sqlite[test]"],
    python_requires=">=3.10",
)
