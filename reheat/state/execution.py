from datetime import datetime
from typing import Any, ClassVar, Dict, List, Optional
from pydantic import BaseModel, Field
from dynawrap import DBItem


# ---------------------------------------------------------------------------
# Bronze layer -- raw data
# ---------------------------------------------------------------------------

class QueryRecord(BaseModel):
    """Bronze -- raw data from a source provider."""
    query: str
    impressions: int = 0
    clicks: int = 0
    ctr: float = 0.0
    position: float = 0.0


class SourceConfig(DBItem, BaseModel):
    """
    Configuration for a data source.

    Access patterns:
        List all sources for user:
            query(TABLE, SourceConfig, user_id=user_id)
            -> PK=USER#{user_id}, SK prefix=SOURCE#

        Get specific source:
            get(TABLE, SourceConfig, user_id=user_id, source_id=source_id)
    """
    pk_pattern: ClassVar[str] = "USER#{user_id}"
    sk_pattern: ClassVar[str] = "SOURCE#{source_id}"

    user_id: str = "default"
    source_id: str
    source_type: str
    domain: str = ""
    credentials: Dict[str, str] = Field(default_factory=dict)
    settings: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class RunRecord(DBItem, BaseModel):
    """
    Bronze layer -- raw fetch result from a source provider.

    Access patterns:
        List all runs for user:
            query(TABLE, RunRecord, user_id=user_id)
            -> PK=USER#{user_id}, SK prefix=RUN#

        Get specific run:
            get(TABLE, RunRecord, user_id=user_id, run_id=run_id)
    """
    pk_pattern: ClassVar[str] = "USER#{user_id}"
    sk_pattern: ClassVar[str] = "RUN#{run_id}"

    user_id: str = "default"
    run_id: str
    domain: str = ""
    source_id: Optional[str] = None
    queries: List[QueryRecord] = Field(default_factory=list)
    fetched_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Silver / gold layer -- enrichments keyed by type
# ---------------------------------------------------------------------------

