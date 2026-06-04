import logging

from dynawrap.backends.base import DBBackend

from reheat.registry import command

logger = logging.getLogger(__name__)


@command(help="Start the reheat API server", interactive_only=True)
def cmd_serve(
    backend: DBBackend,
    *,
    port: int = 8000,
    host: str = "0.0.0.0",
    reload: bool = False,
) -> dict:
    try:
        import uvicorn
    except ImportError:
        raise ImportError("uvicorn is required. pip install uvicorn")

    import threading
    import webbrowser
    from reheat.adapters.fastapi_adapter import build_app

    app = build_app()

    threading.Timer(
        1.0, lambda: webbrowser.open(f"http://localhost:{port}/")
    ).start()

    logger.info("starting reheat API at http://%s:%d", host, port)
    uvicorn.run(app, host=host, port=port, reload=reload)
    return {"host": host, "port": port}
