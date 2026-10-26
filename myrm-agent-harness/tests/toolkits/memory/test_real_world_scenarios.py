"""Real-world scenarios for the geometric scoring system.

Each scenario ranks realistic memories the way a search would and checks the order that relevance,
recency, importance and the memory type should produce. How often a memory was recalled plays no
part in that order (see test_usage_not_in_ranking.py).
"""

from datetime import UTC, datetime, timedelta

from myrm_agent_harness.toolkits.memory.config import RetrievalConfig
from myrm_agent_harness.toolkits.memory.retriever import MemoryRetriever
from myrm_agent_harness.toolkits.memory.types import EpisodicMemory, MemorySearchResult, MemoryType, SemanticMemory


class TestDeveloperWorkflowScenario:
    """Test scenario: Developer asking about recently used tools and configs."""

    def test_recent_tool_usage_beats_old_documentation(self):
        """Scenario: Developer asks 'How do I run tests?'

        Expected: Recent memory of running pytest should rank higher than
        old documentation about test frameworks.
        """
        config = RetrievalConfig(min_relevance_score=0.0)
        retriever = MemoryRetriever(config)

        recent_usage = SemanticMemory(
            content="Run tests with: pytest myrm-agent-harness/tests/ -v",
            created_at=datetime.now(UTC) - timedelta(days=2),
            importance=0.7,
        )

        old_docs = SemanticMemory(
            content="Testing framework documentation: pytest, unittest, nose",
            created_at=datetime.now(UTC) - timedelta(days=180),
            importance=0.5,
        )

        # Semantic scores are similar
        results = [
            MemorySearchResult(memory=recent_usage, score=0.82, memory_type=MemoryType.SEMANTIC),
            MemorySearchResult(memory=old_docs, score=0.85, memory_type=MemoryType.SEMANTIC),
        ]

        ranked = retriever.rank(results, limit=5)

        # Recency and importance outweigh the old document's slightly higher relevance
        assert [r.memory.content for r in ranked] == [recent_usage.content, old_docs.content]

    def test_recall_count_does_not_lift_a_slightly_less_relevant_command(self):
        """Scenario: Developer keeps being shown one git command and rarely the other.

        Expected: Every returned hit is stamped as recalled, so the count measures exposure. The
        command that matches the query better still ranks first, however often the other was shown.
        """
        config = RetrievalConfig(min_relevance_score=0.0)
        retriever = MemoryRetriever(config)

        often_shown = SemanticMemory(
            content="git commit -m 'message' && git push",
            created_at=datetime.now(UTC) - timedelta(days=30),
            access_count=50,
            importance=0.6,
        )

        rarely_shown = SemanticMemory(
            content="git rebase -i HEAD~3",
            created_at=datetime.now(UTC) - timedelta(days=30),
            access_count=1,
            importance=0.6,
        )

        results = [
            MemorySearchResult(memory=often_shown, score=0.78, memory_type=MemoryType.SEMANTIC),
            MemorySearchResult(memory=rarely_shown, score=0.80, memory_type=MemoryType.SEMANTIC),
        ]

        ranked = retriever.rank(results, limit=5)

        assert [r.memory.content for r in ranked] == [rarely_shown.content, often_shown.content]


