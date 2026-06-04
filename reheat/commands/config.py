import json
import logging
from pathlib import Path

from dynawrap.backends.base import DBBackend

from reheat.registry import command, Payload
from reheat.state import USER_TABLE, get_user
from reheat.state.user import UserState

logger = logging.getLogger(__name__)


@command(help="Create a blank config file", interactive_only=True)
def cmd_config_init(backend: DBBackend) -> dict:
    path = Path.home() / ".reheat" / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        logger.info(f"config already exists at {path}")
        return {"path": str(path), "created": False}

    template = {
        "_instructions": "Fill in the values below. Remove this key when done.",
        "_docs": "https://github.com/bayinfosys/reheat",
        **UserState().model_dump(),
    }
    path.write_text(json.dumps(template, indent=2))
    logger.info(f"config created at {path}, edit it and fill in your API keys, then run: reheat sources create")
    return {"path": str(path), "created": True}


@command(help="Show current configuration")
def cmd_config_show(backend: DBBackend) -> dict:
    user = get_user(backend)

    def redact(value: str) -> str:
        if not value:
            return ""
        if len(value) <= 8:
            return "[set]"
        return value[:4] + "..." + value[-4:]

    return {
        "user_id":            user.user_id,
        "default_source_id":  user.default_source_id,
        "embedding_provider": user.embedding_provider,
        "embedding_model":    user.embedding_model,
        "summary_model":      user.summary_model,
        "projection_method":  user.projection_method,
        "cluster_k":          user.cluster_k,
        "summarise_top_n":    user.summarise_top_n,
        "fetch_days":         user.fetch_days,
        "fetch_limit":        user.fetch_limit,
        "serp_enrich_limit":  user.serp_enrich_limit,
        "serp_delay":         user.serp_delay,
    }


@command(help="Set a configuration value")
def cmd_config_set(
    backend: DBBackend,
    *,
    key: Payload[str] = "",
    value: Payload[str] = "",
) -> dict:
    if not key or not value:
        raise ValueError("both key and value are required")

    user = get_user(backend)

    if not hasattr(user, key):
        raise ValueError(f"unknown config key {key!r}")

    field = user.model_fields.get(key)
    if field is not None:
        annotation = field.annotation
        try:
            if annotation is int or str(annotation) == "int":
                value = int(value)
            elif annotation is float or str(annotation) == "float":
                value = float(value)
            elif str(annotation).startswith("List") or str(annotation).startswith("list"):
                value = [v.strip() for v in value.split(",") if v.strip()]
        except ValueError as e:
            raise ValueError(f"invalid value for {key!r}: {e}")

    setattr(user, key, value)
    backend.save(USER_TABLE, user)
    return {"updated": key, "value": value}
