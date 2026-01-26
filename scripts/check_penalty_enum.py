#!/usr/bin/env python3
"""Check penalty_record table and enum status in the database."""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.base import SessionLocal
from sqlalchemy import text

def check_penalty_enum():
    """Check the penalty_record table and enum values."""
    db = SessionLocal()
    try:
        # Check if table exists
        result = db.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'penalty_record'
            );
        """))
        table_exists = result.scalar()
        print(f"✓ penalty_record table exists: {table_exists}")
        
        if not table_exists:
            print("❌ penalty_record table does not exist!")
            return
        
        # Check enum values
        result = db.execute(text("""
            SELECT enumlabel 
            FROM pg_enum 
            WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'penaltyrecordstatus')
            ORDER BY enumsortorder;
        """))
        enum_values = [row[0] for row in result.fetchall()]
        print(f"✓ Enum values in database: {enum_values}")
        
        # Check table row count
        result = db.execute(text("SELECT COUNT(*) FROM penalty_record;"))
        count = result.scalar()
        print(f"✓ penalty_record row count: {count}")
        
        # Check sample data
        if count > 0:
            result = db.execute(text("""
                SELECT id, status, date_issued 
                FROM penalty_record 
                LIMIT 5;
            """))
            print("\nSample penalty records:")
            for row in result.fetchall():
                print(f"  - ID: {row[0]}, Status: {row[1]}, Date: {row[2]}")
        
        # Check for any records with invalid enum values
        result = db.execute(text("""
            SELECT COUNT(*) 
            FROM penalty_record 
            WHERE status::text NOT IN ('pending', 'approved', 'paid');
        """))
        invalid_count = result.scalar()
        if invalid_count > 0:
            print(f"\n⚠️  Warning: {invalid_count} records with invalid enum values!")
            result = db.execute(text("""
                SELECT DISTINCT status::text 
                FROM penalty_record 
                WHERE status::text NOT IN ('pending', 'approved', 'paid');
            """))
            invalid_values = [row[0] for row in result.fetchall()]
            print(f"   Invalid values: {invalid_values}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    check_penalty_enum()
