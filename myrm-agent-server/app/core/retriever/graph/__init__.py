"""Graph Store Toolkit — app-layer graph storage.

Re-exports framework GraphStore and provides app-layer factory.

Example::

    from app.core.retriever.graph import get_graph_store, GraphStore

    store = get_graph_store(memory_enabled=True)
    if store:
        node = await store.create_node(["Memory"], {"content": "..."})
        await store.close()
"""

from myrm_agent_harness.toolkits.memory.graph import GraphStore

from app.core.retriever.graph.factory import get_graph_store

__all__ = [
    "GraphStore",
    "get_graph_store",
]
