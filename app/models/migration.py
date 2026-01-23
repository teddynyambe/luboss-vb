from sqlalchemy import Column, String, ForeignKey, DateTime, Numeric, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from app.db.base import Base
from decimal import Decimal


class IdMapUser(Base):
    """ID mapping: old user ID to new user ID."""
    __tablename__ = "id_map_user"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    old_user_id = Column(String(36), nullable=False, unique=True, index=True)  # Old MySQL char(36)
    new_user_id = Column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False, unique=True, index=True)


class IdMapMember(Base):
    """ID mapping: old member ID to new member_profile ID."""
    __tablename__ = "id_map_member"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    old_member_id = Column(String(36), nullable=False, unique=True, index=True)
    new_member_profile_id = Column(UUID(as_uuid=True), ForeignKey("member_profile.id"), nullable=False, unique=True, index=True)


class IdMapLoan(Base):
    """ID mapping: old loan ID to new loan ID."""
    __tablename__ = "id_map_loan"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    old_loan_id = Column(String(36), nullable=False, unique=True, index=True)
    new_loan_id = Column(UUID(as_uuid=True), ForeignKey("loan.id"), nullable=False, unique=True, index=True)


# Staging tables for migration
class StgMembers(Base):
    """Staging table for members from old system."""
    __tablename__ = "stg_members"
    
    id = Column(String(36), primary_key=True)  # Old ID
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    email = Column(String(255), nullable=True)
    # Add other fields as needed for transformation


class StgDeposits(Base):
    """Staging table for deposits from old system."""
    __tablename__ = "stg_deposits"
    
    id = Column(String(36), primary_key=True)
    member_id = Column(String(36), nullable=False)
    amount = Column(Numeric(10, 2), nullable=True)
    transaction_date = Column(DateTime, nullable=True)
    # Add other fields as needed


class StgLoans(Base):
    """Staging table for loans from old system."""
    __tablename__ = "stg_loans"
    
    id = Column(String(36), primary_key=True)
    member_id = Column(String(36), nullable=False)
    loan_amount = Column(Numeric(10, 2), nullable=True)
    percentage_interest = Column(Numeric(5, 2), nullable=True)
    application_date = Column(DateTime, nullable=True)
    effective_month = Column(Date, nullable=True)
    loan_status = Column(String(50), nullable=True)
    # Add other fields as needed


class StgRepayments(Base):
    """Staging table for repayments from old system."""
    __tablename__ = "stg_repayments"
    
    id = Column(String(36), primary_key=True)
    loan_id = Column(String(36), nullable=False)
    member_id = Column(String(36), nullable=False)
    amount = Column(Numeric(10, 2), nullable=True)
    transaction_date = Column(DateTime, nullable=True)
    # Add other fields as needed


class StgPenalties(Base):
    """Staging table for penalties from old system."""
    __tablename__ = "stg_penalties"
    
    id = Column(String(36), primary_key=True)
    member_id = Column(String(36), nullable=False)
    penalty_type_id = Column(String(36), nullable=False)
    date_issued = Column(DateTime, nullable=True)
    approved = Column(String(10), nullable=True)  # "1" or "0"
    # Add other fields as needed


class StgCycles(Base):
    """Staging table for cycles from old system."""
    __tablename__ = "stg_cycles"
    
    id = Column(String(36), primary_key=True)
    year = Column(String(10), nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    # Add other fields as needed
