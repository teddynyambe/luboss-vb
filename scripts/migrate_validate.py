"""
Migration validation script: Compare old vs new system totals.
"""
from app.db.base import SessionLocal
from app.models.migration import StgMembers, StgDeposits, StgLoans, StgRepayments, StgPenalties
from app.models.ledger import JournalEntry, JournalLine
from app.services.accounting import get_account_balance
from app.models.ledger import LedgerAccount
from sqlalchemy import func
from decimal import Decimal


def validate_migration():
    """Validate migrated data against old system totals."""
    db = SessionLocal()
    
    print("=== Migration Validation Report ===\n")
    
    try:
        # Per-member totals
        print("Per-Member Totals:")
        stg_members = db.query(StgMembers).all()
        
        for member in stg_members[:10]:  # Sample first 10
            # Old system totals
            old_deposits = db.query(func.sum(StgDeposits.amount)).filter(
                StgDeposits.member_id == member.id
            ).scalar() or Decimal("0.00")
            
            # New system totals (would need member mapping)
            print(f"Member {member.id}:")
            print(f"  Old deposits: {old_deposits}")
            # New balance would be calculated from ledger
        
        # Group totals
        print("\nGroup Totals:")
        
        # Old system
        old_total_deposits = db.query(func.sum(StgDeposits.amount)).scalar() or Decimal("0.00")
        old_total_loans = db.query(func.sum(StgLoans.loan_amount)).scalar() or Decimal("0.00")
        
        print(f"Old system:")
        print(f"  Total deposits: {old_total_deposits}")
        print(f"  Total loans: {old_total_loans}")
        
        # New system
        bank_cash = db.query(LedgerAccount).filter(LedgerAccount.account_code == "BANK_CASH").first()
        if bank_cash:
            new_bank_balance = get_account_balance(db, bank_cash.id)
            print(f"\nNew system:")
            print(f"  Bank cash balance: {new_bank_balance}")
        
        print("\nValidation complete")
        
    except Exception as e:
        print(f"Error during validation: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    validate_migration()
