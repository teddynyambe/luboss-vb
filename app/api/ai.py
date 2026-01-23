from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.core.dependencies import require_member, get_current_user
from app.models.user import User
from app.models.member import MemberProfile, MemberStatus
from app.services.member import get_member_profile_by_user_id
from pydantic import BaseModel
from typing import Optional, List, Dict

router = APIRouter(prefix="/api/ai", tags=["ai"])


class ChatRequest(BaseModel):
    query: str


class ChatResponse(BaseModel):
    response: str
    citations: Optional[List[Dict]] = None
    tool_calls: Optional[List[Dict]] = None


@router.post("/chat", response_model=ChatResponse)
def chat(
    chat_request: ChatRequest,
    current_user: User = Depends(require_member),
    db: Session = Depends(get_db)
):
    """AI chat endpoint - RAG + tool-based responses."""
    from app.ai.chat import process_ai_query
    
    member_profile = get_member_profile_by_user_id(db, current_user.id)
    if not member_profile or member_profile.status != MemberStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="Member account is not active")
    
    # Process query through AI service
    result = process_ai_query(
        db=db,
        user_id=current_user.id,
        member_id=member_profile.id,
        query=chat_request.query
    )
    
    return ChatResponse(
        response=result.get("response", ""),
        citations=result.get("citations"),
        tool_calls=result.get("tool_calls")
    )
