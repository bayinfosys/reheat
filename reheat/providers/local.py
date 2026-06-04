import logging
from typing import List

from reheat.providers.base import EmbeddingError, EmbeddingProvider

logger = logging.getLogger(__name__)


class LocalEmbeddingProvider(EmbeddingProvider):
    """
    Embedding provider using fastembed with all-MiniLM-L6-v2.
    No API key required. No torch dependency.
    Model is downloaded on first use and cached by fastembed.
    """

    MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
    DIMENSION = 384

    def __init__(self, model_name: str = MODEL_NAME) -> None:
        try:
            from fastembed import TextEmbedding
        except ImportError:
            raise ImportError(
                "fastembed is required for the local embedding provider. "
                "Install with: pip install reheat[local]"
            )
        logger.info("loading local embedding model %s", model_name)
        self._model_name = model_name
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
        return self.DIMENSION
