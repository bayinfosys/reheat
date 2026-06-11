from datetime import datetime
from typing import Any, ClassVar, Dict, List, Optional

from dynawrap import DBItem
from pydantic import BaseModel, Field


class Enrichment(DBItem, BaseModel):
    """
    Silver or gold layer -- derived data keyed by enrichment type and source.

    source_id identifies what produced this enrichment:
        adjacent    serp:google, serp:youtube, etc.
        tags        regex
        embeddings  sentence-transformers/all-MiniLM-L6-v2, etc.
        summaries   openai, anthropic, marigold
        schedule    openai, anthropic, marigold
        overview    openai, anthropic, marigold
        opportunities, schedule, overview  default

    Access patterns:
        All enrichments for a run:
            query(TABLE, Enrichment, user_id=user_id, run_id=run_id)
            -> PK=USER#{user_id}, SK prefix=RUN#{run_id}#ENRICHMENT#

        All enrichments of a type for a run:
            query(TABLE, Enrichment, user_id=user_id,
                  run_id=run_id, enrichment_type=enrichment_type)
            -> SK prefix=RUN#{run_id}#ENRICHMENT#{enrichment_type}#

        Specific enrichment:
            get(TABLE, Enrichment, user_id=user_id,
                run_id=run_id, enrichment_type=enrichment_type,
                source_id=source_id)
    """
    pk_pattern: ClassVar[str] = "USER#{user_id}"
    sk_pattern: ClassVar[str] = "RUN#{run_id}#ENRICHMENT#{enrichment_type}#{source_id}"

    user_id: str = "default"
    run_id: str
    enrichment_type: str
    source_id: str = "default"
    layer: str = "silver"
    data: Dict[str, Any] = Field(default_factory=dict)
    derived_from: List[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None
