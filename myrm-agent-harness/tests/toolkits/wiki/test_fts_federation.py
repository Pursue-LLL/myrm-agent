"""Which shared indexes a query reaches."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest

from myrm_agent_harness.toolkits.wiki.retrieval.fts_federation import MAX_FEDERATED_DATABASES, attached_tables


@pytest.fixture(params=[sqlite3.Row, None], ids=["row-factory", "tuple-factory"])
def conn(request: pytest.FixtureRequest) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = request.param
    yield connection
    connection.close()


def _attach(conn: sqlite3.Connection, alias: str, *tables: str) -> None:
    """Attach an empty in-memory shared index that holds the given tables."""
    conn.execute(f"ATTACH DATABASE ':memory:' AS {alias}")
    for table in tables:
        conn.execute(f"CREATE TABLE {alias}.{table} (concept_name)")


def test_a_connection_without_shared_indexes_reads_only_its_own_table(conn: sqlite3.Connection) -> None:
    assert attached_tables(conn, "wiki_fts") == ["wiki_fts"]


def test_every_attached_shared_index_with_the_table_is_added_in_alias_order(conn: sqlite3.Connection) -> None:
    _attach(conn, "pub_1", "wiki_fts")
    _attach(conn, "pub_0", "wiki_fts")

    assert attached_tables(conn, "wiki_fts") == ["wiki_fts", "pub_0.wiki_fts", "pub_1.wiki_fts"]


def test_a_shared_index_without_the_table_is_skipped(conn: sqlite3.Connection) -> None:
    _attach(conn, "pub_0", "other")
    _attach(conn, "pub_1", "wiki_fts")

    assert attached_tables(conn, "wiki_fts") == ["wiki_fts", "pub_1.wiki_fts"]


def test_the_table_is_looked_up_by_name_so_edges_work_like_pages(conn: sqlite3.Connection) -> None:
    _attach(conn, "pub_0", "wiki_edges")

    assert attached_tables(conn, "wiki_edges") == ["wiki_edges", "pub_0.wiki_edges"]
    assert attached_tables(conn, "wiki_fts") == ["wiki_fts"]


def test_attached_databases_outside_the_shared_alias_range_are_ignored(conn: sqlite3.Connection) -> None:
    _attach(conn, "scratch", "wiki_fts")
    _attach(conn, f"pub_{MAX_FEDERATED_DATABASES}", "wiki_fts")

    assert attached_tables(conn, "wiki_fts") == ["wiki_fts"]
