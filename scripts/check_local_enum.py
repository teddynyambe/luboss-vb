#!/usr/bin/env python3
"""Check enum values in local database."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.base import SessionLocal
from sqlalchemy import text

def check_enum():
    db = SessionLocal()
    try:
        result = db.execute(text("""
            SELECT enumlabel 
            FROM pg_enum 
            WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'penaltyrecordstatus')
            ORDER BY enumsortorder;
        """))
        enum_values = [row[0] for row in result.fetchall()]
        print(f"Local database enum values: {enum_values}")
        
        if enum_values == ['pending', 'approved', 'paid']:
            print("✅ Enum values are lowercase (matches production)")
        elif enum_values == ['PENDING', 'APPROVED', 'PAID']:
            print("⚠️  Enum values are UPPERCASE (doesn't match production)")
            print("   You need to update the query or fix the enum")
        else:
            print(f"⚠️  Enum values are: {enum_values}")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_enum()
