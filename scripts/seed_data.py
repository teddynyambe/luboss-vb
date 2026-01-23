"""
Seed initial data: roles, policies, chart of accounts.
"""
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.db.base import SessionLocal
from app.models.role import Role
from app.models.ledger import LedgerAccount, AccountType
from app.models.policy import (
    InterestPolicy,
    InterestThresholdPolicy,
    CreditRatingScheme,
    CreditRatingTier,
    BorrowingLimitPolicy
)
from decimal import Decimal
from datetime import date


def seed_roles(db):
    """Seed default roles."""
    print("Seeding roles...")
    roles = [
        {"name": "Admin", "description": "System administrator"},
        {"name": "Chairman", "description": "Village Banking chairman"},
        {"name": "Vice-Chairman", "description": "Vice-chairman"},
        {"name": "Treasurer", "description": "Treasurer"},
        {"name": "Compliance", "description": "Compliance officer"},
        {"name": "Member", "description": "Regular member"}
    ]
    
    for role_data in roles:
        existing = db.query(Role).filter(Role.name == role_data["name"]).first()
        if not existing:
            role = Role(**role_data)
            db.add(role)
    
    db.commit()
    print("Roles seeded")


def seed_chart_of_accounts(db):
    """Seed chart of accounts."""
    print("Seeding chart of accounts...")
    
    accounts = [
        # Assets
        {"account_code": "BANK_CASH", "account_name": "Bank Cash Account", "account_type": AccountType.ASSET},
        {"account_code": "LOANS_RECEIVABLE", "account_name": "Loans Receivable", "account_type": AccountType.ASSET},
        
        # Liabilities
        {"account_code": "MEMBER_SAVINGS", "account_name": "Member Savings Payable", "account_type": AccountType.LIABILITY},
        {"account_code": "SOCIAL_FUND", "account_name": "Social Fund Payable", "account_type": AccountType.LIABILITY},
        {"account_code": "ADMIN_FUND", "account_name": "Admin Fund Payable", "account_type": AccountType.LIABILITY},
        
        # Income
        {"account_code": "INTEREST_INCOME", "account_name": "Interest Income", "account_type": AccountType.INCOME},
        {"account_code": "PENALTY_INCOME", "account_name": "Penalty Income", "account_type": AccountType.INCOME},
        
        # Equity
        {"account_code": "CARRY_FORWARD", "account_name": "Carry-Forward Reserve", "account_type": AccountType.EQUITY}
    ]
    
    for acc_data in accounts:
        existing = db.query(LedgerAccount).filter(LedgerAccount.account_code == acc_data["account_code"]).first()
        if not existing:
            account = LedgerAccount(**acc_data)
            db.add(account)
    
    db.commit()
    print("Chart of accounts seeded")


def seed_policies(db):
    """Seed interest and credit rating policies."""
    print("Seeding policies...")
    
    # Interest policy
    interest_policies = [
        {"term_months": "1", "base_rate_percent": Decimal("10.00"), "effective_from": date(2024, 1, 1)},
        {"term_months": "2", "base_rate_percent": Decimal("15.00"), "effective_from": date(2024, 1, 1)},
        {"term_months": "3", "base_rate_percent": Decimal("20.00"), "effective_from": date(2024, 1, 1)},
        {"term_months": "4", "base_rate_percent": Decimal("25.00"), "effective_from": date(2024, 1, 1)}
    ]
    
    for policy_data in interest_policies:
        existing = db.query(InterestPolicy).filter(
            InterestPolicy.term_months == policy_data["term_months"],
            InterestPolicy.effective_from == policy_data["effective_from"]
        ).first()
        if not existing:
            policy = InterestPolicy(**policy_data)
            db.add(policy)
    
    # Interest threshold policy
    threshold_policies = [
        {"threshold_amount": Decimal("25000.00"), "reduction_percent": Decimal("2.00"), "applies_from_borrow_count": 3, "effective_from": date(2024, 1, 1)},
        {"threshold_amount": Decimal("50000.00"), "reduction_percent": Decimal("3.00"), "applies_from_borrow_count": 3, "effective_from": date(2024, 1, 1)}
    ]
    
    for policy_data in threshold_policies:
        existing = db.query(InterestThresholdPolicy).filter(
            InterestThresholdPolicy.threshold_amount == policy_data["threshold_amount"],
            InterestThresholdPolicy.effective_from == policy_data["effective_from"]
        ).first()
        if not existing:
            policy = InterestThresholdPolicy(**policy_data)
            db.add(policy)
    
    # Credit rating scheme
    scheme = db.query(CreditRatingScheme).filter(CreditRatingScheme.name == "Default Scheme").first()
    if not scheme:
        scheme = CreditRatingScheme(
            name="Default Scheme",
            effective_from=date(2024, 1, 1),
            description="Default credit rating scheme"
        )
        db.add(scheme)
        db.flush()
    
    # Credit rating tiers
    tiers = [
        {"tier_name": "NEW AND DEFAULTED OLD MEMBERS", "tier_order": 1, "description": "New members and defaulted old members"},
        {"tier_name": "MEDIUM RISK", "tier_order": 2, "description": "Medium risk members"},
        {"tier_name": "LOW RISK", "tier_order": 3, "description": "Low risk members"}
    ]
    
    for tier_data in tiers:
        existing = db.query(CreditRatingTier).filter(
            CreditRatingTier.scheme_id == scheme.id,
            CreditRatingTier.tier_name == tier_data["tier_name"]
        ).first()
        if not existing:
            tier = CreditRatingTier(scheme_id=scheme.id, **tier_data)
            db.add(tier)
            db.flush()
            
            # Borrowing limit policy
            multipliers = {"NEW AND DEFAULTED OLD MEMBERS": Decimal("2.00"), "MEDIUM RISK": Decimal("3.00"), "LOW RISK": Decimal("3.00")}
            limit_policy = BorrowingLimitPolicy(
                tier_id=tier.id,
                multiplier=multipliers.get(tier_data["tier_name"], Decimal("2.00")),
                effective_from=date(2024, 1, 1)
            )
            db.add(limit_policy)
    
    db.commit()
    print("Policies seeded")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        seed_roles(db)
        seed_chart_of_accounts(db)
        seed_policies(db)
        print("\nSeed data complete!")
    except Exception as e:
        db.rollback()
        print(f"Error seeding data: {e}")
        raise
    finally:
        db.close()
