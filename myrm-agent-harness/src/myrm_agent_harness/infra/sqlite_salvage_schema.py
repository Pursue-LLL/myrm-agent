"""Sorts the entries of a SQLite ``sqlite_master`` into what the salvage engine replays.

[INPUT]
- rows: ``(type, name, sql)`` entries of ``sqlite_master`` (system ``sqlite_*`` objects already excluded).

[OUTPUT]
- classify_schema_objects: ``(tables, virtual_tables, indexes, views)`` as name -> DDL; shadow tables of virtual tables
  are left out because creating the virtual table recreates them.

[POS]
Schema classification of the salvage engine (``sqlite_salvage.py``). Pure and database-free, so every rule is
testable without a damaged file.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

# The tables FTS3/4/5 create next to a virtual table; each is named ``<virtual table><suffix>``.
_FTS_SHADOW_SUFFIXES = (
    "_data",
    "_idx",
    "_content",
    "_docsize",
    "_config",
    "_segments",
    "_segdir",
    "_stat",
)

# SQLite stores the statement that created the object, so only a statement that opens with these keywords is a
# virtual table. A plain table that merely mentions the word (a column such as ``is_virtual``) is not.
_CREATE_VIRTUAL_TABLE = re.compile(r"\s*CREATE\s+VIRTUAL\s+TABLE\b", re.IGNORECASE)

type SchemaObjects = tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, str]]


def classify_schema_objects(rows: Iterable[tuple[object, object, object]]) -> SchemaObjects:
    """Split ``sqlite_master`` rows into tables, virtual tables, secondary indexes and views.

    A table is a shadow table only when it is named after a virtual table of the same schema. The suffix alone says
    nothing: an application table such as ``conversation_recall_segments`` ends like an FTS4 shadow table and holds
    real rows that salvage has to copy.
    """
    entries = [
        (str(kind).lower(), str(name), sql if isinstance(sql, str) and sql else None) for kind, name, sql in rows
    ]
    virtual_names = {
        name for kind, name, sql in entries if kind == "table" and sql and _CREATE_VIRTUAL_TABLE.match(sql)
    }
    shadow_names = {f"{virtual}{suffix}" for virtual in virtual_names for suffix in _FTS_SHADOW_SUFFIXES}

    tables: dict[str, str] = {}
    virtual_tables: dict[str, str] = {}
    indexes: dict[str, str] = {}
    views: dict[str, str] = {}
    for kind, name, sql in entries:
        if sql is None or name in shadow_names:
            continue
        if kind == "table":
            (virtual_tables if name in virtual_names else tables)[name] = sql
        elif kind == "index":
            # Autoindexes belong to their table's constraints and come back with the table.
            if not name.startswith("sqlite_autoindex_"):
                indexes[name] = sql
        elif kind == "view":
            views[name] = sql
    return tables, virtual_tables, indexes, views
