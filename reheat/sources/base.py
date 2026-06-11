import os
from abc import ABC, abstractmethod
from typing import Any, List

from reheat.state import QueryRecord, SourceConfig


class SourceProvider(ABC):
    """
    Base class for data source providers.

    Providers read all secrets and file paths from environment variables
    at call time. Nothing is stored in SourceConfig.credentials.
    The caller is responsible for setting and securing all env vars.
    """

    source_type: str = ""

    def __init__(self, config: SourceConfig) -> None:
        self.config = config
        self.validate()

    def validate(self) -> None:
        """
        Called at construction time. Raise SourceError if required env vars
        are absent so misconfiguration is caught before any network call.
        """
        pass

    @abstractmethod
    def fetch(self) -> List[QueryRecord]:
        """
        Pull data from the source and return QueryRecords.
        Raises SourceError on failure.
        """
        ...

    def _env(self, var: str) -> str:
        """Return an env var value. Raise SourceError if unset or empty."""
        value = os.environ.get(var, "")
        if not value:
            raise SourceError(
                f"{var} is not set. "
                f"Add it to your environment before running this command."
            )
        return value

    def _setting(self, key: str, default: Any = None) -> Any:
        """Return a runtime setting from SourceConfig with an optional default."""
        return self.config.settings.get(key, default)


class SourceError(Exception):
    """Raised when a source provider fails to fetch data."""
