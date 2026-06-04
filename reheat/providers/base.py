from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a list of text strings.
        Returns a list of float vectors, one per input string.
        Raises EmbeddingError on failure.
        """
        ...

    @abstractmethod
    def dimension(self) -> int:
        """Return the dimensionality of the embedding vectors."""
        ...


class EmbeddingError(Exception):
    """Raised when an embedding provider fails."""
