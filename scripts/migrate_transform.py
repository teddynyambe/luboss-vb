"""
Migration script: Transform staging data into journal entries.
"""
from app.db.base import SessionLocal
from app.models.migration import (
    StgMembers, StgDeposits, StgLoans, StgRepayments, StgPenalties,
    IdMapUser, IdMapMember, IdMapLoan
)
from app.models.user import User
from app.models.member import MemberProfile
from app.models.transaction import Loan
from app.services.accounting import create_journal_entry
from app.models.ledger import LedgerAccount
from decimal import Decimal
from uuid import uuid4


def create_id_mappings(db):
    """Create ID mapping tables."""
    print("Creating ID mappings...")
    
    # Map users
    stg_members = db.query(StgMembers).all()
    for stg_member in stg_members:
        # Find or create user
        user = db.query(User).filter(User.email == stg_member.email).first()
        if not user:
            # User should already exist from migration
            continue
        
        id_map = IdMapUser(
            old_user_id=stg_member.id,
            new_user_id=user.id
        )
        db.add(id_map)
    
    db.commit()
    print("ID mappings created")


def transform_to_journals(db):
    """Transform transactions to journal entries."""
    print("Transforming transactions to journal entries...")
    
    # Get ledger accounts
    bank_cash = db.query(LedgerAccount).filter(LedgerAccount.account_code == "BANK_CASH").first()
    member_savings = db.query(LedgerAccount).filter(LedgerAccount.account_code.like("MEMBER_SAVINGS%")).first()
    social_fund = db.query(LedgerAccount).filter(LedgerAccount.account_code == "SOCIAL_FUND").first()
    admin_fund = db.query(LedgerAccount).filter(LedgerAccount.account_code == "ADMIN_FUND").first()
    loans_receivable = db.query(LedgerAccount).filter(LedgerAccount.account_code.like("LOANS_RECEIVABLE%")).first()
    interest_income = db.query(LedgerAccount).filter(LedgerAccount.account_code == "INTEREST_INCOME").first()
    penalty_income = db.query(LedgerAccount).filter(LedgerAccount.account_code == "PENALTY_INCOME").first()
    
    # Transform deposits
    print("Transforming deposits...")
    stg_deposits = db.query(StgDeposits).all()
    for deposit in stg_deposits:
        # Get member mapping
        id_map = db.query(IdMapUser).filter(IdMapUser.old_user_id == deposit.member_id).first()
        if not id_map:
            continue
        
        member_profile = db.query(MemberProfile).filter(MemberProfile.user_id == id_map.new_user_id).first()
        if not member_profile:
            continue
        
        # Get member's savings account
        member_savings_acc = db.query(LedgerAccount).filter(
            LedgerAccount.member_id == member_profile.id,
            LedgerAccount.account_name.ilike("%savings%")
        ).first()
        
        if not member_savings_acc:
            continue
        
        # Create journal entry (simplified - would need to split amounts properly)
        try:
            create_journal_entry(
                db=db,
                description=f"Migrated deposit from old system",
                lines=[
                    {
                        "account_id": bank_cash.id,
                        "debit_amount": deposit.amount or Decimal("0.00"),
                        "credit_amount": Decimal("0.00"),
                        "description": "Bank cash"
                    },
                    {
                        "account_id": member_savings_acc.id,
                        "debit_amount": Decimal("0.00"),
                        "credit_amount": deposit.amount or Decimal("0.00"),
                        "description": "Member savings"
                    }
                ],
                source_ref=deposit.id,
                source_type="migrated_deposit"
            )
        except Exception as e:
            print(f"Error transforming deposit {deposit.id}: {e}")
    
    db.commit()
    print("Transformation complete")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        create_id_mappings(db)
        transform_to_journals(db)
    finally:
        db.close()
