"""AI tool contracts - no direct SQL access for LLM."""
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Dict, List
from app.services.accounting import get_member_savings_balance, get_member_loan_balance
from app.models.transaction import Loan, PenaltyRecord, Declaration
from app.models.member import MemberProfile


def get_my_account_summary(
    db: Session,
    user_id: UUID,
    cycle_id: UUID = None
) -> Dict:
    """Get member's account summary (user-scoped)."""
    from app.services.member import get_member_profile_by_user_id
    
    member_profile = get_member_profile_by_user_id(db, user_id)
    if not member_profile:
        return {"error": "Member profile not found"}
    
    savings_balance = get_member_savings_balance(db, member_profile.id)
    loan_balance = get_member_loan_balance(db, member_profile.id)
    
    return {
        "member_id": str(member_profile.id),
        "savings_balance": float(savings_balance),
        "loan_balance": float(loan_balance),
        "status": member_profile.status.value
    }


def get_my_loans(
    db: Session,
    user_id: UUID
) -> List[Dict]:
    """Get member's loans (user-scoped)."""
    from app.services.member import get_member_profile_by_user_id
    
    member_profile = get_member_profile_by_user_id(db, user_id)
    if not member_profile:
        return []
    
    loans = db.query(Loan).filter(Loan.member_id == member_profile.id).all()
    return [
        {
            "loan_id": str(loan.id),
            "amount": float(loan.loan_amount),
            "interest_rate": float(loan.percentage_interest),
            "status": loan.loan_status.value,
            "disbursement_date": loan.disbursement_date.isoformat() if loan.disbursement_date else None
        }
        for loan in loans
    ]


def get_my_penalties(
    db: Session,
    user_id: UUID,
    cycle_id: UUID = None
) -> List[Dict]:
    """Get member's penalties (user-scoped)."""
    from app.services.member import get_member_profile_by_user_id
    from app.models.transaction import PenaltyType
    
    member_profile = get_member_profile_by_user_id(db, user_id)
    if not member_profile:
        return []
    
    query = db.query(PenaltyRecord).filter(PenaltyRecord.member_id == member_profile.id)
    if cycle_id:
        # Would need cycle relationship
        pass
    
    penalties = query.all()
    result = []
    for penalty in penalties:
        penalty_info = {
            "penalty_id": str(penalty.id),
            "date_issued": penalty.date_issued.isoformat(),
            "status": penalty.status.value,
            "notes": penalty.notes or ""
        }
        
        # Get penalty type information if available
        try:
            if penalty.penalty_type:
                penalty_info["penalty_type"] = {
                    "name": penalty.penalty_type.name,
                    "description": penalty.penalty_type.description or "",
                    "fee_amount": float(penalty.penalty_type.fee_amount)
                }
        except Exception:
            pass
        
        result.append(penalty_info)
    
    return result


def get_my_declarations(
    db: Session,
    user_id: UUID,
    month: str = None
) -> List[Dict]:
    """Get member's declarations (user-scoped)."""
    from app.services.member import get_member_profile_by_user_id
    
    member_profile = get_member_profile_by_user_id(db, user_id)
    if not member_profile:
        return []
    
    query = db.query(Declaration).filter(Declaration.member_id == member_profile.id)
    if month:
        # Filter by month
        pass
    
    declarations = query.all()
    return [
        {
            "declaration_id": str(decl.id),
            "effective_month": decl.effective_month.isoformat(),
            "status": decl.status.value
        }
        for decl in declarations
    ]


def explain_interest_rate(
    db: Session,
    loan_amount: float,
    months: str,
    borrow_count: int,
    credit_tier: str = None
) -> Dict:
    """Explain interest rate calculation."""
    from app.services.policy import calculate_interest_rate
    
    try:
        rate = calculate_interest_rate(
            db=db,
            term_months=months,
            loan_amount=float(loan_amount),
            borrow_count=borrow_count,
            credit_tier_id=None  # Would need to resolve from tier name
        )
        return {
            "interest_rate": float(rate),
            "explanation": f"Base rate for {months} months, adjusted for borrow count {borrow_count}"
        }
    except Exception as e:
        return {"error": str(e)}


