"""Federated wiki graph table access shared by the graph viewer and graph insights.

[INPUT]
- sqlite3::Connection (POS: wiki index connection with attached `pub_N` public databases)
- .fts_federation::attached_tables (POS: tables of the primary index and the attached shared indexes)
- .sidecar_index::_SIDECAR_PREFIX (POS: directory sidecar index entry prefix)

[OUTPUT]
- concept_rows_filter: SQL predicate for the rows of a `wiki_fts` table that are concept pages (not interim raw text, not sidecar entries)
- is_interim_raw_entry: Whether an index row name is interim raw text, the one row kind that has no page file
- federated_graph_queries: SQL selecting concept pages and edges across the local and public indexes

[POS]
Single definition of "which rows are graph nodes and edges", so the viewer, the insight
panel and community detection always analyze the same graph; the concept-page predicate is
shared with the callers that ask whether an index holds any page, and the interim-raw
predicate with the callers that read a row's page file and must tell a raw row from a page
whose file is gone.
"""

from __future__ import annotations

import sqlite3

from .fts_federation import attached_tables
from .sidecar_index import _SIDECAR_PREFIX

_INTERIM_RAW_PREFIX = "raw:"
_SIDECAR_ENTRY_PREFIX = f"{_SIDECAR_PREFIX}:"


def concept_rows_filter() -> str:
    """Exclude interim raw-text and directory-sidecar entries: they are not concept pages."""
    return (
        f"substr(concept_name, 1, {len(_INTERIM_RAW_PREFIX)}) != '{_INTERIM_RAW_PREFIX}' "
        f"AND substr(concept_name, 1, {len(_SIDECAR_ENTRY_PREFIX)}) != '{_SIDECAR_ENTRY_PREFIX}'"
    )


def is_interim_raw_entry(concept_name: str) -> bool:
    """Whether an index row name is raw text indexed before compilation (``WikiIndexer.index_raw_text``).

    A raw entry never has a page file, so it stands on its index row; any other concept row names a page, and a page
    whose file is gone is a stale row.
    """
    return concept_name.startswith(_INTERIM_RAW_PREFIX)


def federated_graph_queries(conn: sqlite3.Connection) -> tuple[str, str]:
    """Return ``(concept_names_sql, edges_sql)`` over the local and attached public indexes.

    ``concept_names_sql`` yields distinct ``concept_name`` rows of concept pages;
    ``edges_sql`` yields ``source, target, weight`` rows (duplicates across databases
    are left to the caller to collapse).
    """
    row_filter = concept_rows_filter()
    names_sql = " UNION ".join(
        f"SELECT concept_name FROM {table} WHERE {row_filter}" for table in attached_tables(conn, "wiki_fts")
    )
    edges_sql = " UNION ALL ".join(
        f"SELECT source, target, weight FROM {table}" for table in attached_tables(conn, "wiki_edges")
    )
    return names_sql, edges_sql
