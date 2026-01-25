from sqlalchemy import Column, String, ForeignKey, DateTime, Enum as SQLEnum, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from app.db.base import Base
import enum


class MemberStatus(str, enum.Enum):
    """Member status enum."""
    ACTIVE = "active"
    INACTIVE = "inactive"


class MemberProfile(Base):
    """Member profile linked 1:1 to user."""
    __tablename__ = "member_profile"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False, unique=True, index=True)
    status = Column(SQLEnum(MemberStatus), default=MemberStatus.INACTIVE, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default="now()")
    activated_at = Column(DateTime, nullable=True)
    activated_by = Column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    notes = Column(Text, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="member_profile", foreign_keys=[user_id])
    status_history = relationship("MemberStatusHistory", back_populates="member_profile", order_by="desc(MemberStatusHistory.changed_at)")
    declarations = relationship("Declaration", back_populates="member")
    loan_applications = relationship("LoanApplication", back_populates="member")
    loans = relationship("Loan", back_populates="member")
    deposit_proofs = relationship("DepositProof", back_populates="member")
    penalty_records = relationship("PenaltyRecord", back_populates="member")
    credit_ratings = relationship("MemberCreditRating", back_populates="member")
    collateral_assets = relationship("CollateralAsset", back_populates="member")


class MemberStatusHistory(Base):
    """Audit trail for member status changes."""
    __tablename__ = "member_status_history"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_profile_id = Column(UUID(as_uuid=True), ForeignKey("member_profile.id"), nullable=False, index=True)
    old_status = Column(SQLEnum(MemberStatus), nullable=True)
    new_status = Column(SQLEnum(MemberStatus), nullable=False)
    changed_by = Column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    changed_at = Column(DateTime, nullable=False, server_default="now()")
    reason = Column(Text, nullable=True)
    
    # Relationships
    member_profile = relationship("MemberProfile", back_populates="status_history")
