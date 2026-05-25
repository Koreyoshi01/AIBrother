# Card Library

This folder is the writing workspace for AI Brother cards. Keep it separate
from upstream `nanobot/` runtime code.

## Organization

- `templates/`: canonical blank JSON cards for each card type.
- `drafts/`: generated or manually edited cards that are still being written.
- `archive/`: completed cards that should stay searchable but no longer change often.

The Python workflow reads cards recursively, so cards in all three folders can
be searched together. New cards written through `CardWorkflow()` default to
`drafts/`.

Use one JSON file per card. Keep evidence and relations as structured arrays so
later RAG, MCP, or nanobot integrations can consume the same files without a
format migration.
