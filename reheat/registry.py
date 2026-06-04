from typing import Callable, Dict, Generic, Iterator, Optional, Tuple, TypeVar

T = TypeVar("T")


class Resource(Generic[T]):
    """Parameter is a resource identifier. Maps to a URL path segment."""
    pass


class Payload(Generic[T]):
    """Parameter is request payload. Maps to a POST body field."""
    pass


class Registry:
    """
    Central command registry.

    Commands are registered by decorating a function with @registry.command.
    The function name must start with cmd_ and uses underscores to encode
    the command path: cmd_runs_list -> "runs.list", cmd_enrich_cluster -> "enrich.cluster".

    The registry is the single source of truth for both the CLI adapter and
    the FastAPI adapter. Neither adapter imports internal state directly.
    """

    def __init__(self) -> None:
        self._commands: Dict[str, Callable] = {}

    def command(self, help: str = "", interactive_only: bool = False) -> Callable:
        """Decorator. Registers the decorated function as a command."""
        def decorator(fn: Callable) -> Callable:
            parts = fn.__name__.split("_")
            if parts[0] != "cmd":
                raise ValueError(
                    f"command functions must start with cmd_, got {fn.__name__!r}"
                )
            path = ".".join(parts[1:])
            self._commands[path] = fn
            fn._cli_path = path
            fn._cli_help = help
            fn._interactive_only = interactive_only
            return fn
        return decorator

    def get(self, path: str) -> Optional[Callable]:
        """Return the command at path, or None."""
        return self._commands.get(path)

    def items(self) -> Iterator[Tuple[str, Callable]]:
        """Yield (path, fn) pairs for all registered commands."""
        return iter(self._commands.items())

    def __len__(self) -> int:
        return len(self._commands)

    def __contains__(self, path: str) -> bool:
        return path in self._commands


registry = Registry()
command = registry.command
