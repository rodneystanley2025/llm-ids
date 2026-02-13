from pydantic import BaseModel, Field
from typing import Any, Dict, Optional, Literal

Role = Literal["user", "assistant", "system"]

class Event(BaseModel):
    session_id: str
    turn_id: int = Field(ge=0)
    ts: Optional[str] = None
    role: Role
    content: str
    model: Optional[str] = None
    meta: Dict[str, Any] = {}
