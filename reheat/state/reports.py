from datetime import datetime
from typing import ClassVar, List, Optional

from dynawrap import DBItem
from pydantic import BaseModel, Field


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
