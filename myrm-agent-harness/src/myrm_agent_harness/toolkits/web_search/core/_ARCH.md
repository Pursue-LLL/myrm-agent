# core/

## Overview
Shared data models, exception hierarchy, and error classification for web search.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Re-exports common types, exceptions, error helpers | ✅ |
| common.py | Core | SearchResult (names the provider that served it) and Citation data models | ✅ |
| exceptions.py | Core | Web search exception hierarchy with format_for_llm; SearchAPIError text carries status and code but never the user query, so classifiers cannot read the query as a failure signal | ✅ |
| error_handling.py | Core | Search failure classification and ErrorContext SSOT; a 402 answer marks the account depleted whatever the body says, whether the status sits on the exception or in the context of the `SearchAPIError` that `WebSearcher` wraps it in | ✅ |

## Dependencies

- `utils.text_cleaner`
