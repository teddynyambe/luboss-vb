from datetime import datetime
from sqlalchemy.orm import Session
from app.models.member import MemberProfile, MemberStatus, MemberStatusHistory
from app.models.user import User
from uuid import UUID
from typing import Optional


def activate_member(
    db: Session,
    member_profile_id: UUID,
    activated_by: UUID
) -> MemberProfile:
    """Activate a member (change status from PENDING to ACTIVE)."""
    member = db.query(MemberProfile).filter(MemberProfile.id == member_profile_id).first()
    if not member:
        raise ValueError("Member profile not found")
    
    if member.status == MemberStatus.ACTIVE:
        return member  # Already active
    
    old_status = member.status
    member.status = MemberStatus.ACTIVE
    member.activated_at = datetime.utcnow()
    member.activated_by = activated_by
    
    # Create status history record
    status_history = MemberStatusHistory(
        member_profile_id=member.id,
        old_status=old_status,
        new_status=MemberStatus.ACTIVE,
        changed_by=activated_by
    )
    db.add(status_history)
    
    db.commit()
    db.refresh(member)
    return member


def suspend_member(
    db: Session,
    member_profile_id: UUID,
    suspended_by: UUID,
    reason: str = None
) -> MemberProfile:
    """Suspend a member."""
    member = db.query(MemberProfile).filter(MemberProfile.id == member_profile_id).first()
    if not member:
        raise ValueError("Member profile not found")
    
    old_status = member.status
    member.status = MemberStatus.SUSPENDED
    
    # Create status history record
    status_history = MemberStatusHistory(
        member_profile_id=member.id,
        old_status=old_status,
        new_status=MemberStatus.SUSPENDED,
        changed_by=suspended_by,
        reason=reason
    )
    db.add(status_history)
    
    db.commit()
    db.refresh(member)
    return member


def get_member_profile_by_user_id(
    db: Session,
    user_id: UUID
) -> Optional[MemberProfile]:
    """Get member profile by user ID."""
    return db.query(MemberProfile).filter(MemberProfile.user_id == user_id).first()
