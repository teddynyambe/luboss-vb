from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.models.member import MemberStatus


class MemberProfileResponse(BaseModel):
    id: str
    user_id: str
    status: MemberStatus
    created_at: datetime
    activated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class MemberActivateRequest(BaseModel):
    member_id: str
