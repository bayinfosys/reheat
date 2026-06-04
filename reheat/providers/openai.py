import logging
from typing import List

from reheat.providers.base import EmbeddingError, EmbeddingProvider

logger = logging.getLogger(__name__)


class OpenAIEmbeddingProvider(EmbeddingProvider):

    MODEL_NAME = "text-embedding-3-small"
    DIMENSION = 1536

    def __init__(self, api_key: str, model_name: str = MODEL_NAME) -> None:
        raise NotImplementedError(
            "OpenAIEmbeddingProvider is not yet implemented. "
            "Install with: pip install reheat[openai]"
        )

    def embed(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError

    def dimension(self) -> int:
        return self.DIMENSION
