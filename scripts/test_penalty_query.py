#!/usr/bin/env python3
"""Test the penalty query to verify enum fix works even with empty table."""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.base import SessionLocal
from app.models.transaction import PenaltyRecord, PenaltyRecordStatus
from app.models.member import MemberProfile
from sqlalchemy import text

def test_penalty_query():
    """Test the penalty query that was failing."""
    db = SessionLocal()
    try:
        print("=== Testing Penalty Query ===")
        print()
        
        # Get any member (for testing)
        member = db.query(MemberProfile).first()
        if not member:
            print("⚠️  No members found in database. Cannot test query.")
            return
        
        print(f"Testing with member ID: {member.id}")
        print()
        
        # Test the query that was failing
        print("1. Testing query with text() approach (current fix):")
        try:
            penalty_records = db.query(PenaltyRecord).filter(
                PenaltyRecord.member_id == member.id,
                text("penalty_record.status IN ('pending', 'approved')")
            ).order_by(PenaltyRecord.date_issued.desc()).all()
            print(f"   ✅ Query succeeded! Found {len(penalty_records)} records")
        except Exception as e:
            print(f"   ❌ Query failed: {e}")
        
        print()
        print("2. Testing enum values:")
        print(f"   PenaltyRecordStatus.PENDING.value = {PenaltyRecordStatus.PENDING.value}")
        print(f"   PenaltyRecordStatus.APPROVED.value = {PenaltyRecordStatus.APPROVED.value}")
        print(f"   PenaltyRecordStatus.PAID.value = {PenaltyRecordStatus.PAID.value}")
        
        print()
        print("3. Testing database enum values:")
        result = db.execute(text("""
            SELECT enumlabel 
            FROM pg_enum 
            WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'penaltyrecordstatus')
            ORDER BY enumsortorder;
        """))
        db_enums = [row[0] for row in result.fetchall()]
        print(f"   Database enum values: {db_enums}")
        
        if db_enums == ['pending', 'approved', 'paid']:
            print("   ✅ Database enum values match Python enum values")
        else:
            print("   ⚠️  Database enum values don't match Python enum values")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_penalty_query()
