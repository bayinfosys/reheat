import logging
import sys

from dynawrap.backends.base import DBBackend

from reheat.registry import Payload, command
from reheat.state import SOURCES_TABLE, SourceConfig, get_user_id

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ANSI colour helpers -- degrade cleanly when stdout is not a TTY
# ---------------------------------------------------------------------------

_RESET  = "\033[0m"
_CYAN   = "\033[36m"
_AMBER  = "\033[33m"
_GREEN  = "\033[32m"
_RED    = "\033[31m"
_BOLD   = "\033[1m"


def _tty() -> bool:
    return sys.stdout.isatty()


def _step(msg: str) -> None:
    if _tty():
        print(f"{_BOLD}{_CYAN}--> {msg}{_RESET}")
    else:
        print(f"--> {msg}")


def _notice(msg: str) -> None:
    if _tty():
        print(f"{_AMBER}NOTICE  {msg}{_RESET}")
    else:
        print(f"NOTICE  {msg}")


def _ok(msg: str) -> None:
    if _tty():
        print(f"{_GREEN}OK      {msg}{_RESET}")
    else:
        print(f"OK      {msg}")


def _abort(msg: str) -> None:
    if _tty():
        print(f"{_BOLD}{_RED}ABORT   {msg}{_RESET}")
    else:
        print(f"ABORT   {msg}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _has_serp_source(backend: DBBackend) -> bool:
    sources = backend.query(
        SOURCES_TABLE, SourceConfig, user_id=get_user_id(backend)
    )
    return any(s.source_type == "serp" for s in sources)


def _run_step(label: str, fn, *args, **kwargs):
    """
    Execute fn(*args, **kwargs), printing a step header before and a
    completion line after. Raises on failure -- caller decides whether
    to abort the pipeline.
    """
    _step(label)
    result = fn(*args, **kwargs)
    _ok(label)
    return result


# ---------------------------------------------------------------------------
# Pipeline commands
# ---------------------------------------------------------------------------

@command(help="Fetch queries from the configured source and create a new run")
def cmd_fetch(
    backend: DBBackend,
    *,
    source_id: Payload[str] = "",
    headless: Payload[bool] = False,
) -> dict:
    """
    Alias for `reheat runs create`.

    Pulls queries from Google Search Console and persists a RunRecord.
    Run `reheat enrich` after this step to process the downloaded queries.
    """
    from reheat.commands.runs import cmd_runs_create
    return cmd_runs_create(backend, source_id=source_id, headless=headless)


@command(help="Run all enrichment steps for the most recent run")
def cmd_enrich(
    backend: DBBackend,
    *,
    run_id: Payload[str] = "",
    headless: Payload[bool] = False,
) -> dict:
    """
    Runs the full enrichment pipeline in sequence:

        enrich adjacent  (skipped with a notice if no SerpAPI source is configured)
        enrich tags
        enrich embed
        enrich cluster

    Pass --run-id to target a specific run; defaults to the most recent.
    """
    from reheat.commands.enrich import (cmd_enrich_adjacent,
                                        cmd_enrich_cluster, cmd_enrich_embed,
                                        cmd_enrich_tags)

    kwargs = {"run_id": run_id, "headless": headless}

    if _has_serp_source(backend):
        try:
            _run_step("enrich adjacent", cmd_enrich_adjacent, backend, **kwargs)
        except Exception as e:
            _abort(f"enrich adjacent failed: {e}")
            raise
    else:
        _notice(
            "no SerpAPI source configured -- adjacent enrichment skipped.\n"
            "        To enable: reheat sources create --source-type serp\n"
            "        Then re-run: reheat enrich"
        )

    try:
        _run_step("enrich tags", cmd_enrich_tags, backend, **kwargs)
    except Exception as e:
        _abort(f"enrich tags failed: {e}")
        raise

    try:
        _run_step("enrich embed", cmd_enrich_embed, backend, **kwargs)
    except Exception as e:
        _abort(f"enrich embed failed: {e}")
        raise

    try:
        _run_step("enrich cluster", cmd_enrich_cluster, backend, **kwargs)
    except Exception as e:
        _abort(f"enrich cluster failed: {e}")
        raise

    _ok("enrichment complete")
    return {"status": "ok"}


@command(help="Run all analysis and report steps for the most recent run")
def cmd_analyse(
    backend: DBBackend,
    *,
    run_id: Payload[str] = "",
) -> dict:
    """
    Runs the full analysis pipeline in sequence:

        analyse summarise
        analyse opportunities
        analyse schedule
        analyse overview
        project create
        report scatter create
        report summary create
        report coverage create

    Pass --run-id to target a specific run; defaults to the most recent.
    """
    from reheat.commands.analyse import (cmd_analyse_opportunities,
                                         cmd_analyse_overview,
                                         cmd_analyse_schedule,
                                         cmd_analyse_summarise)
    from reheat.commands.project import cmd_project_create
    from reheat.commands.report import (cmd_report_coverage_create,
                                        cmd_report_scatter_create,
                                        cmd_report_summary_create)

    kwargs = {"run_id": run_id}

    steps = [
        ("analyse summarise",       cmd_analyse_summarise,      kwargs),
        ("analyse opportunities",   cmd_analyse_opportunities,  kwargs),
        ("analyse schedule",        cmd_analyse_schedule,       kwargs),
        ("analyse overview",        cmd_analyse_overview,       kwargs),
        ("project create",          cmd_project_create,         kwargs),
        ("report scatter create",   cmd_report_scatter_create,  kwargs),
        ("report summary create",   cmd_report_summary_create,  kwargs),
        ("report coverage create",  cmd_report_coverage_create, kwargs),
    ]

    for label, fn, kw in steps:
        try:
            _run_step(label, fn, backend, **kw)
        except Exception as e:
            _abort(f"{label} failed: {e}")
            raise

    _ok("analysis complete")
    return {"status": "ok"}
