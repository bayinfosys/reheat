from reheat.state.execution import SourceConfig
from reheat.sources.base import SourceProvider, SourceError


def get_source_provider(config: SourceConfig) -> SourceProvider:
    """
    Factory: construct the correct SourceProvider for a SourceConfig.
    Importing here keeps the registry central and avoids circular imports.
    """
    from reheat.sources.google_search_console import GoogleSearchConsoleProvider
    from reheat.sources.serp import SerpAPIProvider

    providers = {
        "google_search_console": GoogleSearchConsoleProvider,
        "serp": SerpAPIProvider,
    }

    cls = providers.get(config.source_type)
    if cls is None:
        raise SourceError(
            f"unknown source type {config.source_type!r}. "
            f"Available: {', '.join(providers)}"
        )
    return cls(config)
