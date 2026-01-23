from sqlalchemy import Column, String, ForeignKey, DateTime, Numeric, Integer, Text, Date
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid
from app.db.base import Base
from decimal import Decimal


class CreditRatingScheme(Base):
    """Credit rating scheme definition."""
    __tablename__ = "credit_rating_scheme"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, unique=True, index=True)
    effective_from = Column(Date, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default="now()")
    
    # Relationships
    tiers = relationship("CreditRatingTier", back_populates="scheme", order_by="CreditRatingTier.tier_order")
    member_ratings = relationship("MemberCreditRating", back_populates="scheme")


class CreditRatingTier(Base):
    """Credit rating tier within a scheme."""
    __tablename__ = "credit_rating_tier"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scheme_id = Column(UUID(as_uuid=True), ForeignKey("credit_rating_scheme.id"), nullable=False, index=True)
    tier_name = Column(String(50), nullable=False)
    tier_order = Column(Integer, nullable=False)  # Lower = better rating
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default="now()")
    
    # Relationships
    scheme = relationship("CreditRatingScheme", back_populates="tiers")
    member_ratings = relationship("MemberCreditRating", back_populates="tier")
    borrowing_limits = relationship("BorrowingLimitPolicy", back_populates="tier")


class MemberCreditRating(Base):
    """Member credit rating assignment per cycle."""
    __tablename__ = "member_credit_rating"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id = Column(UUID(as_uuid=True), ForeignKey("member_profile.id"), nullable=False, index=True)
    cycle_id = Column(UUID(as_uuid=True), ForeignKey("cycle.id"), nullable=False, index=True)
    tier_id = Column(UUID(as_uuid=True), ForeignKey("credit_rating_tier.id"), nullable=False, index=True)
    scheme_id = Column(UUID(as_uuid=True), ForeignKey("credit_rating_scheme.id"), nullable=False, index=True)
    assigned_by = Column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    assigned_at = Column(DateTime, nullable=False, server_default="now()")
    notes = Column(Text, nullable=True)
    
    # Relationships
    member = relationship("MemberProfile", back_populates="credit_ratings")
    cycle = relationship("Cycle", back_populates="member_credit_ratings")
    tier = relationship("CreditRatingTier", back_populates="member_ratings")
    scheme = relationship("CreditRatingScheme", back_populates="member_ratings")


class InterestPolicy(Base):
    """Base interest rate policy by term."""
    __tablename__ = "interest_policy"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    term_months = Column(String(10), nullable=False)  # "1", "2", "3", "4"
    base_rate_percent = Column(Numeric(5, 2), nullable=False)  # e.g., 10.00 for 10%
    effective_from = Column(Date, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default="now()")


class InterestThresholdPolicy(Base):
    """Interest threshold reduction policy."""
    __tablename__ = "interest_threshold_policy"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    threshold_amount = Column(Numeric(10, 2), nullable=False)  # e.g., 25000.00 for K25,000
    reduction_percent = Column(Numeric(5, 2), nullable=False)  # Reduction percentage
    applies_from_borrow_count = Column(Integer, nullable=False)  # e.g., 3 for "from 3rd borrow"
    effective_from = Column(Date, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default="now()")


class BorrowingLimitPolicy(Base):
    """Borrowing limit policy by credit tier."""
    __tablename__ = "borrowing_limit_policy"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tier_id = Column(UUID(as_uuid=True), ForeignKey("credit_rating_tier.id"), nullable=False, index=True)
    multiplier = Column(Numeric(5, 2), nullable=False)  # e.g., 2.00 for 2× savings
    max_amount = Column(Numeric(10, 2), nullable=True)  # Optional max cap
    effective_from = Column(Date, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default="now()")
    
    # Relationships
    tier = relationship("CreditRatingTier", back_populates="borrowing_limits")


class CreditRatingInterestRange(Base):
    """Interest rate for a credit rating tier (optionally term-based)."""
    __tablename__ = "credit_rating_interest_range"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tier_id = Column(UUID(as_uuid=True), ForeignKey("credit_rating_tier.id"), nullable=False, index=True)
    cycle_id = Column(UUID(as_uuid=True), ForeignKey("cycle.id"), nullable=False, index=True)
    term_months = Column(String(10), nullable=True)  # Optional: "1", "2", "3", "4" or NULL for all terms
    effective_rate_percent = Column(Numeric(5, 2), nullable=False)  # e.g., 12.00 for 12%
    created_at = Column(DateTime, nullable=False, server_default="now()")
    
    # Relationships
    tier = relationship("CreditRatingTier")
    cycle = relationship("Cycle")


class PolicyVersion(Base):
    """Links policies to cycles."""
    __tablename__ = "policy_version"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id = Column(UUID(as_uuid=True), ForeignKey("cycle.id"), nullable=False, index=True)
    interest_policy_id = Column(UUID(as_uuid=True), ForeignKey("interest_policy.id"), nullable=True)
    interest_threshold_policy_id = Column(UUID(as_uuid=True), ForeignKey("interest_threshold_policy.id"), nullable=True)
    borrowing_limit_policy_id = Column(UUID(as_uuid=True), ForeignKey("borrowing_limit_policy.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default="now()")


class CollateralPolicyVersion(Base):
    """Versioned collateral policy document."""
    __tablename__ = "collateral_policy_version"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_number = Column(String(20), nullable=False)
    policy_text = Column(Text, nullable=False)
    effective_from = Column(Date, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default="now()")
    created_by = Column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    
    # Relationships
    collateral_assets = relationship("CollateralAsset", back_populates="policy_version")


class CollateralAsset(Base):
    """Member collateral asset."""
    __tablename__ = "collateral_asset"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id = Column(UUID(as_uuid=True), ForeignKey("member_profile.id"), nullable=False, index=True)
    asset_type = Column(String(50), nullable=False)  # e.g., "real_estate", "livestock", "vehicle"
    description = Column(Text, nullable=True)
    title_document_path = Column(String(500), nullable=True)
    policy_version_id = Column(UUID(as_uuid=True), ForeignKey("collateral_policy_version.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default="now()")
    
    # Relationships
    member = relationship("MemberProfile", back_populates="collateral_assets")
    policy_version = relationship("CollateralPolicyVersion", back_populates="collateral_assets")
    valuations = relationship("CollateralValuation", back_populates="asset", order_by="CollateralValuation.valued_at.desc()")
    holds = relationship("CollateralHold", back_populates="asset")


class CollateralValuation(Base):
    """Collateral asset valuation."""
    __tablename__ = "collateral_valuation"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("collateral_asset.id"), nullable=False, index=True)
    valuation_amount = Column(Numeric(10, 2), nullable=False)
    valued_by = Column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False)
    valued_at = Column(DateTime, nullable=False, server_default="now()")
    notes = Column(Text, nullable=True)
    
    # Relationships
    asset = relationship("CollateralAsset", back_populates="valuations")


class CollateralHold(Base):
    """Collateral hold (held for a loan)."""
    __tablename__ = "collateral_hold"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_id = Column(UUID(as_uuid=True), ForeignKey("loan.id"), nullable=False, index=True)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("collateral_asset.id"), nullable=False, index=True)
    hold_start = Column(DateTime, nullable=False, server_default="now()")
    hold_end = Column(DateTime, nullable=True)
    release_notes = Column(Text, nullable=True)
    
    # Relationships
    loan = relationship("Loan", back_populates="collateral_holds")
    asset = relationship("CollateralAsset", back_populates="holds")
