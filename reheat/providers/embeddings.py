import logging
from reheat.providers.base import EmbeddingProvider
from reheat.state.user import UserState

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """Raised when provider configuration is invalid or incomplete."""


def get_embedding_provider(user: UserState) -> EmbeddingProvider:
    """
    Construct the configured EmbeddingProvider from UserState.
    Raises ConfigError if required keys are absent.
    """
    provider = user.embedding_provider
    logger.debug("constructing embedding provider: %s", provider)

    if provider == "local":
        from reheat.providers.local import LocalEmbeddingProvider

        return LocalEmbeddingProvider(
            model_name=user.embedding_model or LocalEmbeddingProvider.MODEL_NAME
        )

    if provider == "openai":
        if not user.openai_api_key:
            raise ConfigError(
                "embedding_provider is 'openai' but openai_api_key is not set. "
                "Run: reheat config set --key openai_api_key --value <key>"
            )
        from reheat.providers.openai import OpenAIEmbeddingProvider

        return OpenAIEmbeddingProvider(
            api_key=user.openai_api_key,
            model_name=user.embedding_model,
        )

    if provider == "marigold":
        if not user.marigold_api_key:
            raise ConfigError(
                "embedding_provider is 'marigold' but marigold_api_key is not set. "
                "Run: reheat config set --key marigold_api_key --value <key>"
            )
        if not user.marigold_endpoint:
            raise ConfigError(
                "embedding_provider is 'marigold' but marigold_endpoint is not set. "
                "Run: reheat config set --key marigold_endpoint --value <url>"
            )
        from reheat.providers.marigold import MarigoldEmbeddingProvider

        return MarigoldEmbeddingProvider(
            api_key=user.marigold_api_key,
            endpoint=user.marigold_endpoint,
            model_name=user.embedding_model,
        )

    raise ConfigError(f"unknown embedding provider: {provider!r}")