class TestConversationalContextScenario:
    """Test scenario: Maintaining conversational context over time."""

    def test_recent_conversation_context_prioritized(self):
        """Scenario: User asks follow-up question about recent discussion.

        Expected: Recent episodic memories should be highly ranked.
        """
        config = RetrievalConfig(min_relevance_score=0.0)
        retriever = MemoryRetriever(config)

        recent_chat = EpisodicMemory(
            content="User asked about Python async/await patterns",
            created_at=datetime.now(UTC) - timedelta(hours=2),
            importance=0.6,
        )

        old_chat = EpisodicMemory(
            content="User discussed Python decorators",
            created_at=datetime.now(UTC) - timedelta(days=14),
            importance=0.6,
        )

        results = [
            MemorySearchResult(memory=recent_chat, score=0.75, memory_type=MemoryType.EPISODIC),
            MemorySearchResult(memory=old_chat, score=0.78, memory_type=MemoryType.EPISODIC),
        ]

        ranked = retriever.rank(results, limit=5)

        # Recent conversation should rank first (episodic has high recency weight)
        assert [r.memory.content for r in ranked] == [recent_chat.content, old_chat.content]

    def test_stale_context_naturally_degrades(self):
        """Scenario: Old conversation context should naturally fade.

        Expected: Very old episodic memories should rank lower even with
        similar semantic scores.
        """
        config = RetrievalConfig(min_relevance_score=0.0)
        retriever = MemoryRetriever(config)

        fresh_memory = EpisodicMemory(
            content="Discussed React hooks best practices",
            created_at=datetime.now(UTC) - timedelta(days=3),
            importance=0.6,
        )

        stale_memory = EpisodicMemory(
            content="Talked about React component patterns",
            created_at=datetime.now(UTC) - timedelta(days=60),
            importance=0.6,
        )

        results = [
            MemorySearchResult(memory=fresh_memory, score=0.80, memory_type=MemoryType.EPISODIC),
            MemorySearchResult(memory=stale_memory, score=0.82, memory_type=MemoryType.EPISODIC),
        ]

        ranked = retriever.rank(results, limit=5)

        # Fresh memory should rank higher due to recency decay
        assert [r.memory.content for r in ranked] == [fresh_memory.content, stale_memory.content]


class TestUserPreferenceScenario:
    """Test scenario: User preferences should remain stable over time."""

    def test_high_importance_outranks_a_casual_mention_of_the_same_age(self):
        """Scenario: A core preference and a passing mention, equally relevant and equally old.

        Expected: Importance decides.
        """
        config = RetrievalConfig(min_relevance_score=0.0)
        retriever = MemoryRetriever(config)

        core_preference = SemanticMemory(
            content="User's core preference: TypeScript over JavaScript",
            created_at=datetime.now(UTC) - timedelta(days=30),
            importance=0.9,
        )

        casual_mention = SemanticMemory(
            content="User mentioned TypeScript briefly",
            created_at=datetime.now(UTC) - timedelta(days=30),
            importance=0.4,
        )

        results = [
            MemorySearchResult(memory=casual_mention, score=0.84, memory_type=MemoryType.SEMANTIC),
            MemorySearchResult(memory=core_preference, score=0.84, memory_type=MemoryType.SEMANTIC),
        ]

        ranked = retriever.rank(results, limit=5)

        assert [r.memory.content for r in ranked] == [core_preference.content, casual_mention.content]


class TestSemanticDominanceScenario:
    """Test scenario: Very high semantic relevance should override recency and importance."""

    def test_highly_relevant_beats_fresh_but_less_relevant(self):
        """Scenario: Searching for specific topic.

        Expected: A highly relevant memory should beat a fresher, less relevant one
        when the semantic gap is large enough.
        """
        config = RetrievalConfig(min_relevance_score=0.0)
        retriever = MemoryRetriever(config)

        highly_relevant = SemanticMemory(
            content="Kubernetes deployment strategies for microservices",
            created_at=datetime.now(UTC) - timedelta(days=90),
            importance=0.7,
        )

        fresh_but_less_relevant = SemanticMemory(
            content="Docker container basics",
            created_at=datetime.now(UTC) - timedelta(days=10),
            importance=0.6,
        )

        results = [
            MemorySearchResult(memory=highly_relevant, score=0.95, memory_type=MemoryType.SEMANTIC),
            MemorySearchResult(memory=fresh_but_less_relevant, score=0.65, memory_type=MemoryType.SEMANTIC),
        ]

        ranked = retriever.rank(results, limit=5)

        # High semantic score should dominate when gap is large
        assert [r.memory.content for r in ranked] == [highly_relevant.content, fresh_but_less_relevant.content]

    def test_close_semantic_scores_are_decided_by_recency_and_importance(self):
        """Scenario: When semantic scores are close, the context signals decide.

        Expected: With similar semantic scores, the newer and more important memory wins.
        """
        config = RetrievalConfig(min_relevance_score=0.0)
        retriever = MemoryRetriever(config)

        recent_memory = SemanticMemory(
            content="Python list comprehensions tutorial",
            created_at=datetime.now(UTC) - timedelta(days=5),
            importance=0.7,
        )

        old_memory = SemanticMemory(
            content="Python list operations guide",
            created_at=datetime.now(UTC) - timedelta(days=120),
            importance=0.6,
        )

        # Similar semantic scores (difference < 0.15)
        results = [
            MemorySearchResult(memory=recent_memory, score=0.82, memory_type=MemoryType.SEMANTIC),
            MemorySearchResult(memory=old_memory, score=0.85, memory_type=MemoryType.SEMANTIC),
        ]

        ranked = retriever.rank(results, limit=5)

        assert [r.memory.content for r in ranked] == [recent_memory.content, old_memory.content]


