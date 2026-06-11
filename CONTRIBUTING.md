# Contributing to reheat

## Development setup

Clone the repository and install in editable mode with development dependencies:

    git clone https://github.com/bayinfosys/reheat
    cd reheat
    pip install -e ".[dev]"

## Running the tests

The test suite requires a PostgreSQL database. Start one with Docker:

    docker run --name reheat-test-db \
      -e POSTGRES_USER=reheat \
      -e POSTGRES_PASSWORD=reheat \
      -e POSTGRES_DB=reheat_test \
      -p 5433:5432 \
      -d postgres:16

Set the connection string and run pytest:

    export REHEAT_TEST_DB=postgresql://reheat:reheat@localhost:5433/reheat_test
    pytest

The suite truncates all tables before each test. No teardown is required
between runs. External API calls (Google Search Console, SerpAPI, embedding
and instruct providers) are replaced by in-process mocks; no API keys are
needed to run the tests.

## Project structure

    reheat/
      adapters/    CLI (argparse) and HTTP (FastAPI) adapters
      commands/    Command functions registered via @command
      pipeline/    Pure functions: clustering, embedding, gap analysis, reports
      providers/   Embedding and instruct provider abstractions
      sources/     Data source providers (GSC, SerpAPI)
      state/       Persistence models and backend initialisation
      static/      Web UI (HTML, JS, CSS)
    tests/
      fixtures/    Static JSON fixtures for GSC and SerpAPI responses
      test_*.py    One file per command module

## Architecture

reheat follows a three-layer design:

1. Adapters (argparse, FastAPI) parse input and call commands by path.
2. Commands orchestrate state reads/writes and call pipeline functions.
3. Pipeline functions are pure: they take data in, return data out, and
   have no database or provider dependencies.

New features follow this boundary. A pipeline function must not import
from commands or state. A command must not import from adapters.

## Adding a command

Register a function in the appropriate commands module:

    from reheat.registry import command, Payload, Resource

    @command(help="One-line description shown in reheat --help")
    def cmd_mygroup_myaction(
        backend: DBBackend,
        *,
        run_id: Resource[str] = "",
        some_option: Payload[str] = "",
    ) -> dict:
        ...

The function name encodes the CLI path: `cmd_mygroup_myaction` becomes
`reheat mygroup myaction`. `Resource[T]` parameters map to URL path
segments and CLI positional arguments. `Payload[T]` parameters map to
POST body fields and CLI `--flags`.

Import the new module in `reheat/commands/__init__.py` inside
`register_all_commands()`.

## Code style

    black reheat tests
    isort reheat tests
    flake8 reheat tests

No hard rules on line length beyond what black enforces.

## Submitting changes

Open a pull request against `main`. Include at least one test covering
the new behaviour. The test suite must pass in full before merge.