def get_my_credit_rating(
    db: Session,
    user_id: UUID
) -> Dict:
    """Get member's credit rating for the current cycle (user-scoped)."""
    from app.services.member import get_member_profile_by_user_id
    from app.services.cycle import get_current_cycle
    from app.models.policy import MemberCreditRating, CreditRatingTier, BorrowingLimitPolicy, CreditRatingInterestRange
    from app.services.accounting import get_member_savings_balance
    
    member_profile = get_member_profile_by_user_id(db, user_id)
    if not member_profile:
        return {"error": "Member profile not found"}
    
    # Get current active cycle
    current_cycle = get_current_cycle(db)
    if not current_cycle:
        return {"error": "No active cycle found"}
    
    # Get member's credit rating for this cycle
    credit_rating = db.query(MemberCreditRating).filter(
        MemberCreditRating.member_id == member_profile.id,
        MemberCreditRating.cycle_id == current_cycle.id
    ).first()
    
    if not credit_rating:
        return {
            "has_credit_rating": False,
            "message": "No credit rating assigned for the current cycle. Please contact the administrator."
        }
    
    # Get tier details
    tier = db.query(CreditRatingTier).filter(CreditRatingTier.id == credit_rating.tier_id).first()
    if not tier:
        return {
            "has_credit_rating": False,
            "message": "Credit rating tier not found."
        }
    
    # Get borrowing limit (multiplier)
    borrowing_limit = db.query(BorrowingLimitPolicy).filter(
        BorrowingLimitPolicy.tier_id == tier.id,
        BorrowingLimitPolicy.effective_from <= current_cycle.end_date
    ).order_by(BorrowingLimitPolicy.effective_from.desc()).first()
    
    # Get member's savings balance
    savings_balance = get_member_savings_balance(db, member_profile.id)
    
    # Calculate max loan amount if borrowing limit exists
    max_loan_amount = None
    if borrowing_limit:
        max_loan_amount = float(savings_balance * borrowing_limit.multiplier)
    
    # Get available interest rates for this tier
    interest_ranges = db.query(CreditRatingInterestRange).filter(
        CreditRatingInterestRange.tier_id == tier.id,
        CreditRatingInterestRange.cycle_id == current_cycle.id
    ).all()
    
    # Format available terms
    available_terms = []
    for ir in interest_ranges:
        if ir.term_months is None:
            available_terms.append({
                "term_months": None,
                "term_label": "All Terms",
                "interest_rate": float(ir.effective_rate_percent)
            })
        else:
            available_terms.append({
                "term_months": ir.term_months,
                "term_label": f"{ir.term_months} Month{'s' if ir.term_months != 1 else ''}",
                "interest_rate": float(ir.effective_rate_percent)
            })
    
    return {
        "has_credit_rating": True,
        "tier_name": tier.tier_name,
        "tier_order": tier.tier_order,
        "tier_description": tier.description,
        "savings_balance": float(savings_balance),
        "multiplier": float(borrowing_limit.multiplier) if borrowing_limit else None,
        "max_loan_amount": max_loan_amount,
        "available_terms": available_terms,
        "assigned_at": credit_rating.assigned_at.isoformat() if credit_rating.assigned_at else None
    }


def get_policy_answer(
    db: Session,
    query: str
) -> Dict:
    """Get policy answer from RAG (constitution and other policy docs)."""
    from app.ai.retrieval import retrieve_relevant_chunks, format_citations
    
    # Search all documents, not just constitution (document_name=None searches all)
    chunks = retrieve_relevant_chunks(db, query, top_k=8, document_name=None)
    citations = format_citations(chunks)
    
    # Combine chunk texts as context
    context = "\n\n".join([chunk.get("chunk_text", "") for chunk in chunks])
    
    return {
        "context": context,
        "citations": citations
    }


