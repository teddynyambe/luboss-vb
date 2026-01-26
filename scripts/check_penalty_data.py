#!/usr/bin/env python3
"""Check if penalty_record table has data and show sample records."""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.base import SessionLocal
from app.models.transaction import PenaltyRecord
from sqlalchemy import text

def check_penalty_data():
    """Check penalty_record table data."""
    db = SessionLocal()
    try:
        # Count total records
        count = db.query(PenaltyRecord).count()
        print(f"=== Penalty Record Data Check ===")
        print(f"\nTotal penalty records: {count}")
        
        if count == 0:
            print("\n⚠️  No penalty records found in the database.")
            return
        
        # Show breakdown by status
        print("\n--- Breakdown by Status ---")
        status_counts = db.query(
            PenaltyRecord.status,
            text('COUNT(*)')
        ).group_by(PenaltyRecord.status).all()
        
        for status, count in status_counts:
            print(f"  {status}: {count}")
        
        # Show sample records
        print("\n--- Sample Records (first 5) ---")
        samples = db.query(PenaltyRecord).limit(5).all()
        for i, penalty in enumerate(samples, 1):
            print(f"\n{i}. ID: {penalty.id}")
            print(f"   Member ID: {penalty.member_id}")
            print(f"   Status: {penalty.status} (type: {type(penalty.status).__name__})")
            print(f"   Date Issued: {penalty.date_issued}")
            print(f"   Notes: {penalty.notes[:50] if penalty.notes else 'None'}...")
        
        # Check for any records with invalid status values
        print("\n--- Status Value Check ---")
        all_statuses = db.query(PenaltyRecord.status).distinct().all()
        valid_statuses = ['pending', 'approved', 'paid']
        invalid_found = False
        
        for (status,) in all_statuses:
            status_str = str(status) if hasattr(status, 'value') else status
            if status_str not in valid_statuses:
                print(f"⚠️  Invalid status found: '{status_str}' (not in {valid_statuses})")
                invalid_found = True
        
        if not invalid_found:
            print("✅ All status values are valid (pending, approved, paid)")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    check_penalty_data()
