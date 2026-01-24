from sqlalchemy import Column, String, ForeignKey, DateTime, Date, Enum as SQLEnum, Boolean, UniqueConstraint, Integer, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from app.db.base import Base
import enum
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.transaction import PenaltyType


class CycleStatus(str, enum.Enum):
    """Cycle status."""
    DRAFT = "draft"
    ACTIVE = "active"
    CLOSED = "closed"


class PhaseType(str, enum.Enum):
    """Cycle phase types."""
    DECLARATION = "declaration"
    LOAN_APPLICATION = "loan_application"
    DEPOSITS = "deposits"
    PAYOUT = "payout"
    SHAREOUT = "shareout"


class Cycle(Base):
    """Financial cycle (typically annual)."""
    __tablename__ = "cycle"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    year = Column(String(10), nullable=False, unique=True, index=True)  # e.g., "2024"
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(SQLEnum(CycleStatus), default=CycleStatus.DRAFT, nullable=False)
    social_fund_required = Column(Numeric(10, 2), nullable=True)  # Annual social fund requirement per member
    admin_fund_required = Column(Numeric(10, 2), nullable=True)  # Annual admin fund requirement per member
    created_at = Column(DateTime, nullable=False, server_default="now()")
    created_by = Column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    
    # Relationships
    phases = relationship("CyclePhase", back_populates="cycle", order_by="CyclePhase.phase_order")
    journal_entries = relationship("JournalEntry", backref="cycle")
    declarations = relationship("Declaration", back_populates="cycle")
    loan_applications = relationship("LoanApplication", back_populates="cycle")
    loans = relationship("Loan", back_populates="cycle")
    member_credit_ratings = relationship("MemberCreditRating", back_populates="cycle")


class CyclePhase(Base):
    """Cycle phase configuration."""
    __tablename__ = "cycle_phase"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id = Column(UUID(as_uuid=True), ForeignKey("cycle.id"), nullable=False, index=True)
    phase_type = Column(SQLEnum(PhaseType), nullable=False)
    phase_order = Column(String(10), nullable=False)  # Order within cycle
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    is_open = Column(Boolean, default=False, nullable=False)
    monthly_start_day = Column(Integer, nullable=True)  # Day of month (1-31) for monthly recurring phases
    monthly_end_day = Column(Integer, nullable=True)  # Day of month (1-31) for monthly recurring phases end
    penalty_amount = Column(Numeric(10, 2), nullable=True)  # Optional penalty for transactions outside date range (deprecated, use penalty_type_id)
    penalty_type_id = Column(UUID(as_uuid=True), ForeignKey("penalty_type.id"), nullable=True)  # Optional penalty type for declaration phase
    auto_apply_penalty = Column(Boolean, default=False, nullable=False)  # Whether to automatically apply penalty when declaration is made outside date range
    created_at = Column(DateTime, nullable=False, server_default="now()")
    
    # Relationships
    cycle = relationship("Cycle", back_populates="phases")
    penalty_type = relationship("PenaltyType", foreign_keys=[penalty_type_id])
    
    # Unique constraint: one phase type per cycle
    __table_args__ = (
        UniqueConstraint("cycle_id", "phase_type", name="uq_cycle_phase_type"),
    )
