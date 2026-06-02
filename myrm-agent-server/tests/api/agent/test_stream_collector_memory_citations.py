from app.services.agent.streaming_support.stream_collector import StreamContentCollector


def test_stream_collector_persists_memory_citation_refs() -> None:
    collector = StreamContentCollector()

    collector.feed_event(
        {
            "type": "tool_end",
            "tool_name": "memory_recall_tool",
            "cited_memory_ids": ["mem-1", "mem-1", "mem-2"],
            "cited_memory_refs": [
                {
                    "id": "mem-1",
                    "memory_type": "semantic",
                    "content": "User prefers concise answers.",
                    "score": 0.91,
                    "primary_namespace": "global",
                    "namespaces": ["global"],
                },
                {
                    "id": "mem-1",
                    "memory_type": "semantic",
                    "content": "Duplicate entry should be ignored.",
                },
                {
                    "id": "mem-2",
                    "memory_type": "episodic",
                    "content": "User discussed Shared Context governance.",
                    "score": 0.84,
                    "primary_namespace": "shared:customer-a",
                    "namespaces": ["global", "shared:customer-a"],
                },
            ],
        }
    )

    extra_data = collector.extra_data

    assert extra_data is not None
    assert extra_data["citedMemoryIds"] == ["mem-1", "mem-2"]
    assert extra_data["citedMemoryRefs"] == [
        {
            "id": "mem-1",
            "memory_type": "semantic",
            "content": "User prefers concise answers.",
            "score": 0.91,
            "primary_namespace": "global",
            "namespaces": ["global"],
        },
        {
            "id": "mem-2",
            "memory_type": "episodic",
            "content": "User discussed Shared Context governance.",
            "score": 0.84,
            "primary_namespace": "shared:customer-a",
            "namespaces": ["global", "shared:customer-a"],
        },
    ]


def test_stream_collector_persists_memory_citations_from_runtime_tool_alias() -> None:
    collector = StreamContentCollector()

    collector.feed_event(
        {
            "type": "tool_end",
            "tool_name": "memory_recall_tool",
            "cited_memory_ids": ["mem-runtime"],
            "cited_memory_refs": [
                {
                    "id": "mem-runtime",
                    "memory_type": "semantic",
                    "content": "Runtime tool alias should still persist citations.",
                }
            ],
        }
    )

    extra_data = collector.extra_data

    assert extra_data is not None
    assert extra_data["citedMemoryIds"] == ["mem-runtime"]
    assert extra_data["citedMemoryRefs"] == [
        {
            "id": "mem-runtime",
            "memory_type": "semantic",
            "content": "Runtime tool alias should still persist citations.",
        }
    ]
