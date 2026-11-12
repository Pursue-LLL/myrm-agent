# assignment_sweep/

## Overview

Secret assignment sweep: finds credential assignments written with quoted keys, bracketed environment or config keys and separator-prefixed words (`"api_key": "..."`, `os.environ["API_KEY"] = "..."`, `MY_API_KEY=...`), skips placeholders and benign code symbols, audits database connection URIs with a loopback development exemption, and reports masked previews. `find_assignment_matches` is the single one-line definition of a non-benign secret assignment and also reports the value span, so persistence can redact exactly the value.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Package facade: the single import point for the sweep engine, the one-line match helper, the database URL auditor and the domain types. | ✅ |
| `database_url_auditor.py` | Core | Recognizes database connection URIs that carry credentials and decides whether each is an exempt local-development DSN (loopback host plus a standard development credential pair) or a leak. | ✅ |
| `quoted_sweep_engine.py` | Core | Finds quoted, bracketed and plain key-value assignments of sensitive keys, drops placeholders and benign code symbols, folds in the database-URL audit and returns a masked report. | ✅ |
| `types.py` | Types | Key-family, notation and verdict enums plus the finding, report and DSN-audit models. | ✅ |
