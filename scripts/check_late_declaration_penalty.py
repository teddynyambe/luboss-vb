#!/usr/bin/env python3
"""Check why late declaration penalties are not being created."""
import sys
import os
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.base import SessionLocal
from app.models.cycle import Cycle, CyclePhase, PhaseType, CycleStatus
from app.models.transaction import PenaltyType, PenaltyRecord
from sqlalchemy import extract

def check_late_declaration_penalty():
    """Check cycle phase configuration for late declaration penalties."""
    db = SessionLocal()
    try:
        print("=== Checking Late Declaration Penalty Configuration ===\n")
        
        # Get active cycle
        active_cycle = db.query(Cycle).filter(Cycle.status == CycleStatus.ACTIVE).first()
        if not active_cycle:
            print("❌ No active cycle found!")
            return
        
        print(f"✅ Active cycle found: {active_cycle.year} (ID: {active_cycle.id})")
        print()
        
        # Get declaration phase
        declaration_phase = db.query(CyclePhase).filter(
            CyclePhase.cycle_id == active_cycle.id,
            CyclePhase.phase_type == PhaseType.DECLARATION
        ).first()
        
        if not declaration_phase:
            print("❌ No declaration phase found for active cycle!")
            return
        
        print("✅ Declaration phase found")
        print(f"   Phase ID: {declaration_phase.id}")
        print()
        
        # Check configuration
        auto_apply = getattr(declaration_phase, 'auto_apply_penalty', None)
        monthly_end_day = getattr(declaration_phase, 'monthly_end_day', None)
        penalty_type_id = getattr(declaration_phase, 'penalty_type_id', None)
        
        print("Configuration:")
        print(f"   auto_apply_penalty: {auto_apply}")
        print(f"   monthly_end_day: {monthly_end_day}")
        print(f"   penalty_type_id: {penalty_type_id}")
        print()
        
        # Check if all required fields are set
        if not auto_apply:
            print("❌ auto_apply_penalty is not enabled!")
            print("   Fix: Set auto_apply_penalty = True in the declaration phase")
        elif not monthly_end_day:
            print("❌ monthly_end_day is not set!")
            print("   Fix: Set monthly_end_day to the day when declarations are due (e.g., 25)")
        elif not penalty_type_id:
            print("❌ penalty_type_id is not set!")
            print("   Fix: Set penalty_type_id to a valid penalty type ID")
        else:
            print("✅ All required fields are set")
            print()
            
            # Check penalty type
            penalty_type = db.query(PenaltyType).filter(PenaltyType.id == penalty_type_id).first()
            if penalty_type:
                print(f"✅ Penalty type found: {penalty_type.name}")
                print(f"   Fee amount: {penalty_type.fee_amount}")
                print(f"   Enabled: {penalty_type.enabled}")
            else:
                print(f"❌ Penalty type with ID {penalty_type_id} not found!")
                return
            
            print()
            
            # Check if today is late
            today = date.today()
            print(f"Today's date: {today}")
            print(f"Monthly end day: {monthly_end_day}")
            print()
            
            # Test with current month
            current_month = date(today.year, today.month, 1)
            is_late = False
            
            if today.year == current_month.year and today.month == current_month.month:
                if today.day > monthly_end_day:
                    is_late = True
                    print(f"✅ Declaration for {current_month.strftime('%B %Y')} IS LATE")
                    print(f"   Today is day {today.day}, end day is {monthly_end_day}")
                else:
                    print(f"❌ Declaration for {current_month.strftime('%B %Y')} is NOT late")
                    print(f"   Today is day {today.day}, end day is {monthly_end_day}")
                    print(f"   Penalty will be created when day > {monthly_end_day}")
            else:
                print(f"⚠️  Current month check: {current_month.strftime('%B %Y')}")
            
            print()
            
            # Check for existing penalties
            print("Checking for existing penalty records...")
            # Get a sample member to test
            from app.models.member import MemberProfile
            sample_member = db.query(MemberProfile).first()
            if sample_member:
                existing_penalties = db.query(PenaltyRecord).filter(
                    PenaltyRecord.member_id == sample_member.id,
                    PenaltyRecord.penalty_type_id == penalty_type_id
                ).all()
                print(f"   Found {len(existing_penalties)} penalty records for sample member")
                for p in existing_penalties[:3]:
                    print(f"     - {p.date_issued.date()}: {p.status.value} - {p.notes[:50] if p.notes else 'No notes'}")
            else:
                print("   No members found to check")
            
            print()
            print("=== Summary ===")
            if auto_apply and monthly_end_day and penalty_type_id:
                if today.day > monthly_end_day:
                    print("✅ Configuration is correct and declaration should be late")
                    print("   Penalties should be created when declarations are submitted")
                else:
                    print(f"⚠️  Configuration is correct, but today (day {today.day}) is not after end day ({monthly_end_day})")
                    print(f"   Penalties will be created when day > {monthly_end_day}")
            else:
                print("❌ Configuration is incomplete - penalties will NOT be created")
                print("   Fix the missing configuration above")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    check_late_declaration_penalty()
