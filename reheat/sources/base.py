from abc import ABC, abstractmethod
from typing import Any, Dict, List
from reheat.state.execution import QueryRecord, SourceConfig


class SourceProvider(ABC):
    """
    Base class for data source providers.

    Each provider knows how to:
    - validate its configuration
    - execute a fetch and return QueryRecords
    """

    source_type: str = ""

    def __init__(self, config: SourceConfig) -> None:
        self.config = config
        self.validate()

    def validate(self) -> None:
        """
        Raise ValueError if the SourceConfig is missing required credentials
        or settings. Called at construction time.
        """
        pass

    @abstractmethod
    def fetch(self) -> List[QueryRecord]:
        """
        Pull data from the source and return QueryRecords.
        Raises SourceError on failure.
        """
        ...

    def _credential(self, key: str) -> str:
        """Return a credential value, raising ValueError if absent."""
        value = self.config.credentials.get(key, "")
        if not value:
            raise ValueError(
                f"source {self.config.source_id!r} missing credential {key!r}"
            )
        return value

    def _setting(self, key: str, default: Any = None) -> Any:
        """Return a setting value with optional default."""
        return self.config.settings.get(key, default)


class SourceError(Exception):
    """Raised when a source provider fails to fetch data."""
