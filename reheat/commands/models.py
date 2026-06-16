import logging

from dynawrap.backends.base import DBBackend

from reheat.registry import Payload, Resource, command
from reheat.state import (MODELS_TABLE, ClusterBackbone, ClusterModel,
                          ModelRuns, get_user_id)

logger = logging.getLogger(__name__)


def _get_model(backend: DBBackend, model_id: str) -> ClusterModel:
    model = backend.get(MODELS_TABLE, ClusterModel, user_id=get_user_id(backend), model_id=model_id)
    if model is None:
        raise ValueError(f"cluster model {model_id!r} not found")
    return model


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@command(help="List all cluster models")
def cmd_models_list(
    backend: DBBackend,
    *,
    source_id: Payload[str] = "",
) -> list:
    """
    List all ClusterModel records for the current user, sorted by
    creation time descending. Optionally filter by source_id.
    """
    models = sorted(
        backend.query(MODELS_TABLE, ClusterModel, user_id=get_user_id(backend)),
        key=lambda m: m.model_id,
        reverse=True,
    )
    if source_id:
        models = [m for m in models if m.source_id == source_id]

    return [
        {
            "model_id":        m.model_id,
            "source_id":       m.source_id,
            "description":     m.description or "",
            "algorithm":       m.algorithm,
            "embedding_model": m.embedding_model,
            "k":               m.k,
            "label_count":     len(m.labels),
            "created_at":      m.created_at.isoformat() if m.created_at else None,
        }
        for m in models
    ]


@command(help="Show cluster model detail")
def cmd_models_show(
    backend: DBBackend,
    *,
    model_id: Resource[str],
) -> dict:
    """
    Return full detail for a single ClusterModel including labels,
    the list of runs it has been applied to, and any stored backbones.
    Centroids are omitted from the return value (too large for display).
    """
    model = _get_model(backend, model_id)

    runs = list(backend.query(
        MODELS_TABLE, ModelRuns, user_id=get_user_id(backend), model_id=model_id,
    ))
    backbones = list(backend.query(
        MODELS_TABLE, ClusterBackbone, user_id=get_user_id(backend), model_id=model_id,
    ))

    return {
        "model_id":        model.model_id,
        "source_id":       model.source_id,
        "description":     model.description or "",
        "algorithm":       model.algorithm,
        "embedding_model": model.embedding_model,
        "k":               model.k,
        "labels":          model.labels,
        "created_at":      model.created_at.isoformat() if model.created_at else None,
        "runs_applied":    [
            {
                "run_id":     r.run_id,
                "applied_at": r.applied_at.isoformat() if r.applied_at else None,
            }
            for r in sorted(runs, key=lambda r: r.run_id)
        ],
        "backbones": [
            {
                "backbone_id": b.backbone_id,
                "created_at":  b.created_at.isoformat() if b.created_at else None,
            }
            for b in sorted(backbones, key=lambda b: b.backbone_id)
        ],
    }


@command(help="Update cluster model description")
def cmd_models_describe(
    backend: DBBackend,
    *,
    model_id: Resource[str],
    description: Payload[str],
) -> dict:
    """
    Update the description field on a ClusterModel via read-modify-write.
    """
    model = _get_model(backend, model_id)
    updated = model.model_copy(update={"description": description})
    backend.save(MODELS_TABLE, updated)
    return {"model_id": model_id, "description": description}


@command(help="Show cluster assignments for a run")
def cmd_models_assignments_show(
    backend: DBBackend,
    *,
    model_id: Resource[str] = "",
    run_id: Payload[str] = "",
) -> list:
    """
    Return per-query cluster assignments for a (model, run) pair, joined
    with the cluster label from the model's labels dict.

    Useful for exporting cluster membership to external tools:

        reheat models assignments show --model-id <id> --run-id <id> \
          | jq -r '.[] | [.query, .cluster_id, .label] | @csv'
    """
    from reheat.commands.runs import _resolve_run
    from reheat.state import ClusterAssignments

    if not model_id:
        raise ValueError("model_id is required")

    run = _resolve_run(backend, run_id or None)
    model = _get_model(backend, model_id)

    record = backend.get(
        MODELS_TABLE, ClusterAssignments,
        user_id=get_user_id(backend),
        model_id=model_id,
        run_id=run.run_id,
    )
    if record is None:
        raise ValueError(
            f"no assignments for model {model_id!r} on run {run.run_id!r}"
        )

    return [
        {
            "query":      a["query"],
            "cluster_id": a["cluster_id"],
            "label":      model.labels.get(str(a["cluster_id"]), ""),
            "is_adjacent": a.get("is_adjacent", False),
        }
        for a in record.assignments
    ]
