#!/usr/bin/env python3
"""
Script to clean the database, removing all user-entered data while preserving:
- Admin user
- All roles
- System configuration (policies, settings, ledger account structure)
- System documents (constitution, AI documents)

This script will:
- Delete all member profiles and related data
- Delete all transactions (declarations, deposits, loans, penalties)
- Delete all journal entries
- Delete all non-admin users
- Keep admin user, all system configuration, and all cycle data
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db.base import SessionLocal
from app.models.user import User
from app.models.member import MemberProfile, MemberStatusHistory
from app.models.role import Role, UserRole
from app.models.ledger import LedgerAccount, JournalEntry, JournalLine, PostingLock
from app.models.cycle import Cycle
from app.models.transaction import (
    Declaration,
    DepositProof,
    DepositApproval,
    LoanApplication,
    Loan,
    Repayment,
    PenaltyType,
    PenaltyRecord,
)
from app.models.policy import (
    CreditRatingScheme,
    CreditRatingTier,
    MemberCreditRating,
    InterestPolicy,
    InterestThresholdPolicy,
    BorrowingLimitPolicy,
    CreditRatingInterestRange,
    PolicyVersion,
    CollateralPolicyVersion,
    CollateralAsset,
    CollateralValuation,
    CollateralHold,
)
from app.models.system import SystemSettings, VBGroup, CommitteeAssignment, ConstitutionDocumentVersion
from app.models.ai import DocumentChunk, DocumentEmbedding, AIAuditLog
from app.models.migration import (
    IdMapUser,
    IdMapMember,
    IdMapLoan,
    StgMembers,
    StgDeposits,
    StgLoans,
    StgRepayments,
    StgPenalties,
    # StgCycles,
)


def get_admin_user(db: Session):
    """Get admin user by checking for admin role or email pattern."""
    # First try to find user with admin role
    admin_role = db.query(Role).filter(Role.name == "Admin").first()
    if admin_role:
        admin_user_role = db.query(UserRole).filter(UserRole.role_id == admin_role.id).first()
        if admin_user_role:
            admin_user = db.query(User).filter(User.id == admin_user_role.user_id).first()
            if admin_user:
                return admin_user
    
    # Fallback: find user with admin email pattern
    admin_user = db.query(User).filter(User.email.ilike("%admin%")).first()
    if admin_user:
        return admin_user
    
    # Last resort: find any user with admin role in legacy role field
    admin_user = db.query(User).filter(User.role == "admin").first()
    return admin_user


def clean_database(db: Session, admin_user_id=None, dry_run=False):
    """Clean all user-entered data while preserving system data.
    
    Args:
        db: Database session
        admin_user_id: ID of admin user to preserve (optional, will be auto-detected)
        dry_run: If True, only show what would be deleted without actually deleting
    """
    
    print("=" * 60)
    if dry_run:
        print("DATABASE CLEANUP - DRY RUN MODE (No changes will be made)")
    else:
        print("DATABASE CLEANUP - Removing User Data")
    print("=" * 60)
    print()
    
    # Get admin user if not provided
    if not admin_user_id:
        admin_user = get_admin_user(db)
        if not admin_user:
            print("⚠️  WARNING: No admin user found!")
            print("   The script will proceed but may delete all users.")
            response = input("   Continue anyway? (yes/no): ")
            if response.lower() != "yes":
                print("❌ Cleanup cancelled.")
                return
            admin_user_id = None
        else:
            admin_user_id = admin_user.id
            print(f"✓ Found admin user: {admin_user.email} (ID: {admin_user_id})")
            print()
    
    # Count records before deletion
    print("Counting records to be deleted...")
    counts = {
        "member_profiles": db.query(MemberProfile).count(),
        "declarations": db.query(Declaration).count(),
        "deposit_proofs": db.query(DepositProof).count(),
        "deposit_approvals": db.query(DepositApproval).count(),
        "loan_applications": db.query(LoanApplication).count(),
        "loans": db.query(Loan).count(),
        "repayments": db.query(Repayment).count(),
        "penalty_records": db.query(PenaltyRecord).count(),
        # "cycles": db.query(Cycle).count(),
        "journal_entries": db.query(JournalEntry).count(),
        "journal_lines": db.query(JournalLine).count(),
        "users": db.query(User).count(),
    }
    
    print("\nRecords to be deleted:")
    for key, count in counts.items():
        print(f"  {key}: {count}")
    
    print(f"\nTotal users: {counts['users']}")
    if admin_user_id:
        print(f"Admin user will be preserved")
    
    if not dry_run:
        print()
        response = input("⚠️  This will DELETE ALL USER DATA. Continue? (yes/no): ")
        if response.lower() != "yes":
            print("❌ Cleanup cancelled.")
            return
    else:
        print("⚠️  DRY RUN MODE - No data will be deleted")
        print()
    
    print()
    if dry_run:
        print("Simulating cleanup (DRY RUN)...")
    else:
        print("Starting cleanup...")
    print("-" * 60)
    
    try:
        if dry_run:
            # In dry run, just show what would be deleted
            print("\n📋 DRY RUN - Would delete the following:")
            for key, count in counts.items():
                if count > 0:
                    print(f"  ✓ {key}: {count} records")
            print("\n✅ DRY RUN COMPLETE - No data was deleted")
            return
        # Delete in order to respect foreign key constraints
        
        # 1. Delete journal lines first (depends on journal_entry)
        print("1. Deleting journal lines...")
        db.query(JournalLine).delete()
        print("   ✓ Deleted journal lines")
        
        # 2. Delete repayments (depends on loans)
        print("2. Deleting repayments...")
        db.query(Repayment).delete()
        print("   ✓ Deleted repayments")
        
        # 3. Delete deposit approvals (depends on journal_entry)
        print("3. Deleting deposit approvals...")
        db.query(DepositApproval).delete()
        print("   ✓ Deleted deposit approvals")
        
        # 4. Delete loans (may have disbursement_journal_entry_id, depends on loan applications)
        print("4. Deleting loans...")
        db.query(Loan).delete()
        print("   ✓ Deleted loans")
        
        # 5. Delete penalty records (may have journal_entry_id)
        print("5. Deleting penalty records...")
        db.query(PenaltyRecord).delete()
        print("   ✓ Deleted penalty records")
        
        # 6. Now safe to delete journal entries (all references removed)
        print("6. Deleting journal entries...")
        db.query(JournalEntry).delete()
        print("   ✓ Deleted journal entries")
        
        # 7. Delete loan applications
        print("7. Deleting loan applications...")
        db.query(LoanApplication).delete()
        print("   ✓ Deleted loan applications")
        
        # 8. Delete deposit proofs
        print("8. Deleting deposit proofs...")
        db.query(DepositProof).delete()
        print("   ✓ Deleted deposit proofs")
        
        # 9. Delete declarations
        print("9. Deleting declarations...")
        db.query(Declaration).delete()
        print("   ✓ Deleted declarations")
        
        # 10. Delete member credit ratings
        print("10. Deleting member credit ratings...")
        db.query(MemberCreditRating).delete()
        print("   ✓ Deleted member credit ratings")
        
        # 11. Delete collateral data
        print("11. Deleting collateral holds...")
        db.query(CollateralHold).delete()
        print("   ✓ Deleted collateral holds")
        
        print("12. Deleting collateral valuations...")
        db.query(CollateralValuation).delete()
        print("   ✓ Deleted collateral valuations")
        
        print("13. Deleting collateral assets...")
        db.query(CollateralAsset).delete()
        print("   ✓ Deleted collateral assets")
        
        # 12. Delete policy versions (references cycles)
        # print("14. Deleting policy versions...")
        # db.query(PolicyVersion).delete()
        # print("   ✓ Deleted policy versions")
        
        # 13. Delete credit rating interest ranges (references cycles)
        # print("15. Deleting credit rating interest ranges...")
        # db.query(CreditRatingInterestRange).delete()
        # print("   ✓ Deleted credit rating interest ranges")
        
        # # 14. Delete cycle phases
        # print("16. Deleting cycle phases...")
        # db.query(CyclePhase).delete()
        # print("   ✓ Deleted cycle phases")
        
        # # 15. Delete cycles (after all references removed)
        # print("17. Deleting cycles...")
        # db.query(Cycle).delete()
        # print("   ✓ Deleted cycles")
        
        # 16. Clean up member-specific ledger accounts (before deleting member profiles)
        print("18. Cleaning up member-specific ledger accounts...")
        # Delete accounts that have member_id set (member-specific accounts)
        member_accounts = db.query(LedgerAccount).filter(LedgerAccount.member_id.isnot(None)).delete()
        print(f"   ✓ Deleted {member_accounts} member-specific ledger accounts")
        print("   ✓ Preserved core organization accounts")
        
        # 17. Delete member status history
        print("19. Deleting member status history...")
        db.query(MemberStatusHistory).delete()
        print("   ✓ Deleted member status history")
        
        # 18. Delete member profiles
        print("20. Deleting member profiles...")
        db.query(MemberProfile).delete()
        print("   ✓ Deleted member profiles")
        
        # 19. Delete committee assignments
        print("21. Deleting committee assignments...")
        db.query(CommitteeAssignment).delete()
        print("   ✓ Deleted committee assignments")
        
        # 20. Delete AI audit logs
        print("22. Deleting AI audit logs...")
        db.query(AIAuditLog).delete()
        print("   ✓ Deleted AI audit logs")
        
        # 21. Delete migration staging data
        print("23. Deleting migration staging data...")
        # db.query(StgCycles).delete()
        db.query(StgPenalties).delete()
        db.query(StgRepayments).delete()
        db.query(StgLoans).delete()
        db.query(StgDeposits).delete()
        db.query(StgMembers).delete()
        db.query(IdMapLoan).delete()
        db.query(IdMapMember).delete()
        db.query(IdMapUser).delete()
        print("   ✓ Deleted migration staging data")
        
        # 22. Update system documents and cycles to reference admin user (before deleting users)
        print("24. Updating system documents and cycles to reference admin user...")
        if admin_user_id:
            # Set constitution document uploaded_by to admin (preserve constitution documents)
            constitution_updates = db.query(ConstitutionDocumentVersion).filter(
                ConstitutionDocumentVersion.uploaded_by != admin_user_id
            ).update({"uploaded_by": admin_user_id}, synchronize_session=False)
            print(f"   ✓ Updated {constitution_updates} constitution documents")
            
            # Set system settings updated_by to NULL (nullable, preserve settings)
            settings_updates = db.query(SystemSettings).filter(
                SystemSettings.updated_by.isnot(None),
                SystemSettings.updated_by != admin_user_id
            ).update({"updated_by": None}, synchronize_session=False)
            print(f"   ✓ Updated {settings_updates} system settings")
            
            # Set cycle created_by to admin (preserve cycles; avoids FK violation when deleting users)
            cycle_updates = db.query(Cycle).filter(
                Cycle.created_by.isnot(None),
                Cycle.created_by != admin_user_id
            ).update({"created_by": admin_user_id}, synchronize_session=False)
            print(f"   ✓ Updated {cycle_updates} cycles (created_by -> admin)")
        else:
            print("   ⚠️  No admin user ID - skipping document updates")
        
        # 23. Delete user roles (except for admin)
        print("25. Deleting user roles (except admin)...")
        if admin_user_id:
            db.query(UserRole).filter(UserRole.user_id != admin_user_id).delete()
        else:
            db.query(UserRole).delete()
        print("   ✓ Deleted user roles")
        
        # 24. Delete non-admin users
        print("26. Deleting non-admin users...")
        if admin_user_id:
            deleted_users = db.query(User).filter(User.id != admin_user_id).delete()
            print(f"   ✓ Deleted {deleted_users} users (admin preserved)")
        else:
            print("   ⚠️  No admin user ID provided - skipping user deletion")
        
        # Commit all deletions
        db.commit()
        
        print()
        print("-" * 60)
        print("✅ DATABASE CLEANUP COMPLETED SUCCESSFULLY")
        print("-" * 60)
        print()
        print("Preserved:")
        print("  ✓ Admin user")
        print("  ✓ All roles")
        print("  ✓ All cycles (and phases, policy versions, credit rating config)")
        print("  ✓ Core ledger accounts (organization-level)")
        print("  ✓ System settings")
        print("  ✓ Policies (interest, credit rating, borrowing limits)")
        print("  ✓ Penalty types")
        print("  ✓ Constitution documents")
        print("  ✓ AI document chunks and embeddings")
        print("  ✓ VB Group")
        print()
        print("Deleted:")
        print("  ✓ All member profiles")
        print("  ✓ All transactions (declarations, deposits, loans, penalties)")
        print("  ✓ All journal entries")
        print("  ✓ All non-admin users")
        print("  ✓ All member-specific ledger accounts")
        print()
        
    except Exception as e:
        db.rollback()
        print()
        print("❌ ERROR during cleanup:")
        print(f"   {str(e)}")
        print()
        print("Database has been rolled back. No changes were made.")
        raise


def main():
    """Main function to run database cleanup."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Clean database, removing user data while preserving system configuration')
    parser.add_argument('--dry-run', action='store_true', help='Run in dry-run mode (show what would be deleted without actually deleting)')
    args = parser.parse_args()
    
    print()
    print("=" * 60)
    print("LUBOSS 95 - Database Cleanup Script")
    print("=" * 60)
    print()
    print("This script will remove all user-entered data while preserving:")
    print("  - Admin user account")
    print("  - All system roles")
    print("  - All cycle data (cycles, phases, policy versions, credit rating config)")
    print("  - System configuration (policies, settings)")
    print("  - Core ledger account structure")
    print("  - System documents (constitution, AI documents)")
    print()
    if args.dry_run:
        print("🔍 DRY RUN MODE - No data will be deleted")
    else:
        print("⚠️  WARNING: This action cannot be undone!")
    print()
    
    db = SessionLocal()
    try:
        clean_database(db, dry_run=args.dry_run)
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
