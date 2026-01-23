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
    
    member_profile = get_member_profile_by_user_id(db, user_id)
    if not member_profile:
        return []
    
    query = db.query(PenaltyRecord).filter(PenaltyRecord.member_id == member_profile.id)
    if cycle_id:
        # Would need cycle relationship
        pass
    
    penalties = query.all()
    return [
        {
            "penalty_id": str(penalty.id),
            "date_issued": penalty.date_issued.isoformat(),
            "status": penalty.status.value
        }
        for penalty in penalties
    ]


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
