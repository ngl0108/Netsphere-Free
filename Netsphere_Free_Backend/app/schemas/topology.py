from typing import List, Optional, Any, Dict
from pydantic import BaseModel, ConfigDict
from datetime import datetime

class TopologyLayoutBase(BaseModel):
    name: Optional[str] = "Default Layout"
    is_shared: Optional[bool] = False
    data: Any  # Supports legacy node arrays and richer layout envelopes with overrides

class TopologyLayoutCreate(TopologyLayoutBase):
    pass

class TopologyLayoutResponse(TopologyLayoutBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)
