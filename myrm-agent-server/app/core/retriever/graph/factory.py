"""Graph Store Factory.

Creates graph store instances based on environment configuration.
Default: SQLiteGraphStore (zero external dependencies).
Optional: AGEStore (requires PostgreSQL + Apache AGE, explicit DATABASE_URL).
"""

import logging

from myrm_agent_harness.toolkits.memory.graph import GraphStore

logger = logging.getLogger(__name__)

_graph_store: GraphStore | None = None
_graph_store_created = False


def get_graph_store(memory_enabled: bool = False) -> GraphStore | None:
    """Get or create the graph store singleton.

    When memory_enabled=False the call returns None without caching,
    so a later call with memory_enabled=True can still create the store.
    Once created (or failed), the result is cached for the process lifetime.
    """
    global _graph_store, _graph_store_created
    if _graph_store_created:
        return _graph_store

    if not memory_enabled:
        return None

    try:
        from app.config.settings import settings

        pg_url = settings.database.database_url
        if pg_url:
            from myrm_agent_harness.toolkits.memory.graph.age_store import AGEStore

            logger.info("Using PostgreSQL + AGE graph store (explicit DATABASE_URL)")
            _graph_store = AGEStore(dsn=pg_url, graph_name="episodic_memory")
        else:
            from myrm_agent_harness.toolkits.memory.graph import SQLiteGraphStore

            sqlite_path = settings.database.sqlite_path
            logger.info("Using SQLite graph store: %s", sqlite_path)
            _graph_store = SQLiteGraphStore(db_path=sqlite_path)

    except Exception as e:
        logger.error("Failed to initialize graph store: %s", e)

    _graph_store_created = True
    return _graph_store


__all__ = [
    "get_graph_store",
]
