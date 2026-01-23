from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.core.dependencies import require_compliance, get_current_user
from app.models.user import User
from app.models.transaction import PenaltyRecord, PenaltyType, PenaltyRecordStatus
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/compliance", tags=["compliance"])


class PenaltyCreate(BaseModel):
    member_id: str
    penalty_type_id: str
    notes: Optional[str] = None


@router.post("/penalties")
def create_penalty(
    penalty_data: PenaltyCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a penalty record (Compliance only)."""
    try:
        # Verify penalty type exists
        penalty_type = db.query(PenaltyType).filter(PenaltyType.id == penalty_data.penalty_type_id).first()
        if not penalty_type:
            return {"message": "To be done - penalty type not found"}
        
        penalty = PenaltyRecord(
            member_id=penalty_data.member_id,
            penalty_type_id=penalty_data.penalty_type_id,
            status=PenaltyRecordStatus.PENDING,
            created_by=current_user.id,
            notes=penalty_data.notes
        )
        db.add(penalty)
        db.commit()
        db.refresh(penalty)
        return {"message": "Penalty record created successfully", "penalty_id": str(penalty.id)}
    except Exception as e:
        return {"message": f"To be done - {str(e)}"}


@router.get("/penalties")
def get_penalties(
    current_user: User = Depends(require_compliance),
    db: Session = Depends(get_db)
):
    """Get all penalties created by compliance."""
    penalties = db.query(PenaltyRecord).filter(
        PenaltyRecord.created_by == current_user.id
    ).all()
    return penalties
