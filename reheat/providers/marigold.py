import logging
from typing import List

from reheat.providers.base import EmbeddingError, EmbeddingProvider

logger = logging.getLogger(__name__)


class MarigoldEmbeddingProvider(EmbeddingProvider):

    DIMENSION = 768

    def __init__(
        self,
        api_key: str,
        endpoint: str,
        model_name: str = "default",
    ) -> None:
        raise NotImplementedError(
            "MarigoldEmbeddingProvider is not yet implemented. "
            "Awaiting Marigold client library."
        )

    def embed(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError

    def dimension(self) -> int:
        return self.DIMENSION
