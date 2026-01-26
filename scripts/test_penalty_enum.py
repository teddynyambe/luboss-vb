#!/usr/bin/env python3
"""Test script to verify PenaltyRecordStatus enum values."""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.transaction import PenaltyRecordStatus

print("=== Testing PenaltyRecordStatus Enum ===")
print()

# Test enum values
print("1. Enum Values:")
print(f"   PENDING.name = {PenaltyRecordStatus.PENDING.name}")
print(f"   PENDING.value = {PenaltyRecordStatus.PENDING.value}")
print(f"   APPROVED.name = {PenaltyRecordStatus.APPROVED.name}")
print(f"   APPROVED.value = {PenaltyRecordStatus.APPROVED.value}")
print(f"   PAID.name = {PenaltyRecordStatus.PAID.name}")
print(f"   PAID.value = {PenaltyRecordStatus.PAID.value}")
print()

# Test string conversion
print("2. String Conversion:")
print(f"   str(PenaltyRecordStatus.PAID) = {str(PenaltyRecordStatus.PAID)}")
print(f"   repr(PenaltyRecordStatus.PAID) = {repr(PenaltyRecordStatus.PAID)}")
print()

# Test SQLAlchemy enum usage
print("3. SQLAlchemy Enum Test:")
try:
    from sqlalchemy import Column, Enum as SQLEnum
    from sqlalchemy.dialects.postgresql import UUID
    from app.db.base import Base
    
    # This is how it's defined in the model
    test_col = Column(SQLEnum(PenaltyRecordStatus), default=PenaltyRecordStatus.PENDING)
    print(f"   Column type: {test_col.type}")
    print(f"   Column default: {test_col.default}")
    print(f"   Default value: {test_col.default.arg.value if hasattr(test_col.default, 'arg') else test_col.default.arg}")
    print()
    
    # Test what SQLAlchemy would send
    print("4. What SQLAlchemy would send to database:")
    print(f"   PenaltyRecordStatus.PAID = {PenaltyRecordStatus.PAID}")
    print(f"   PenaltyRecordStatus.PAID.value = {PenaltyRecordStatus.PAID.value}")
    print(f"   Should be: 'paid' (lowercase)")
    print()
    
    if PenaltyRecordStatus.PAID.value == "paid":
        print("✅ Enum value is correct (lowercase 'paid')")
    else:
        print(f"❌ Enum value is wrong: {PenaltyRecordStatus.PAID.value} (expected 'paid')")
        
except Exception as e:
    print(f"❌ Error testing SQLAlchemy: {e}")
    import traceback
    traceback.print_exc()