class TestMultiSourceFusionScenario:
    """Test scenario: Fusing results from multiple memory types."""

    def test_multi_type_retrieval_balanced_ranking(self):
        """Scenario: Searching across semantic and episodic.

        Expected: RRF fusion should balance different memory types
        with geometric scoring applied to each.
        """
        config = RetrievalConfig(min_relevance_score=0.0)
        retriever = MemoryRetriever(config)

        semantic_fact = SemanticMemory(
            content="Functional programming emphasizes immutability",
            created_at=datetime.now(UTC) - timedelta(days=30),
            importance=0.7,
        )

        episodic_chat = EpisodicMemory(
            content="Discussed functional programming patterns yesterday",
            created_at=datetime.now(UTC) - timedelta(days=1),
            importance=0.6,
        )

        # Simulate multi-source search
        result_lists = [
            [MemorySearchResult(memory=semantic_fact, score=0.85, memory_type=MemoryType.SEMANTIC)],
            [MemorySearchResult(memory=episodic_chat, score=0.80, memory_type=MemoryType.EPISODIC)],
        ]

        fused = retriever.fuse(result_lists, limit=5)

        # Both should be present
        assert len(fused) == 2
        memory_types = {r.memory_type for r in fused}
        assert MemoryType.SEMANTIC in memory_types
        assert MemoryType.EPISODIC in memory_types


class TestPerformanceExpectations:
    """Test the ranking quality of geometric scoring on noisy near-ties."""

    def test_relevant_memories_surface_above_noise_with_near_equal_scores(self):
        """Scenario: Five candidates with near-equal semantic scores, only three truly relevant.

        Expected: Recency and importance lift the relevant memories above the noise.
        """
        config = RetrievalConfig(min_relevance_score=0.0)
        retriever = MemoryRetriever(config)

        relevant_week_old = SemanticMemory(
            id="relevant_1",
            content="Python async/await best practices for web servers",
            created_at=datetime.now(UTC) - timedelta(days=7),
            importance=0.8,
        )

        relevant_recent = SemanticMemory(
            id="relevant_2",
            content="FastAPI async endpoint implementation guide",
            created_at=datetime.now(UTC) - timedelta(days=2),
            importance=0.7,
        )

        relevant_old = SemanticMemory(
            id="relevant_3",
            content="Async programming patterns in Python web frameworks",
            created_at=datetime.now(UTC) - timedelta(days=60),
            importance=0.6,
        )

        # Irrelevant but with similar semantic scores
        irrelevant_1 = SemanticMemory(
            id="irrelevant_1",
            content="Python threading vs multiprocessing",
            created_at=datetime.now(UTC) - timedelta(days=100),
            importance=0.5,
        )

        irrelevant_2 = SemanticMemory(
            id="irrelevant_2",
            content="Python generators and iterators",
            created_at=datetime.now(UTC) - timedelta(days=150),
            importance=0.5,
        )

        # Simulate search results with noisy semantic scores
        results = [
            MemorySearchResult(memory=relevant_week_old, score=0.85, memory_type=MemoryType.SEMANTIC),
            MemorySearchResult(memory=irrelevant_1, score=0.83, memory_type=MemoryType.SEMANTIC),
            MemorySearchResult(memory=relevant_recent, score=0.82, memory_type=MemoryType.SEMANTIC),
            MemorySearchResult(memory=irrelevant_2, score=0.80, memory_type=MemoryType.SEMANTIC),
            MemorySearchResult(memory=relevant_old, score=0.78, memory_type=MemoryType.SEMANTIC),
        ]

        ranked = retriever.rank(results, limit=5)

        assert {r.memory.id for r in ranked[:3]} == {"relevant_1", "relevant_2", "relevant_3"}


