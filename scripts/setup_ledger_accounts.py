#!/usr/bin/env python3
"""
Script to set up required ledger accounts for the Village Banking system.
Run this script to create all necessary accounts for deposit approvals and other transactions.
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.orm import Session
from app.db.base import SessionLocal
from app.models.ledger import LedgerAccount, AccountType
from app.models.member import MemberProfile
from uuid import uuid4

def create_ledger_accounts(db: Session):
    """Create all required ledger accounts."""
    
    # Core organization accounts
    core_accounts = [
        {
            "account_code": "BANK_CASH",
            "account_name": "Bank Cash Account",
            "account_type": AccountType.ASSET,
            "description": "Main bank account for cash deposits"
        },
        {
            "account_code": "SOCIAL_FUND",
            "account_name": "Social Fund",
            "account_type": AccountType.LIABILITY,
            "description": "Social fund contributions from members"
        },
        {
            "account_code": "ADMIN_FUND",
            "account_name": "Administration Fund",
            "account_type": AccountType.LIABILITY,
            "description": "Administration fund contributions from members"
        },
        {
            "account_code": "INTEREST_INCOME",
            "account_name": "Interest Income",
            "account_type": AccountType.INCOME,
            "description": "Interest income from loans"
        },
        {
            "account_code": "PENALTY_INCOME",
            "account_name": "Penalty Income",
            "account_type": AccountType.INCOME,
            "description": "Penalty income from late payments"
        },
    ]
    
    created_count = 0
    skipped_count = 0
    
    for account_data in core_accounts:
        existing = db.query(LedgerAccount).filter(
            LedgerAccount.account_code == account_data["account_code"]
        ).first()
        
        if existing:
            print(f"✓ Account {account_data['account_code']} already exists")
            skipped_count += 1
        else:
            account = LedgerAccount(**account_data)
            db.add(account)
            print(f"✓ Created account: {account_data['account_code']} - {account_data['account_name']}")
            created_count += 1
    
    db.commit()
    
    # Create member-specific accounts for each member
    members = db.query(MemberProfile).all()
    member_accounts_created = 0
    
    for member in members:
        # Member Savings Account
        savings_account = db.query(LedgerAccount).filter(
            LedgerAccount.member_id == member.id,
            LedgerAccount.account_name.ilike("%savings%")
        ).first()
        
        if not savings_account:
            # Use short code - just use member_id as string (first 8 chars of UUID)
            short_id = str(member.id).replace('-', '')[:8]
            savings_account = LedgerAccount(
                account_code=f"MEM_SAV_{short_id}",
                account_name=f"Member Savings - {member.id}",
                account_type=AccountType.LIABILITY,
                member_id=member.id,
                description=f"Savings account for member {member.id}"
            )
            db.add(savings_account)
            member_accounts_created += 1
            print(f"✓ Created savings account for member {member.id}")
        
        # Penalties Payable Account
        penalties_account = db.query(LedgerAccount).filter(
            LedgerAccount.member_id == member.id,
            LedgerAccount.account_name.ilike("%penalties payable%")
        ).first()
        
        if not penalties_account:
            short_id = str(member.id).replace('-', '')[:8]
            penalties_account = LedgerAccount(
                account_code=f"PEN_PAY_{short_id}",
                account_name=f"Penalties Payable - {member.id}",
                account_type=AccountType.LIABILITY,
                member_id=member.id,
                description=f"Penalties payable account for member {member.id}"
            )
            db.add(penalties_account)
            member_accounts_created += 1
            print(f"✓ Created penalties payable account for member {member.id}")
        
        # Loans Receivable Account
        loans_account = db.query(LedgerAccount).filter(
            LedgerAccount.member_id == member.id,
            LedgerAccount.account_name.ilike("%loan%receivable%")
        ).first()
        
        if not loans_account:
            short_id = str(member.id).replace('-', '')[:8]
            loans_account = LedgerAccount(
                account_code=f"LOAN_REC_{short_id}",
                account_name=f"Loans Receivable - {member.id}",
                account_type=AccountType.ASSET,
                member_id=member.id,
                description=f"Loans receivable account for member {member.id}"
            )
            db.add(loans_account)
            member_accounts_created += 1
            print(f"✓ Created loans receivable account for member {member.id}")
    
    db.commit()
    
    print(f"\n{'='*60}")
    print(f"Summary:")
    print(f"  Core accounts created: {created_count}")
    print(f"  Core accounts skipped: {skipped_count}")
    print(f"  Member accounts created: {member_accounts_created}")
    print(f"{'='*60}\n")
    
    return created_count + member_accounts_created


def main():
    """Main function to set up ledger accounts."""
    print("Setting up ledger accounts...")
    print("="*60)
    
    db = SessionLocal()
    try:
        count = create_ledger_accounts(db)
        print(f"✓ Successfully set up {count} new ledger accounts")
    except Exception as e:
        print(f"✗ Error setting up ledger accounts: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
