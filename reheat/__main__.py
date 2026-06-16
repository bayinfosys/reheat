import logging
import sys

from reheat.adapters.argparse_adapter import build_parser, dispatch
from reheat.commands import register_all_commands
from reheat.state import init_backend


def main():
    register_all_commands()

    parser = build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
    )

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    try:
        backend = init_backend(getattr(args, "config", None))
    except Exception as e:
        print(f"error: failed to initialise backend: {e}")
        sys.exit(1)

    if not backend:
        print("error: failed to obtain backend")
        sys.exit(2)

    try:
        dispatch(args, backend)
    except KeyboardInterrupt:
        print("\ninterrupted")
        sys.exit(130)
    except Exception:
        logging.getLogger(__name__).exception("command failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