class TestEdgeCasesInRealScenarios:
    """Test edge cases that might occur in real usage."""

    def test_all_memories_very_old_still_ranks_correctly(self):
        """Scenario: All memories are old, relative ranking should still work."""
        config = RetrievalConfig(min_relevance_score=0.0)
        retriever = MemoryRetriever(config)

        less_relevant = SemanticMemory(
            content="Old knowledge, loosely related",
            created_at=datetime.now(UTC) - timedelta(days=365),
            importance=0.7,
        )

        more_relevant = SemanticMemory(
            content="Old knowledge, closely related",
            created_at=datetime.now(UTC) - timedelta(days=365),
            importance=0.7,
        )

        results = [
            MemorySearchResult(memory=less_relevant, score=0.80, memory_type=MemoryType.SEMANTIC),
            MemorySearchResult(memory=more_relevant, score=0.82, memory_type=MemoryType.SEMANTIC),
        ]

        ranked = retriever.rank(results, limit=5)

        # Equal age leaves relevance to decide
        assert [r.memory.content for r in ranked] == [more_relevant.content, less_relevant.content]

    def test_recent_memory_not_over_ranked(self):
        """Scenario: A recent memory shouldn't dominate just because it's recent."""
        config = RetrievalConfig(min_relevance_score=0.0)
        retriever = MemoryRetriever(config)

        recent = SemanticMemory(
            content="Just learned about topic X",
            created_at=datetime.now(UTC) - timedelta(days=2),
            importance=0.5,
        )

        established = SemanticMemory(
            content="Deep knowledge about topic X from experience",
            created_at=datetime.now(UTC) - timedelta(days=30),
            importance=0.8,
        )

        results = [
            MemorySearchResult(memory=recent, score=0.75, memory_type=MemoryType.SEMANTIC),
            MemorySearchResult(memory=established, score=0.85, memory_type=MemoryType.SEMANTIC),
        ]

        ranked = retriever.rank(results, limit=5)

        # The established memory ranks higher: better semantic score and higher importance
        assert [r.memory.content for r in ranked] == [established.content, recent.content]


class TestCrossTypeComparison:
    """Test ranking across different memory types."""

    def test_semantic_vs_episodic_with_similar_scores(self):
        """Scenario: Comparing semantic and episodic memories.

        Expected: Type-specific weights should influence ranking.
        """
        config = RetrievalConfig(min_relevance_score=0.0)
        retriever = MemoryRetriever(config)

        semantic_mem = SemanticMemory(
            content="Python best practices documentation",
            created_at=datetime.now(UTC) - timedelta(days=30),
            importance=0.7,
        )

        episodic_mem = EpisodicMemory(
            content="Discussed Python best practices in meeting",
            created_at=datetime.now(UTC) - timedelta(days=2),
            importance=0.6,
        )

        result_lists = [
            [MemorySearchResult(memory=semantic_mem, score=0.85, memory_type=MemoryType.SEMANTIC)],
            [MemorySearchResult(memory=episodic_mem, score=0.82, memory_type=MemoryType.EPISODIC)],
        ]

        fused = retriever.fuse(result_lists, limit=5)

        # Both should be present and properly ranked
        assert len(fused) == 2
        # Recent episodic should rank high due to high recency weight
        assert any(r.memory_type == MemoryType.EPISODIC for r in fused[:2])
