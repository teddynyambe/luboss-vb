from datetime import datetime
from sqlalchemy.orm import Session
from app.models.member import MemberProfile, MemberStatus, MemberStatusHistory
from app.models.user import User
from uuid import UUID
from typing import Optional


def toggle_member_status(
    db: Session,
    member_profile_id: UUID,
    changed_by: UUID,
    reason: str = None
) -> MemberProfile:
    """Toggle member status between ACTIVE and INACTIVE."""
    member = db.query(MemberProfile).filter(MemberProfile.id == member_profile_id).first()
    if not member:
        raise ValueError("Member profile not found")
    
    old_status = member.status
    
    # Toggle status
    if member.status == MemberStatus.ACTIVE:
        new_status = MemberStatus.INACTIVE
        # Unapprove the associated user
        user = db.query(User).filter(User.id == member.user_id).first()
        if user:
            user.approved = False
    else:
        new_status = MemberStatus.ACTIVE
        member.activated_at = datetime.utcnow()
        member.activated_by = changed_by
        # Approve the associated user
        user = db.query(User).filter(User.id == member.user_id).first()
        if user:
            user.approved = True
    
    member.status = new_status
    
    # Create status history record
    status_history = MemberStatusHistory(
        member_profile_id=member.id,
        old_status=old_status,
        new_status=new_status,
        changed_by=changed_by,
        reason=reason
    )
    db.add(status_history)
    
    db.commit()
    db.refresh(member)
    return member


def activate_member(
    db: Session,
    member_profile_id: UUID,
    activated_by: UUID
) -> MemberProfile:
    """Activate a member (set status to ACTIVE) and approve the associated user."""
    member = db.query(MemberProfile).filter(MemberProfile.id == member_profile_id).first()
    if not member:
        raise ValueError("Member profile not found")
    
    if member.status == MemberStatus.ACTIVE:
        # Even if already active, ensure user is approved
        user = db.query(User).filter(User.id == member.user_id).first()
        if user and not user.approved:
            user.approved = True
            db.commit()
        return member  # Already active
    
    old_status = member.status
    member.status = MemberStatus.ACTIVE
    member.activated_at = datetime.utcnow()
    member.activated_by = activated_by
    
    # Also approve the associated user
    user = db.query(User).filter(User.id == member.user_id).first()
    if user:
        user.approved = True
    
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
    """Deactivate a member (set status to INACTIVE) and unapprove the associated user."""
    member = db.query(MemberProfile).filter(MemberProfile.id == member_profile_id).first()
    if not member:
        raise ValueError("Member profile not found")
    
    old_status = member.status
    member.status = MemberStatus.INACTIVE
    
    # Also unapprove the associated user
    user = db.query(User).filter(User.id == member.user_id).first()
    if user:
        user.approved = False
    
    # Create status history record
    status_history = MemberStatusHistory(
        member_profile_id=member.id,
        old_status=old_status,
        new_status=MemberStatus.INACTIVE,
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


def sync_user_and_member_status(
    db: Session,
    user_id: UUID
) -> bool:
    """Sync User.approved with MemberProfile.status to fix discrepancies.
    Returns True if a sync was performed, False if already in sync."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return False
    
    member_profile = db.query(MemberProfile).filter(MemberProfile.user_id == user_id).first()
    if not member_profile:
        return False
    
    # Check for discrepancies and sync
    if user.approved and member_profile.status == MemberStatus.INACTIVE:
        # User is approved but member is inactive - activate member
        try:
            activate_member(db, member_profile.id, user_id)  # Use user_id as activated_by
            return True
        except Exception:
            return False
    elif not user.approved and member_profile.status == MemberStatus.ACTIVE:
        # User is not approved but member is active - deactivate member
        try:
            suspend_member(db, member_profile.id, user_id)  # Use user_id as suspended_by
            return True
        except Exception:
            return False
    elif not user.approved and member_profile.status == MemberStatus.INACTIVE:
        # Both are unapproved/inactive - ensure user.approved is False
        if user.approved:
            user.approved = False
            db.commit()
            return True
    
    return False
