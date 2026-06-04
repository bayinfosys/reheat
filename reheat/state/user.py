from typing import ClassVar, List, Literal
from pydantic import BaseModel, Field
from dynawrap import DBItem


class UserState(DBItem, BaseModel):
    """
    User preferences and analysis parameters.
    Source credentials live in SourceConfig records, not here.
    """
    pk_pattern: ClassVar[str] = "USER#{user_id}"
    sk_pattern: ClassVar[str] = "STATE#USER"

    user_id: str = "default"

    # Provider preferences
    embedding_provider: Literal["local", "openai", "marigold"] = "local"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    summary_model: str = "default"
    projection_method: Literal["umap", "tsne", "pca"] = "umap"

    # Analysis parameters
    cluster_k: int = 32
    summarise_top_n: int = 10
    fetch_days: int = 90
    fetch_limit: int = 25000  # google limit
    serp_enrich_limit: int = 50
    serp_delay: float = 0.5

    # Default source (convenience -- can be overridden per run)
    default_source_id: str = ""
