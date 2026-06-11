def register_all_commands() -> None:
    """
    Import all command modules to trigger @command decorator registration.
    These imports are not unused -- each module registers its commands
    as a side effect of being imported.
    """
    import reheat.commands.analyse  # noqa: F401
    import reheat.commands.config  # noqa: F401
    import reheat.commands.enrich  # noqa: F401
    import reheat.commands.enrichments  # noqa: F401
    import reheat.commands.models  # noqa: F401
    import reheat.commands.pipeline  # noqa: F401
    import reheat.commands.project  # noqa: F401
    import reheat.commands.report  # noqa: F401
    import reheat.commands.runs  # noqa: F401
    import reheat.commands.serve  # noqa: F401
    import reheat.commands.sources  # noqa: F401
    import reheat.commands.status  # noqa: F401
