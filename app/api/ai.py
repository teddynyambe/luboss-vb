from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.member import MemberProfile, MemberStatus
from app.services.member import get_member_profile_by_user_id
from pydantic import BaseModel
from typing import Optional, List, Dict

router = APIRouter(prefix="/api/ai", tags=["ai"])


class ChatRequest(BaseModel):
    query: str
    is_first_message: bool = False  # Flag to indicate if this is the first message


class ChatResponse(BaseModel):
    response: str
    citations: Optional[List[Dict]] = None
    tool_calls: Optional[List[Dict]] = None


@router.get("/greeting")
def get_greeting(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get personalized greeting for the logged-in user."""
    # Use get_current_user instead of require_member to allow any authenticated user
    # The chat endpoint will still enforce active member requirement
    
    # Get user's first name
    first_name = current_user.first_name or "Member"
    
    # Check if member profile exists and status
    member_profile = get_member_profile_by_user_id(db, current_user.id)
    if member_profile and member_profile.status == MemberStatus.ACTIVE:
        # Active member - full greeting
        greeting = f"Shani ama yama ba {first_name}! I'm your Luboss VB Finance Assistant. I'm here to help you with:\n\n"
        greeting += "• Information about the app and how to use it\n"
        greeting += "• Questions about the uploaded constitution and its interpretation\n"
        greeting += "• Your account details, transactions, savings, loans, and declarations\n"
        greeting += "• Understanding village banking rules and policies\n\n"
        greeting += "How can I assist you today?"
    else:
        # Not an active member yet - simpler greeting
        greeting = f"Shani ama yama ba {first_name}! I'm your Luboss VB Finance Assistant.\n\n"
        if member_profile and member_profile.status == MemberStatus.INACTIVE:
            greeting += "Your member account is inactive. Once activated, I'll be able to help you with:\n"
        else:
            greeting += "I'm here to help you with:\n"
        greeting += "• Information about the app and how to use it\n"
        greeting += "• Questions about the uploaded constitution and its interpretation\n"
        greeting += "• Understanding village banking rules and policies\n\n"
        greeting += "How can I assist you today?"
    
    return ChatResponse(
        response=greeting,
        citations=None,
        tool_calls=None
    )


@router.post("/chat", response_model=ChatResponse)
def chat(
    chat_request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """AI chat endpoint - RAG + tool-based responses."""
    from app.ai.chat import process_ai_query
    
    # Check if user has a member profile
    member_profile = get_member_profile_by_user_id(db, current_user.id)
    if not member_profile:
        raise HTTPException(
            status_code=403, 
            detail="You need to have a member profile to use the AI chat. Please contact an administrator."
        )
    
    # For account-related queries, require active status
    # For general questions about app/constitution, allow pending members too
    query_lower = chat_request.query.lower()
    is_account_query = any(keyword in query_lower for keyword in [
        "my", "account", "balance", "loan", "savings", "penalty", "declaration", "status",
        "transaction", "deposit", "withdrawal", "repayment", "interest", "fund"
    ])
    
    if is_account_query and member_profile.status != MemberStatus.ACTIVE:
        raise HTTPException(
            status_code=403, 
            detail="Your member account must be active to access account information. Your account is currently pending approval."
        )
    
    # If this is the first message, return greeting instead of processing
    if chat_request.is_first_message:
        first_name = current_user.first_name or "Member"
        greeting = f"Shani ama yama ba {first_name}! I'm your Luboss VB Finance Assistant. I'm here to help you with:\n\n"
        greeting += "• Information about the app and how to use it\n"
        greeting += "• Questions about the uploaded constitution and its interpretation\n"
        greeting += "• Your account details, transactions, savings, loans, and declarations\n"
        greeting += "• Understanding village banking rules and policies\n\n"
        greeting += "How can I assist you today?"
        
        return ChatResponse(
            response=greeting,
            citations=None,
            tool_calls=None
        )
    
    # Process query through AI service
    result = process_ai_query(
        db=db,
        user_id=current_user.id,
        member_id=member_profile.id,
        user_first_name=current_user.first_name,
        query=chat_request.query
    )
    
    return ChatResponse(
        response=result.get("response", ""),
        citations=result.get("citations"),
        tool_calls=result.get("tool_calls")
    )