class Enrichment(DBItem, BaseModel):
    """
    Silver or gold layer -- derived data keyed by enrichment type.

    Known enrichment_type values:
        tags          silver   auto-generated query labels
        adjacent      silver   PAA and related queries from SerpAPI
        embeddings    silver   embedding vectors for seed and adjacent queries
        summaries     gold     LLM-generated cluster labels
        opportunities gold     ranked content gap recommendations

    Access patterns:
        All enrichments for a run:
            query(TABLE, Enrichment, user_id=user_id, run_id=run_id)
            -> PK=USER#{user_id}, SK prefix=RUN#{run_id}#ENRICHMENT#

        Specific enrichment:
            get(TABLE, Enrichment, user_id=user_id,
                run_id=run_id, enrichment_type=enrichment_type)
    """
    pk_pattern: ClassVar[str] = "USER#{user_id}"
    sk_pattern: ClassVar[str] = "RUN#{run_id}#ENRICHMENT#{enrichment_type}"

    user_id: str = "default"
    run_id: str
    enrichment_type: str
    layer: str = "silver"
    data: Dict[str, Any] = Field(default_factory=dict)
    derived_from: List[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Cluster models -- reheat_models table
# ---------------------------------------------------------------------------

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
    chronologically. The latest backbone is the last result of a prefix
    query on the model partition.

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
    proximity: Dict[str, float] = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class ClusterAssignments(DBItem, BaseModel):
    """
    Per-query cluster assignments produced by applying model M to run R.
    One record per (model, run) pair. Reapplying the same model to the
    same run overwrites this record. Deleted when the parent run is deleted
    via the RunModels adjacency index.

    Access patterns:
        Assignments for a specific (model, run) pair:
            get(TABLE, ClusterAssignments, user_id=user_id,
                model_id=model_id, run_id=run_id)
            -> PK=USER#{user_id}#MODEL#{model_id},
               SK=RUN#{run_id}#ASSIGNMENTS

        All assignment records for model M across runs:
            query(TABLE, ClusterAssignments, user_id=user_id, model_id=model_id)
            -> PK=USER#{user_id}#MODEL#{model_id}, SK prefix=RUN#
            Note: this prefix also returns ModelRunMetric and ModelRuns
            records. Supply run_id to the query to narrow if needed.
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
    Metrics for a single cluster computed from a specific run. One record
    per (model, cluster, computation). metric_id is a timestamp distinct
    from run_id, allowing recomputation without overwriting prior history.
    run_id is a data field for reference only.

    cluster_id is zero-padded to four digits so lexicographic and numeric
    sort orders agree: "0001", "0002", ..., "0016".

    This is the primary record for cluster trend analysis over time.

    Metrics:
        intent_demand     total observable demand for this cluster
                          (seed impressions + adjacent impression weights)
        coverage_health   fraction of intent_demand represented by seeds
                          (seed_impressions / intent_demand)
        click_quality     CTR within visible seed impressions
                          (clicks / seed_impressions)
        demand_capture    fraction of total demand resulting in a click
                          (clicks / intent_demand)
                          = coverage_health * click_quality

    Access patterns:
        Trend for cluster C across all computations (chronological):
            query(TABLE, ModelClusterMetric, user_id=user_id,
                  model_id=model_id, cluster_id=cluster_id)
            -> PK=USER#{user_id}#MODEL#{model_id},
               SK prefix=CLUSTER#{cluster_id}#METRIC#

        All metric records for model M:
            query(TABLE, ModelClusterMetric, user_id=user_id, model_id=model_id)
            -> PK=USER#{user_id}#MODEL#{model_id}, SK prefix=CLUSTER#

        Specific record:
            get(TABLE, ModelClusterMetric, user_id=user_id,
                model_id=model_id, cluster_id=cluster_id, metric_id=metric_id)
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
    Written atomically alongside ModelClusterMetric. Recomputing metrics
    for an existing run overwrites this record; history is preserved in
    ModelClusterMetric. metric_id matches the corresponding
    ModelClusterMetric record.

    This is the primary record for report generation: all cluster metrics
    for a given run under a given model.

    Access patterns:
        All cluster metrics for run R under model M:
            query(TABLE, ModelRunMetric, user_id=user_id,
                  model_id=model_id, run_id=run_id)
            -> PK=USER#{user_id}#MODEL#{model_id},
               SK prefix=RUN#{run_id}#CLUSTER#

        Specific cluster metric for run R:
            get(TABLE, ModelRunMetric, user_id=user_id,
                model_id=model_id, run_id=run_id, cluster_id=cluster_id)
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


# ---------------------------------------------------------------------------
# Many-to-many adjacency index: runs <-> models
# ---------------------------------------------------------------------------

class RunModels(DBItem, BaseModel):
    """
    Records that model M was applied to run R.
    One record per (run, model) pair. Written alongside ModelRuns.

    Primary traversal: given a run, list all models applied to it.
    Used by _delete_run_and_enrichments to locate all model-partition
    records that must be deleted when a run is removed.

    Access patterns:
        All models applied to run R:
            query(TABLE, RunModels, user_id=user_id, run_id=run_id)
            -> PK=USER#{user_id}#RUN#{run_id}, SK prefix=MODEL#

        Existence check for a specific (run, model) pair:
            get(TABLE, RunModels, user_id=user_id,
                run_id=run_id, model_id=model_id)
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
    One record per (model, run) pair. Written atomically alongside RunModels.

    Primary traversal: given a model, list all runs it has been applied to.
    Used by cmd_models_delete to check for dependent data before allowing
    deletion of a model.

    The SK suffix #APPLIED distinguishes this record from ClusterAssignments
    (RUN#{run_id}#ASSIGNMENTS) and ModelRunMetric (RUN#{run_id}#CLUSTER#...)
    within the same model partition.

    Access patterns:
        All runs a model has been applied to:
            query(TABLE, ModelRuns, user_id=user_id, model_id=model_id)
            -> PK=USER#{user_id}#MODEL#{model_id}, SK prefix=RUN#
            Note: this prefix also returns ClusterAssignments and
            ModelRunMetric records. Use get with a full run_id to target
            this record specifically.

        Specific (model, run) association:
            get(TABLE, ModelRuns, user_id=user_id,
                model_id=model_id, run_id=run_id)
            -> PK=USER#{user_id}#MODEL#{model_id}, SK=RUN#{run_id}#APPLIED
    """
    pk_pattern: ClassVar[str] = "USER#{user_id}#MODEL#{model_id}"
    sk_pattern: ClassVar[str] = "RUN#{run_id}#APPLIED"

    user_id: str = "default"
    model_id: str
    run_id: str
    applied_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Report layer -- pre-built report datasets
# ---------------------------------------------------------------------------

class ClusterSummary(BaseModel):
    """Pipeline-internal summary struct. Not persisted directly."""
    cluster_id: int
    label: str = ""
    description: str = ""
    top_queries: List[str] = Field(default_factory=list)
    query_count: int = 0
    total_impressions: int = 0
    total_clicks: int = 0
    avg_position: float = 0.0


class ProjectionData(DBItem, BaseModel):
    """
    Cached dimensionality reduction result for scatter plot rendering.

    Access patterns:
        Get projection for a run and method:
            get(TABLE, ProjectionData, user_id=user_id,
                run_id=run_id, method=method)
    """
    pk_pattern: ClassVar[str] = "USER#{user_id}"
    sk_pattern: ClassVar[str] = "RUN#{run_id}#PROJECTION#{method}"

    user_id: str = "default"
    run_id: str
    method: str
    embedding_model: str = ""
    seed_coords: List[List[float]] = Field(default_factory=list)
    adjacent_coords: List[List[float]] = Field(default_factory=list)
    created_at: Optional[datetime] = None


class ScatterData(DBItem, BaseModel):
    """Pre-built scatter plot datasets for the report."""
    pk_pattern: ClassVar[str] = "USER#{user_id}"
    sk_pattern: ClassVar[str] = "RUN#{run_id}#SCATTER"

    user_id: str = "default"
    run_id: str
    datasets: List[dict] = Field(default_factory=list)
    created_at: Optional[datetime] = None


class SummaryData(DBItem, BaseModel):
    """Pre-built summary panel data for the report."""
    pk_pattern: ClassVar[str] = "USER#{user_id}"
    sk_pattern: ClassVar[str] = "RUN#{run_id}#SUMMARY"

    user_id: str = "default"
    run_id: str
    top_performing: List[dict] = Field(default_factory=list)
    top_clusters: List[dict] = Field(default_factory=list)
    missed_opportunities: List[dict] = Field(default_factory=list)
    new_opportunities: List[dict] = Field(default_factory=list)
    created_at: Optional[datetime] = None


class CoverageData(DBItem, BaseModel):
    """Pre-built coverage table data for the report."""
    pk_pattern: ClassVar[str] = "USER#{user_id}"
    sk_pattern: ClassVar[str] = "RUN#{run_id}#COVERAGE"

    user_id: str = "default"
    run_id: str
    queries: List[dict] = Field(default_factory=list)
    created_at: Optional[datetime] = None
