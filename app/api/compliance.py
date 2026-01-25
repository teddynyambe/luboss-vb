from fastapi import APIRouter, Depends, HTTPException, Form
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.core.dependencies import require_compliance, require_any_role, get_current_user
from app.models.user import User
from app.models.transaction import PenaltyRecord, PenaltyType, PenaltyRecordStatus
from app.models.member import MemberProfile, MemberStatus
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
    """Create a penalty record (Compliance only).
    
    Only non-cycle-defined penalties can be created manually.
    Cycle-defined penalties (Late Declaration, Late Deposits, Late Loan Application)
    are automatically created by the system with APPROVED status.
    """
    from app.services.transaction import is_cycle_defined_penalty_type
    from uuid import UUID
    
    try:
        # Verify penalty type exists
        penalty_type = db.query(PenaltyType).filter(PenaltyType.id == penalty_data.penalty_type_id).first()
        if not penalty_type:
            raise HTTPException(status_code=404, detail="Penalty type not found")
        
        # Prevent manual creation of cycle-defined penalties
        if is_cycle_defined_penalty_type(penalty_type.name):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot manually create cycle-defined penalty '{penalty_type.name}'. These penalties are automatically created by the system."
            )
        
        # Validate member_id
        try:
            member_uuid = UUID(penalty_data.member_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid member ID format")
        
        member = db.query(MemberProfile).filter(MemberProfile.id == member_uuid).first()
        if not member:
            raise HTTPException(status_code=404, detail="Member not found")
        
        penalty = PenaltyRecord(
            member_id=member_uuid,
            penalty_type_id=penalty_data.penalty_type_id,
            status=PenaltyRecordStatus.PENDING,  # Compliance-created penalties start as PENDING
            created_by=current_user.id,
            notes=penalty_data.notes
        )
        db.add(penalty)
        db.commit()
        db.refresh(penalty)
        return {"message": "Penalty record created successfully", "penalty_id": str(penalty.id)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating penalty: {str(e)}")


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


@router.post("/penalty-types")
def create_penalty_type(
    name: str = Form(...),
    description: str = Form(None),
    fee_amount: float = Form(...),
    current_user: User = Depends(require_any_role("Compliance", "Admin", "Chairman")),
    db: Session = Depends(get_db)
):
    """Create a new penalty type. Accessible by Compliance, Admin, and Chairman."""
    from decimal import Decimal
    
    penalty_type = PenaltyType(
        name=name,
        description=description,
        fee_amount=Decimal(str(fee_amount)),
        enabled="1"
    )
    db.add(penalty_type)
    db.commit()
    db.refresh(penalty_type)
    return {
        "message": "Penalty type created successfully",
        "penalty_type": {
            "id": str(penalty_type.id),
            "name": penalty_type.name,
            "description": penalty_type.description,
            "fee_amount": str(penalty_type.fee_amount)
        }
    }


@router.put("/penalty-types/{penalty_type_id}")
def update_penalty_type(
    penalty_type_id: str,
    name: str = Form(...),
    description: str = Form(None),
    fee_amount: float = Form(...),
    current_user: User = Depends(require_any_role("Compliance", "Admin", "Chairman")),
    db: Session = Depends(get_db)
):
    """Update an existing penalty type. Accessible by Compliance, Admin, and Chairman."""
    from decimal import Decimal
    
    try:
        penalty_type = db.query(PenaltyType).filter(PenaltyType.id == penalty_type_id).first()
        if not penalty_type:
            raise HTTPException(status_code=404, detail="Penalty type not found")
        
        penalty_type.name = name
        penalty_type.description = description
        penalty_type.fee_amount = Decimal(str(fee_amount))
        
        db.commit()
        db.refresh(penalty_type)
        return {
            "message": "Penalty type updated successfully",
            "penalty_type": {
                "id": str(penalty_type.id),
                "name": penalty_type.name,
                "description": penalty_type.description,
                "fee_amount": str(penalty_type.fee_amount)
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating penalty type: {str(e)}")


@router.get("/penalty-types")
def get_penalty_types(
    current_user: User = Depends(require_any_role("Compliance", "Admin", "Chairman", "Treasurer")),
    db: Session = Depends(get_db)
):
    """Get all penalty types. Accessible by Compliance, Admin, Chairman, and Treasurer."""
    try:
        penalty_types = db.query(PenaltyType).filter(PenaltyType.enabled == "1").order_by(PenaltyType.name).all()
        if not penalty_types:
            return []
        return [{
            "id": str(pt.id),
            "name": pt.name,
            "description": pt.description,
            "fee_amount": str(pt.fee_amount)
        } for pt in penalty_types]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading penalty types: {str(e)}")


@router.get("/members")
def get_members_for_penalty(
    current_user: User = Depends(require_any_role("Compliance", "Admin", "Chairman")),
    db: Session = Depends(get_db)
):
    """Get list of active members for penalty assignment. Accessible by Compliance, Admin, and Chairman."""
    try:
        members = db.query(MemberProfile).filter(
            MemberProfile.status == MemberStatus.ACTIVE
        ).order_by(MemberProfile.created_at.desc()).all()
        
        if not members:
            return []
        
        result = []
        for member in members:
            user = db.query(User).filter(User.id == member.user_id).first()
            result.append({
                "id": str(member.id),
                "user_id": str(member.user_id),
                "status": member.status.value,
                "user": {
                    "email": user.email if user else None,
                    "first_name": user.first_name if user else None,
                    "last_name": user.last_name if user else None,
                } if user else None
            })
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading members: {str(e)}")
