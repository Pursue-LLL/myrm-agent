"""Embedding Service Base Interface.

Abstract interface for vector embedding services, defining a unified embedding API.
Also satisfies MemoryManager's EmbeddingProtocol (embed / embed_batch / dimension).

[INPUT]
- (none - standard library ABC)

[OUTPUT]
- EmbeddingService: Abstract base class for all embedding backends

[POS]
Embedding contract layer. Declares the abstract interface that every embedding backend
(cloud, local, cached) must implement.

"""

from abc import ABC, abstractmethod


class EmbeddingService(ABC):
    """Abstract interface for vector embedding services.

    Every embedding service implementation must inherit this class and implement the abstract methods.
    The interface matches ``EmbeddingProtocol`` exactly, so an implementation can be passed directly to ``MemoryManager``.
    """

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the embedding vector dimension."""
        ...

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Embed a single text.

        Args:
            text: Input text

        Returns:
            Embedding vector
        """
        ...

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts.

        Args:
            texts: Input texts

        Returns:
            List of embedding vectors
        """
        ...
