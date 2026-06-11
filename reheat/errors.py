class ReheatError(Exception):
    """Base class for all reheat errors."""


class ConfigError(ReheatError):
    """No provider can be configured from the available environment."""


class InstructError(ReheatError):
    """An instruct provider call failed."""


class EmbeddingError(ReheatError):
    """An embedding provider call failed."""


class SourceError(ReheatError):
    """A source provider failed to fetch data."""


class ScheduleError(ReheatError):
    """Schedule or overview generation failed."""


class SummarisationError(ReheatError):
    """Raised when a cluster cannot be summarised."""
