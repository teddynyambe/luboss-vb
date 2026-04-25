from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Form
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.core.dependencies import require_compliance, require_any_role, get_current_user
from app.models.user import User
from app.models.transaction import PenaltyRecord, PenaltyType, PenaltyRecordStatus
from app.models.member import MemberProfile, MemberStatus
from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID

router = APIRouter(prefix="/api/compliance", tags=["compliance"])


class PenaltyCreate(BaseModel):
    member_id: str
    penalty_type_id: str
    notes: Optional[str] = None


class PenaltyReversalRequest(BaseModel):
    reason: str = Field(min_length=1)


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
        # Validate and convert IDs
        try:
            penalty_type_uuid = UUID(penalty_data.penalty_type_id)
            member_uuid = UUID(penalty_data.member_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid ID format")

        # Verify penalty type exists
        penalty_type = db.query(PenaltyType).filter(PenaltyType.id == penalty_type_uuid).first()
        if not penalty_type:
            raise HTTPException(status_code=404, detail="Penalty type not found")

        # Prevent manual creation of cycle-defined penalties
        if is_cycle_defined_penalty_type(penalty_type.name):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot manually create cycle-defined penalty '{penalty_type.name}'. These penalties are automatically created by the system."
            )

        member = db.query(MemberProfile).filter(MemberProfile.id == member_uuid).first()
        if not member:
            raise HTTPException(status_code=404, detail="Member not found")

        penalty = PenaltyRecord(
            member_id=member_uuid,
            penalty_type_id=penalty_type_uuid,
            status=PenaltyRecordStatus.PENDING.value,  # Use .value to ensure lowercase string is sent
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
        try:
            penalty_type_uuid = UUID(penalty_type_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid penalty type ID format")
        penalty_type = db.query(PenaltyType).filter(PenaltyType.id == penalty_type_uuid).first()
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


# ---------------------------------------------------------------------------
# Penalty Reversal — request (Compliance) then approve (Treasurer)
# ---------------------------------------------------------------------------

def _penalty_detail(p: PenaltyRecord, db: Session) -> dict:
    """Serialize a PenaltyRecord with member/user names for the UI."""
    member = p.member
    user = db.query(User).filter(User.id == member.user_id).first() if member else None
    member_name = f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip() if user else "Unknown"
    requester = db.query(User).filter(User.id == p.reversal_requested_by).first() if p.reversal_requested_by else None
    reverser = db.query(User).filter(User.id == p.reversed_by).first() if p.reversed_by else None
    return {
        "id": str(p.id),
        "member_id": str(p.member_id),
        "member_name": member_name,
        "penalty_type_name": p.penalty_type.name if p.penalty_type else "Unknown",
        "fee_amount": float(p.penalty_type.fee_amount) if p.penalty_type else 0,
        "status": p.status.value if isinstance(p.status, PenaltyRecordStatus) else p.status,
        "date_issued": p.date_issued.isoformat() if p.date_issued else None,
        "notes": p.notes,
        "reversal_reason": p.reversal_reason,
        "reversal_requested_by_name": f"{(requester.first_name or '')} {(requester.last_name or '')}".strip() if requester else None,
        "reversal_requested_at": p.reversal_requested_at.isoformat() if p.reversal_requested_at else None,
        "reversed_by_name": f"{(reverser.first_name or '')} {(reverser.last_name or '')}".strip() if reverser else None,
        "reversed_at": p.reversed_at.isoformat() if p.reversed_at else None,
    }


@router.get("/penalties/approved")
def get_approved_penalties(
    current_user: User = Depends(require_any_role("Compliance", "Admin", "Chairman")),
    db: Session = Depends(get_db),
):
    """Get approved penalties that can be reversed."""
    penalties = db.query(PenaltyRecord).filter(
        PenaltyRecord.status.in_([
            PenaltyRecordStatus.APPROVED.value,
            PenaltyRecordStatus.REVERSAL_PENDING.value,
        ])
    ).order_by(PenaltyRecord.date_issued.desc()).all()
    return [_penalty_detail(p, db) for p in penalties]


@router.put("/penalties/{penalty_id}/request-reversal")
def request_penalty_reversal(
    penalty_id: str,
    body: PenaltyReversalRequest,
    current_user: User = Depends(require_any_role("Compliance", "Admin", "Chairman")),
    db: Session = Depends(get_db),
):
    """Request reversal of an approved penalty. Goes to Treasurer for approval."""
    try:
        pid = UUID(penalty_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid penalty ID")

    penalty = db.query(PenaltyRecord).filter(PenaltyRecord.id == pid).first()
    if not penalty:
        raise HTTPException(status_code=404, detail="Penalty not found")

    status_val = penalty.status.value if isinstance(penalty.status, PenaltyRecordStatus) else penalty.status
    if status_val not in (PenaltyRecordStatus.APPROVED.value,):
        raise HTTPException(
            status_code=400,
            detail=f"Only approved penalties can be reversed. Current status: {status_val}",
        )

    penalty.status = PenaltyRecordStatus.REVERSAL_PENDING
    penalty.reversal_requested_by = current_user.id
    penalty.reversal_requested_at = datetime.utcnow()
    penalty.reversal_reason = body.reason
    db.commit()
    db.refresh(penalty)

    from app.core.audit import write_audit_log
    member = penalty.member
    user = db.query(User).filter(User.id == member.user_id).first() if member else None
    member_name = f"{(user.first_name or '')} {(user.last_name or '')}".strip() if user else "Unknown"
    write_audit_log(
        user_name=f"{current_user.first_name or ''} {current_user.last_name or ''}".strip(),
        user_role="compliance",
        action="Penalty reversal requested",
        details=f"member={member_name}, penalty={penalty.penalty_type.name if penalty.penalty_type else 'Unknown'}, reason={body.reason}",
    )

    return _penalty_detail(penalty, db)