def get_penalty_information(
    db: Session
) -> Dict:
    """Get penalty types and cycle phase penalty configurations. Use this when users ask about penalties, penalty types, when penalties are applied, automatic penalties, or penalty rules."""
    from app.models.transaction import PenaltyType
    from app.models.cycle import Cycle, CyclePhase
    from app.services.cycle import get_current_cycle
    
    # Get current active cycle
    current_cycle = get_current_cycle(db)
    if not current_cycle:
        return {
            "error": "No active cycle found",
            "penalty_types": [],
            "phase_penalties": []
        }
    
    # Get all enabled penalty types
    penalty_types = db.query(PenaltyType).filter(PenaltyType.enabled == "1").order_by(PenaltyType.name).all()
    penalty_types_list = [
        {
            "id": str(pt.id),
            "name": pt.name,
            "description": pt.description or "",
            "fee_amount": float(pt.fee_amount)
        }
        for pt in penalty_types
    ]
    
    # Get cycle phases with penalty configurations
    phases = db.query(CyclePhase).filter(CyclePhase.cycle_id == current_cycle.id).all()
    phase_penalties = []
    
    for phase in phases:
        phase_info = {
            "phase_type": phase.phase_type.value,
            "phase_name": phase.phase_type.value.replace("_", " ").title(),
            "monthly_start_day": phase.monthly_start_day,
            "monthly_end_day": phase.monthly_end_day,
            "has_penalty": False,
            "penalty_type": None,
            "auto_apply": False
        }
        
        # Safely get penalty information (columns might not exist yet)
        try:
            penalty_type_id = getattr(phase, 'penalty_type_id', None)
            if penalty_type_id:
                # Find the penalty type
                penalty_type = db.query(PenaltyType).filter(PenaltyType.id == penalty_type_id).first()
                if penalty_type:
                    phase_info["has_penalty"] = True
                    phase_info["penalty_type"] = {
                        "id": str(penalty_type.id),
                        "name": penalty_type.name,
                        "description": penalty_type.description or "",
                        "fee_amount": float(penalty_type.fee_amount)
                    }
                    phase_info["auto_apply"] = getattr(phase, 'auto_apply_penalty', False)
        except Exception:
            pass
        
        phase_penalties.append(phase_info)
    
    return {
        "cycle_year": current_cycle.year,
        "penalty_types": penalty_types_list,
        "phase_penalties": phase_penalties
    }


def get_member_info(
    db: Session,
    search_term: str = None,
    status: str = None
) -> Dict:
    """
    Get member information (non-financial) by name, email, or status.
    Returns member details excluding savings, loans, penalties, and other financial information.
    Use this when users ask about other members, member lists, member status, or member contact information.
    """
    from app.models.member import MemberProfile, MemberStatus
    from app.models.user import User
    
    # Build query
    query = db.query(MemberProfile).join(User, MemberProfile.user_id == User.id)
    
    # Apply filters
    if search_term:
        search_lower = search_term.lower()
        # Search by name or email
        from sqlalchemy import or_, func
        query = query.filter(
            or_(
                User.first_name.ilike(f"%{search_term}%"),
                User.last_name.ilike(f"%{search_term}%"),
                User.email.ilike(f"%{search_term}%"),
                func.concat(User.first_name, " ", User.last_name).ilike(f"%{search_term}%")
            )
        )
    
    if status:
        try:
            status_enum = MemberStatus(status.lower())
            query = query.filter(MemberProfile.status == status_enum)
        except ValueError:
            # Invalid status, ignore filter
            pass
    
    # Get results
    members = query.all()
    
    if not members:
        return {
            "members": [],
            "count": 0,
            "message": f"No members found matching the search criteria."
        }
    
    # Format results (exclude financial data)
    member_list = []
    for member in members:
        user = member.user
        member_info = {
            "member_id": str(member.id),
            "name": f"{user.first_name or ''} {user.last_name or ''}".strip(),
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "phone_number": user.phone_number,
            "status": member.status.value,
            "date_joined": user.date_joined.isoformat() if user.date_joined else None,
            "activated_at": member.activated_at.isoformat() if member.activated_at else None,
        }
        member_list.append(member_info)
    
    return {
        "members": member_list,
        "count": len(member_list),
        "message": f"Found {len(member_list)} member(s)."
    }
