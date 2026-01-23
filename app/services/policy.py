from sqlalchemy.orm import Session
from app.models.policy import (
    InterestPolicy,
    InterestThresholdPolicy,
    BorrowingLimitPolicy,
    CreditRatingTier,
    MemberCreditRating,
    CollateralPolicyVersion
)
from app.models.transaction import Loan
from decimal import Decimal
from uuid import UUID
from datetime import date


def calculate_interest_rate(
    db: Session,
    term_months: str,
    loan_amount: Decimal,
    borrow_count: int,
    credit_tier_id: UUID = None
) -> Decimal:
    """
    Calculate interest rate based on:
    - Base rate for term
    - Threshold reductions (from 3rd borrow)
    - Credit tier adjustments
    """
    # Get base interest rate
    interest_policy = db.query(InterestPolicy).filter(
        InterestPolicy.term_months == term_months
    ).order_by(InterestPolicy.effective_from.desc()).first()
    
    if not interest_policy:
        raise ValueError(f"No interest policy found for term: {term_months} months")
    
    base_rate = interest_policy.base_rate_percent
    
    # Apply threshold reductions (from 3rd borrow)
    if borrow_count >= 3:
        threshold_policies = db.query(InterestThresholdPolicy).filter(
            InterestThresholdPolicy.applies_from_borrow_count <= borrow_count
        ).order_by(InterestThresholdPolicy.effective_from.desc()).all()
        
        for policy in threshold_policies:
            if loan_amount >= policy.threshold_amount:
                base_rate = base_rate - policy.reduction_percent
                break  # Apply only the highest matching threshold
    
    # Apply credit tier adjustments (e.g., LOW RISK starts at 8%)
    if credit_tier_id:
        tier = db.query(CreditRatingTier).filter(CreditRatingTier.id == credit_tier_id).first()
        if tier and tier.tier_name == "LOW RISK":
            # Special rule: LOW RISK starts at 8% in new cycle
            # This would need cycle context - simplified here
            pass
    
    return max(Decimal("0"), base_rate)  # Ensure non-negative


def get_borrowing_limit(
    db: Session,
    member_id: UUID,
    cycle_id: UUID,
    savings_balance: Decimal
) -> Decimal:
    """Calculate maximum borrowing limit based on credit tier and savings."""
    # Get member's credit rating for cycle
    credit_rating = db.query(MemberCreditRating).filter(
        MemberCreditRating.member_id == member_id,
        MemberCreditRating.cycle_id == cycle_id
    ).first()
    
    if not credit_rating:
        # Default: NEW AND DEFAULTED OLD MEMBERS - 2× savings
        multiplier = Decimal("2.00")
    else:
        # Get borrowing limit policy for tier
        limit_policy = db.query(BorrowingLimitPolicy).filter(
            BorrowingLimitPolicy.tier_id == credit_rating.tier_id
        ).order_by(BorrowingLimitPolicy.effective_from.desc()).first()
        
        if limit_policy:
            multiplier = limit_policy.multiplier
        else:
            multiplier = Decimal("2.00")  # Default
    
    max_amount = savings_balance * multiplier
    
    # Apply max cap if specified
    if credit_rating:
        limit_policy = db.query(BorrowingLimitPolicy).filter(
            BorrowingLimitPolicy.tier_id == credit_rating.tier_id
        ).order_by(BorrowingLimitPolicy.effective_from.desc()).first()
        
        if limit_policy and limit_policy.max_amount:
            max_amount = min(max_amount, limit_policy.max_amount)
    
    return max_amount


def requires_collateral(
    db: Session,
    loan_amount: Decimal
) -> bool:
    """Check if loan amount requires collateral (typically > K100,000)."""
    # Get current collateral policy
    policy = db.query(CollateralPolicyVersion).order_by(
        CollateralPolicyVersion.effective_from.desc()
    ).first()
    
    if not policy:
        # Default threshold
        return loan_amount > Decimal("100000.00")
    
    # Parse policy text for threshold (simplified - would need proper parsing)
    # For now, use default
    return loan_amount > Decimal("100000.00")


def get_member_borrow_count(
    db: Session,
    member_id: UUID
) -> int:
    """Get count of loans borrowed by member (for interest calculation)."""
    return db.query(Loan).filter(
        Loan.member_id == member_id,
        Loan.loan_status.in_(["disbursed", "closed", "open"])
    ).count()
