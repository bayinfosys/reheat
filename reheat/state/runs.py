from datetime import datetime
from typing import Any, ClassVar, Dict, List, Optional

from dynawrap import DBItem
from pydantic import BaseModel, Field


class QueryRecord(BaseModel):
    """Bronze -- raw data from a source provider."""
    query: str
    impressions: int = 0
    clicks: int = 0
    ctr: float = 0.0
    position: float = 0.0


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
