from datetime import datetime
from typing import Any, ClassVar, Dict, List, Optional

from dynawrap import DBItem
from pydantic import BaseModel, Field


class ClusterModel(DBItem, BaseModel):
    """
    A fitted cluster model. Created once by cmd_enrich_cluster when no
    --model argument is supplied. Centroids are stored here and used to
    assign new observations without re-fitting. Labels are populated
    later by cmd_analyse_summarise via read-modify-write.

    Access patterns:
        List all models for user:
            query(TABLE, ClusterModel, user_id=user_id)
            -> PK=USER#{user_id}, SK prefix=MODEL#

        Get specific model:
            get(TABLE, ClusterModel, user_id=user_id, model_id=model_id)
    """
    pk_pattern: ClassVar[str] = "USER#{user_id}"
    sk_pattern: ClassVar[str] = "MODEL#{model_id}"

    user_id: str = "default"
    model_id: str
    source_id: str = ""
    description: Optional[str] = None
    algorithm: str = "agglomerative+kmeans"
    embedding_model: str = ""
    k: int = 0
    centroids: List[List[float]] = Field(default_factory=list)
    labels: Dict[str, str] = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class ClusterBackbone(DBItem, BaseModel):
    """
    Minimum spanning tree over the cluster centroids for a given model.
    Computed separately by cmd_enrich_backbone. Multiple backbones per
    model are supported; backbone_id is a timestamp so records sort
    chronologically.

    Access patterns:
        All backbones for model (chronological):
            query(TABLE, ClusterBackbone, user_id=user_id, model_id=model_id)
            -> PK=USER#{user_id}#MODEL#{model_id}, SK prefix=BACKBONE#

        Specific backbone:
            get(TABLE, ClusterBackbone, user_id=user_id,
                model_id=model_id, backbone_id=backbone_id)
    """
    pk_pattern: ClassVar[str] = "USER#{user_id}#MODEL#{model_id}"
    sk_pattern: ClassVar[str] = "BACKBONE#{backbone_id}"

    user_id: str = "default"
    model_id: str
    backbone_id: str
    edges: List[Dict[str, Any]] = Field(default_factory=list)
    degree: Dict[str, int] = Field(default_factory=dict)
    betweenness: Dict[str, float] = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class ClusterAssignments(DBItem, BaseModel):
    """
    Per-query cluster assignments produced by applying model M to run R.
    One record per (model, run) pair.

    Access patterns:
        Assignments for a specific (model, run) pair:
            get(TABLE, ClusterAssignments, user_id=user_id,
                model_id=model_id, run_id=run_id)
            -> PK=USER#{user_id}#MODEL#{model_id},
               SK=RUN#{run_id}#ASSIGNMENTS
    """
    pk_pattern: ClassVar[str] = "USER#{user_id}#MODEL#{model_id}"
    sk_pattern: ClassVar[str] = "RUN#{run_id}#ASSIGNMENTS"

    user_id: str = "default"
    model_id: str
    run_id: str
    assignments: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: Optional[datetime] = None


class ModelClusterMetric(DBItem, BaseModel):
    """
    Metrics for a single cluster computed from a specific run.
    One record per (model, cluster, computation). metric_id is a timestamp,
    allowing recomputation without overwriting prior history.

    cluster_id is zero-padded to four digits so lexicographic and numeric
    sort orders agree: "0001", "0002", ..., "0016".

    Metrics:
        intent_demand     total observable demand for this cluster
        coverage_health   seed impressions / intent_demand
        click_quality     clicks / seed_impressions
        demand_capture    clicks / intent_demand

    Access patterns:
        Trend for cluster C across all computations:
            query(TABLE, ModelClusterMetric, user_id=user_id,
                  model_id=model_id, cluster_id=cluster_id)
            -> PK=USER#{user_id}#MODEL#{model_id},
               SK prefix=CLUSTER#{cluster_id}#METRIC#
    """
    pk_pattern: ClassVar[str] = "USER#{user_id}#MODEL#{model_id}"
    sk_pattern: ClassVar[str] = "CLUSTER#{cluster_id}#METRIC#{metric_id}"

    user_id: str = "default"
    model_id: str
    cluster_id: str
    metric_id: str
    run_id: str
    intent_demand: float = 0.0
    coverage_health: float = 0.0
    click_quality: float = 0.0
    demand_capture: float = 0.0
    seed_query_count: int = 0
    adjacent_query_count: int = 0
    computed_at: Optional[datetime] = None


class ModelRunMetric(DBItem, BaseModel):
    """
    Dual-write counterpart to ModelClusterMetric with RUN-first SK.
    Written atomically alongside ModelClusterMetric.

    Primary record for report generation: all cluster metrics for a
    given run under a given model.

    Access patterns:
        All cluster metrics for run R under model M:
            query(TABLE, ModelRunMetric, user_id=user_id,
                  model_id=model_id, run_id=run_id)
            -> PK=USER#{user_id}#MODEL#{model_id},
               SK prefix=RUN#{run_id}#CLUSTER#
    """
    pk_pattern: ClassVar[str] = "USER#{user_id}#MODEL#{model_id}"
    sk_pattern: ClassVar[str] = "RUN#{run_id}#CLUSTER#{cluster_id}"

    user_id: str = "default"
    model_id: str
    run_id: str
    cluster_id: str
    metric_id: str
    intent_demand: float = 0.0
    coverage_health: float = 0.0
    click_quality: float = 0.0
    demand_capture: float = 0.0
    seed_query_count: int = 0
    adjacent_query_count: int = 0
    computed_at: Optional[datetime] = None


class RunModels(DBItem, BaseModel):
    """
    Records that model M was applied to run R.
    Primary traversal: given a run, list all models applied to it.

    Access patterns:
        All models applied to run R:
            query(TABLE, RunModels, user_id=user_id, run_id=run_id)
            -> PK=USER#{user_id}#RUN#{run_id}, SK prefix=MODEL#
    """
    pk_pattern: ClassVar[str] = "USER#{user_id}#RUN#{run_id}"
    sk_pattern: ClassVar[str] = "MODEL#{model_id}"

    user_id: str = "default"
    run_id: str
    model_id: str
    applied_at: Optional[datetime] = None


class ModelRuns(DBItem, BaseModel):
    """
    Inverse index of RunModels.
    Primary traversal: given a model, list all runs it has been applied to.

    The SK suffix #APPLIED distinguishes this from ClusterAssignments
    (RUN#{run_id}#ASSIGNMENTS) and ModelRunMetric (RUN#{run_id}#CLUSTER#...)
    within the same model partition.

    Access patterns:
        All runs a model has been applied to:
            query(TABLE, ModelRuns, user_id=user_id, model_id=model_id)
            -> PK=USER#{user_id}#MODEL#{model_id}, SK prefix=RUN#
    """
    pk_pattern: ClassVar[str] = "USER#{user_id}#MODEL#{model_id}"
    sk_pattern: ClassVar[str] = "RUN#{run_id}#APPLIED"

    user_id: str = "default"
    model_id: str
    run_id: str
    applied_at: Optional[datetime] = None
