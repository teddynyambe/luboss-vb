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


def get_policy_answer(
    db: Session,
    query: str
) -> Dict:
    """Get policy answer from RAG (constitution and other policy docs)."""
    from app.ai.retrieval import retrieve_relevant_chunks, format_citations
    
    chunks = retrieve_relevant_chunks(db, query, top_k=5, document_name="constitution")
    citations = format_citations(chunks)
    
    # Combine chunk texts as context
    context = "\n\n".join([chunk.get("chunk_text", "") for chunk in chunks])
    
    return {
        "context": context,
        "citations": citations
    }
