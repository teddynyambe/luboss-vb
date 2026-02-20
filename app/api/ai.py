from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.core.dependencies import get_current_user, require_any_role
from app.models.user import User
from app.models.member import MemberProfile, MemberStatus
from app.services.member import get_member_profile_by_user_id
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime

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
        greeting += "• Group information: committee members, total members, current cycle\n"
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
        greeting += "• Group information: committee members, total members, current cycle\n"
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
        user_role=current_user.role.value if current_user.role else None,
        query=chat_request.query
    )

    return ChatResponse(
        response=result.get("response", ""),
        citations=result.get("citations"),
        tool_calls=result.get("tool_calls")
    )


def _generate_member_directory_text(db: Session) -> str:
    """Build a structured member directory text snapshot from the database."""
    from app.models.member import MemberProfile, MemberStatus
    from app.models.user import User
    from app.models.role import UserRole, Role
    from app.models.policy import MemberCreditRating, CreditRatingTier
    from app.models.transaction import Loan, LoanStatus
    from app.services.cycle import get_current_cycle

    now = datetime.utcnow()
    today_str = now.strftime("%Y-%m-%d")

    lines = [
        "=== LUBOSS VB MEMBER DIRECTORY ===",
        f"Generated: {today_str}",
        "",
    ]

    # Committee section
    committee_roles = ["Chairman", "Treasurer", "Compliance", "Vice-Chairman", "Secretary"]
    try:
        user_roles = db.query(UserRole).join(Role).join(
            User, UserRole.user_id == User.id
        ).filter(
            Role.name.in_(committee_roles),
            (UserRole.start_date.is_(None) | (UserRole.start_date <= now)),
            (UserRole.end_date.is_(None) | (UserRole.end_date >= now))
        ).all()

        if user_roles:
            lines.append("=== COMMITTEE ===")
            for ur in user_roles:
                user = ur.user
                name = f"{user.first_name or ''} {user.last_name or ''}".strip()
                since = ""
                if ur.start_date:
                    since = f" (active since {ur.start_date.strftime('%b %Y')})"
                lines.append(f"- {name}: {ur.role.name}{since}")
            lines.append("")
    except Exception:
        pass

    # Get current cycle for credit tier lookups
    try:
        current_cycle = get_current_cycle(db)
    except Exception:
        current_cycle = None

    # Members section
    all_members = db.query(MemberProfile).join(User, MemberProfile.user_id == User.id).all()
    active_count = sum(1 for m in all_members if m.status == MemberStatus.ACTIVE)
    inactive_count = sum(1 for m in all_members if m.status == MemberStatus.INACTIVE)

    lines.append(f"=== MEMBERS ({active_count} active, {inactive_count} inactive) ===")
    lines.append("")

    for member in all_members:
        user = member.user
        name = f"{user.first_name or ''} {user.last_name or ''}".strip()
        joined = user.date_joined.strftime("%B %Y") if user.date_joined else "Unknown"
        status_label = "Active" if member.status == MemberStatus.ACTIVE else "Inactive"

        # Roles
        member_roles = []
        try:
            uroles = db.query(UserRole).join(Role).filter(
                UserRole.user_id == user.id,
                (UserRole.start_date.is_(None) | (UserRole.start_date <= now)),
                (UserRole.end_date.is_(None) | (UserRole.end_date >= now))
            ).all()
            member_roles = [ur.role.name for ur in uroles if ur.role]
        except Exception:
            pass

        # Credit tier
        credit_tier = None
        try:
            if current_cycle:
                cr = db.query(MemberCreditRating).filter(
                    MemberCreditRating.member_id == member.id,
                    MemberCreditRating.cycle_id == current_cycle.id
                ).first()
                if cr:
                    tier = db.query(CreditRatingTier).filter(
                        CreditRatingTier.id == cr.tier_id
                    ).first()
                    if tier:
                        credit_tier = tier.tier_name
        except Exception:
            pass

        # Active loan
        has_active_loan = False
        try:
            active_loan = db.query(Loan).filter(
                Loan.member_id == member.id,
                Loan.loan_status.in_([LoanStatus.DISBURSED.value, LoanStatus.OPEN.value])
            ).first()
            has_active_loan = active_loan is not None
        except Exception:
            pass

        lines.append(f"Member: {name}")
        lines.append(f"  Status: {status_label} | Joined: {joined}")
        if member_roles:
            lines.append(f"  Roles: {', '.join(member_roles)}")
        lines.append(f"  Credit Tier: {credit_tier or 'Not assigned'}")
        lines.append(f"  Has Active Loan: {'Yes' if has_active_loan else 'No'}")
        lines.append("")

    return "\n".join(lines)


@router.post("/refresh-member-directory")
async def refresh_member_directory(
    current_user: User = Depends(require_any_role("Chairman", "Admin")),
    db: Session = Depends(get_db)
):
    """Regenerate and re-ingest the member directory document into the RAG vector store.
    Requires Chairman or Admin role.
    """
    from app.ai.ingestion import ingest_text_content

    text = _generate_member_directory_text(db)
    chunks = ingest_text_content(db, "member_directory", "live", text)
    return {"status": "ok", "chunks_created": len(chunks)}
