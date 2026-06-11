import logging
import os
from abc import ABC, abstractmethod
from typing import List

from reheat.errors import ConfigError, EmbeddingError
from reheat.state.user import UserState

logger = logging.getLogger(__name__)


class EmbeddingProvider(ABC):
    provider_name: str = ""
    model_name: str = ""

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


class LocalEmbeddingProvider(EmbeddingProvider):
    """
    Embedding provider using fastembed with all-MiniLM-L6-v2.
    No API key required. No torch dependency.
    Model is downloaded on first use and cached by fastembed.
    """

    provider_name: str = "local"

    DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
    DEFAULT_DIMENSION = 384

    def __init__(self, model_name: str = DEFAULT_MODEL_NAME) -> None:
        try:
            from fastembed import TextEmbedding
        except ImportError:
            raise ImportError(
                "fastembed is required for the local embedding provider. "
                "Install with: pip install reheat[local]"
            )
        logger.info("loading local embedding model %s", model_name)
        self.model_name = model_name
        self._model = TextEmbedding(model_name=model_name)
        logger.info("local embedding model loaded")

    def embed(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        try:
            logger.debug("embedding %d texts with local provider", len(texts))
            vectors = list(self._model.embed(texts))
            return [v.tolist() for v in vectors]
        except Exception as e:
            logger.exception("local embedding failed")
            raise EmbeddingError(f"local embedding failed: {e}") from e

    def dimension(self) -> int:
        return self.DEFAULT_DIMENSION


class OpenAIEmbeddingProvider(EmbeddingProvider):
    provider_name: str = "openai"

    DEFAULT_MODEL_NAME = "text-embedding-3-small"
    DEFAULT_DIMENSION = 1536

    def __init__(self, api_key: str, model_name: str = DEFAULT_MODEL_NAME) -> None:
        raise NotImplementedError(
            "OpenAIEmbeddingProvider is not yet implemented. "
            "Install with: pip install reheat[openai]"
        )

    def embed(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError

    def dimension(self) -> int:
        return self.DEFAULT_DIMENSION


class MarigoldEmbeddingProvider(EmbeddingProvider):
    provider_name: str = "marigold"
    DEFAULT_MODEL_NAME = "default"
    DEFAULT_DIMENSION = 768

    def __init__(
        self,
        api_key: str,
        endpoint: str,
        model_name: str = DEFAULT_MODEL_NAME,
    ) -> None:
        raise NotImplementedError(
            "MarigoldEmbeddingProvider is not yet implemented. "
            "Awaiting Marigold client library."
        )

    def embed(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError

    def dimension(self) -> int:
        return self.DEFAULT_DIMENSION


def get_embedding_provider(user: UserState) -> EmbeddingProvider:
    provider = user.embedding_provider
    logger.debug("constructing embedding provider: %s", provider)

    if provider == "local":
        return LocalEmbeddingProvider(
            model_name=user.embedding_model or LocalEmbeddingProvider.DEFAULT_MODEL_NAME
        )

    if provider == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            raise ConfigError(
                "embedding_provider is 'openai' but OPENAI_API_KEY is not set."
            )

        return OpenAIEmbeddingProvider(
            model_name=user.embedding_model
            or OpenAIEmbeddingProvider.DEFAULT_MODEL_NAME,
        )

    if provider == "marigold":
        if not os.environ.get("MARIGOLD_API_KEY"):
            raise ConfigError(
                "embedding_provider is 'marigold' but MARIGOLD_API_KEY is not set."
            )
        if not os.environ.get("MARIGOLD_ENDPOINT"):
            raise ConfigError(
                "embedding_provider is 'marigold' but MARIGOLD_ENDPOINT is not set."
            )

        return MarigoldEmbeddingProvider(
            model_name=user.embedding_model
            or MarigoldEmbeddingProvider.DEFAULT_MODEL_NAME,
        )

    raise ConfigError(f"unknown embedding provider: {provider!r}")
