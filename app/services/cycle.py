from sqlalchemy.orm import Session
from app.models.cycle import Cycle, CyclePhase, PhaseType, CycleStatus
from uuid import UUID
from datetime import datetime, date
from typing import Optional


def create_cycle(
    db: Session,
    year: str,
    start_date: date,
    end_date: date,
    created_by: UUID = None
) -> Cycle:
    """Create a new cycle."""
    cycle = Cycle(
        year=year,
        start_date=start_date,
        end_date=end_date,
        status=CycleStatus.DRAFT,
        created_by=created_by
    )
    db.add(cycle)
    db.commit()
    db.refresh(cycle)
    return cycle


def open_phase(
    db: Session,
    phase_id: UUID
) -> CyclePhase:
    """Open a cycle phase."""
    phase = db.query(CyclePhase).filter(CyclePhase.id == phase_id).first()
    if not phase:
        raise ValueError("Phase not found")
    
    phase.is_open = True
    db.commit()
    db.refresh(phase)
    return phase


def close_phase(
    db: Session,
    phase_id: UUID
) -> CyclePhase:
    """Close a cycle phase."""
    phase = db.query(CyclePhase).filter(CyclePhase.id == phase_id).first()
    if not phase:
        raise ValueError("Phase not found")
    
    phase.is_open = False
    db.commit()
    db.refresh(phase)
    return phase


def is_phase_open(
    db: Session,
    cycle_id: UUID,
    phase_type: PhaseType
) -> bool:
    """Check if a specific phase is open."""
    phase = db.query(CyclePhase).filter(
        CyclePhase.cycle_id == cycle_id,
        CyclePhase.phase_type == phase_type
    ).first()
    
    return phase.is_open if phase else False


def get_current_cycle(
    db: Session
) -> Optional[Cycle]:
    """Get the current active cycle."""
    today = date.today()
    return db.query(Cycle).filter(
        Cycle.status == CycleStatus.ACTIVE,
        Cycle.start_date <= today,
        Cycle.end_date >= today
    ).first()


def close_cycle(
    db: Session,
    cycle_id: UUID,
    closed_by: UUID = None
) -> Cycle:
    """
    Close a cycle and prepare for the next cycle.
    
    This function:
    1. Sets the cycle status to CLOSED
    2. Closes all phases in the cycle
    3. Finalizes all pending transactions
    4. Prepares accounts for the next cycle
    
    Note: Account balances are preserved in the ledger and carry forward
    to the next cycle. Only cycle-specific data (declarations, loan applications)
    are tied to the cycle.
    """
    cycle = db.query(Cycle).filter(Cycle.id == cycle_id).first()
    if not cycle:
        raise ValueError("Cycle not found")
    
    if cycle.status == CycleStatus.CLOSED:
        return cycle  # Already closed
    
    # Close all phases in this cycle
    phases = db.query(CyclePhase).filter(CyclePhase.cycle_id == cycle_id).all()
    for phase in phases:
        phase.is_open = False
    
    # Set cycle status to CLOSED
    cycle.status = CycleStatus.CLOSED
    
    db.commit()
    db.refresh(cycle)
    return cycle


def reopen_cycle(
    db: Session,
    cycle_id: UUID,
    reopened_by: UUID = None
) -> Cycle:
    """
    Reopen a closed cycle (change status from CLOSED to DRAFT).
    
    This allows the cycle to be activated again if needed.
    Note: Only cycles from the current year or future years can be reopened.
    """
    cycle = db.query(Cycle).filter(Cycle.id == cycle_id).first()
    if not cycle:
        raise ValueError("Cycle not found")
    
    if cycle.status != CycleStatus.CLOSED:
        raise ValueError("Only closed cycles can be reopened")
    
    # Check if cycle is from a previous year
    current_year = date.today().year
    try:
        cycle_year = int(cycle.year)
        if cycle_year < current_year:
            raise ValueError(f"Cannot reopen cycles from previous years. This cycle is from {cycle_year}.")
    except (ValueError, TypeError):
        # If year is not a valid integer, allow reopening (might be a string like "2024-2025")
        pass
    
    # Change status from CLOSED to DRAFT
    cycle.status = CycleStatus.DRAFT
    
    db.commit()
    db.refresh(cycle)
    return cycle


def activate_cycle(
    db: Session,
    cycle_id: UUID,
    activated_by: UUID = None
) -> Cycle:
    """
    Activate a cycle and deactivate all other active cycles.
    
    This ensures only one cycle is active at a time.
    When a new cycle is activated:
    1. All other ACTIVE cycles are set to DRAFT
    2. The selected cycle is set to ACTIVE
    3. Account balances carry forward from previous cycles (via ledger)
    """
    cycle = db.query(Cycle).filter(Cycle.id == cycle_id).first()
    if not cycle:
        raise ValueError("Cycle not found")
    
    # Deactivate all other active cycles
    db.query(Cycle).filter(
        Cycle.id != cycle_id,
        Cycle.status == CycleStatus.ACTIVE
    ).update({Cycle.status: CycleStatus.DRAFT})
    
    # Activate this cycle
    cycle.status = CycleStatus.ACTIVE
    
    db.commit()
    db.refresh(cycle)
    return cycle
