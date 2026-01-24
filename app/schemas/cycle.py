from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date
from decimal import Decimal


class CycleCreate(BaseModel):
    """Schema for creating a new cycle."""
    year: str = Field(..., description="Cycle year (e.g., '2024')")
    start_date: date = Field(..., description="Cycle start date")
    social_fund_required: Optional[Decimal] = Field(None, ge=0, description="Annual social fund requirement per member")
    admin_fund_required: Optional[Decimal] = Field(None, ge=0, description="Annual admin fund requirement per member")
    # end_date will be calculated as start_date + 1 year


class CyclePhaseConfig(BaseModel):
    """Schema for configuring cycle phase start and end days."""
    phase_type: str = Field(..., description="Phase type: declaration, loan_application, deposits")
    monthly_start_day: int = Field(..., ge=1, le=31, description="Day of month (1-31) when phase starts each month")
    monthly_end_day: Optional[int] = Field(None, ge=1, le=31, description="Day of month (1-31) when phase ends each month")
    penalty_amount: Optional[Decimal] = Field(None, ge=0, description="Optional penalty amount for transactions outside date range (deprecated, use penalty_type_id)")
    penalty_type_id: Optional[str] = Field(None, description="Optional penalty type ID for declaration phase")
    auto_apply_penalty: Optional[bool] = Field(False, description="Whether to automatically apply penalty when declaration is made outside date range")


class InterestRateRangeCreate(BaseModel):
    """Schema for creating an interest rate for a credit tier."""
    term_months: Optional[str] = Field(None, description="Term in months (e.g., '1', '2', '3', '4') or None for all terms")
    effective_rate_percent: Decimal = Field(..., ge=0, le=100, description="Effective interest rate percentage")


class CreditRatingTierCreate(BaseModel):
    """Schema for creating a credit rating tier."""
    tier_name: str = Field(..., description="Tier name (e.g., 'LOW RISK', 'MEDIUM RISK')")
    tier_order: int = Field(..., description="Tier order (lower = better rating)")
    description: Optional[str] = Field(None, description="Tier description")
    multiplier: Decimal = Field(..., description="Borrowing multiplier (e.g., 2.00 for 2× savings)")
    interest_ranges: List[InterestRateRangeCreate] = Field(default_factory=list, description="Interest rate ranges for this tier")


class CreditRatingSchemeCreate(BaseModel):
    """Schema for creating a credit rating scheme with tiers and interest ranges."""
    name: str = Field(..., description="Scheme name")
    description: Optional[str] = Field(None, description="Scheme description")
    tiers: List[CreditRatingTierCreate] = Field(..., description="Credit rating tiers (each with its own interest ranges)")


class CycleConfigRequest(BaseModel):
    """Complete cycle configuration request."""
    cycle: CycleCreate
    phase_configs: List[CyclePhaseConfig] = Field(default_factory=list, description="Monthly phase start day configurations")
    credit_rating_scheme: Optional[CreditRatingSchemeCreate] = Field(None, description="Credit rating scheme for the cycle")


class CycleUpdate(BaseModel):
    """Schema for updating a cycle."""
    year: Optional[str] = Field(None, description="Cycle year")
    start_date: Optional[date] = Field(None, description="Cycle start date")
    status: Optional[str] = Field(None, description="Cycle status: draft, active, closed")
    social_fund_required: Optional[Decimal] = Field(None, ge=0, description="Annual social fund requirement per member")
    admin_fund_required: Optional[Decimal] = Field(None, ge=0, description="Annual admin fund requirement per member")


class CycleUpdateRequest(BaseModel):
    """Complete cycle update request."""
    cycle: CycleUpdate
    phase_configs: Optional[List[CyclePhaseConfig]] = Field(None, description="Monthly phase start day configurations")
    credit_rating_scheme: Optional[CreditRatingSchemeCreate] = Field(None, description="Credit rating scheme for the cycle")


class CycleResponse(BaseModel):
    """Schema for cycle response."""
    id: str
    year: str
    start_date: date
    end_date: date
    status: str
    created_at: str
    
    class Config:
        from_attributes = True


class CyclePhaseResponse(BaseModel):
    """Schema for cycle phase response."""
    id: str
    phase_type: str
    monthly_start_day: Optional[int]
    monthly_end_day: Optional[int]
    penalty_amount: Optional[Decimal]
    penalty_type_id: Optional[str]
    auto_apply_penalty: Optional[bool]
    
    class Config:
        from_attributes = True


class CreditRatingTierResponse(BaseModel):
    """Schema for credit rating tier response."""
    id: str
    tier_name: str
    tier_order: int
    description: Optional[str]
    multiplier: Decimal
    
    class Config:
        from_attributes = True


class InterestRateRangeResponse(BaseModel):
    """Schema for interest rate response."""
    id: str
    term_months: Optional[str]
    effective_rate_percent: Decimal
    
    class Config:
        from_attributes = True
