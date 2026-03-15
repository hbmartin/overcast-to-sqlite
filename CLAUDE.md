## Python Practices
- Always use or add type hints
- Prefer @dataclasses where applicable
- Always use f-string over string formatting or concatenation (except in logging strings)
- Use async generators and comprehensions when they might provide benefits
- Use underscores in large numeric literals
- Use walrus assignment := where applicable
- Prefer to use named arguments when calling a method with more than one argument
- Use "list" instead of "List" and "dict" instead of "Dict" and "|" instead of "Union" for types
- Use "Self" for applicable types
- Use Structural Pattern Matching (match...case) where applicable
- Always use pathlib.Path for file operations, never use os.path

# Workflow
- Always run `uv run black overcast_to_sqlite; uv run ruff check overcast_to_sqlite --fix; uv run pyrefly check overcast_to_sqlite; uv run ty check overcast_to_sqlite` after making changes.
- Run `uv run lizard -Eduplicate overcast_to_sqlite; uv run pytest tests/` after finishing implementation.
- Any user facing changes (e.g. new CLI flags) should be documented in the `README.md`.
- Use `uv` not `python` for running scripts.
- Treat Type Hints as First-Class
- Prefer Explicitness and Small Functions
- Use modern Python features e.g. assignment expressions and Structural Pattern Matching where applicable
- Use a parenthesized tuple of exception classes in the except clause
