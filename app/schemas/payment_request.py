"""Pydantic schemas for payment request workflows."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.payment_request import PaymentCategory, PaymentRequestStatus


class PaymentRequestCreate(BaseModel):
    amount: Decimal = Field(gt=0)
    description: str = Field(min_length=1)
    category: PaymentCategory
    beneficiary_name: str = Field(min_length=1)
    beneficiary_member_id: Optional[UUID] = None
    cycle_id: Optional[UUID] = None


class PaymentRequestReject(BaseModel):
    rejection_reason: str = Field(min_length=1)


class PaymentRequestExecute(BaseModel):
    payment_reference: Optional[str] = None


class PaymentRequestResponse(BaseModel):
    id: UUID
    amount: Decimal
    description: str
    category: PaymentCategory
    source_account_code: str
    beneficiary_name: str
    beneficiary_member_id: Optional[UUID] = None
    cycle_id: Optional[UUID] = None
    status: PaymentRequestStatus
    initiated_by: UUID
    initiator_name: Optional[str] = None
    initiated_at: datetime
    approved_by: Optional[UUID] = None
    approver_name: Optional[str] = None
    approved_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    executed_by: Optional[UUID] = None
    executor_name: Optional[str] = None
    executed_at: Optional[datetime] = None
    payment_reference: Optional[str] = None
    journal_entry_id: Optional[UUID] = None

    class Config:
        from_attributes = True
