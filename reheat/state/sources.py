from datetime import datetime
from typing import Any, ClassVar, Dict, Optional
from pydantic import BaseModel, Field
from dynawrap import DBItem


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
    settings: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
