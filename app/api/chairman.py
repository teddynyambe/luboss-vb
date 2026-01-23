from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.core.dependencies import require_any_role
from app.core.config import CONSTITUTION_UPLOADS_DIR
from app.models.user import User, UserRoleEnum
from app.models.member import MemberProfile, MemberStatus
from app.models.system import ConstitutionDocumentVersion
from app.models.ai import DocumentChunk, DocumentEmbedding
from app.services.member import activate_member
from app.schemas.member import MemberActivateRequest
from app.schemas.cycle import (
    CycleCreate, CycleConfigRequest, CycleResponse, CyclePhaseResponse,
    CreditRatingTierResponse, InterestRateRangeResponse, CycleUpdateRequest
)
from pydantic import BaseModel
from typing import List, Optional
from datetime import date, timedelta, datetime
from decimal import Decimal
from uuid import UUID
from pathlib import Path
import os

router = APIRouter(prefix="/api/chairman", tags=["chairman"])


# User Management Models
class UserRoleUpdate(BaseModel):
    role: str


class UserListItem(BaseModel):
    id: str
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: str
    approved: Optional[bool] = None
    
    class Config:
        from_attributes = True


@router.get("/members")
def get_all_members(
    status: Optional[str] = None,
    current_user: User = Depends(require_any_role("Chairman", "Vice-Chairman", "Admin")),
    db: Session = Depends(get_db)
):
    """Get list of all members, optionally filtered by status (pending, active, suspended)."""
    try:
        query = db.query(MemberProfile)
        
        # Filter by status if provided
        if status:
            try:
                status_enum = MemberStatus(status.lower())
                query = query.filter(MemberProfile.status == status_enum)
            except ValueError:
                # Invalid status, return all
                pass
        
        members = query.order_by(MemberProfile.created_at.desc()).all()
        
        if not members:
            return []
        
        # Format response with user data
        result = []
        for member in members:
            user = db.query(User).filter(User.id == member.user_id).first()
            result.append({
                "id": str(member.id),
                "user_id": str(member.user_id),
                "status": member.status.value,
                "created_at": member.created_at.isoformat() if member.created_at else None,
                "activated_at": member.activated_at.isoformat() if member.activated_at else None,
                "user": {
                    "email": user.email if user else None,
                    "first_name": user.first_name if user else None,
                    "last_name": user.last_name if user else None,
                } if user else None
            })
        return result
    except Exception as e:
        return {"message": f"To be done - {str(e)}"}


@router.get("/pending-members")
def get_pending_members(
    current_user: User = Depends(require_any_role("Chairman", "Vice-Chairman", "Admin")),
    db: Session = Depends(get_db)
):
    """Get list of pending members awaiting approval (deprecated - use /members?status=pending)."""
    return get_all_members(status="pending", current_user=current_user, db=db)


@router.post("/members/{member_id}/approve")
def approve_member(
    member_id: str,
    current_user: User = Depends(require_any_role("Chairman", "Vice-Chairman", "Admin")),
    db: Session = Depends(get_db)
):
    """Approve a pending member (activate)."""
    try:
        member = activate_member(db, UUID(member_id), current_user.id)
        # activate_member already commits, so no need to commit again
        return {"message": "Member approved successfully", "member_id": str(member.id)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to approve member: {str(e)}")


@router.post("/members/{member_id}/suspend")
def suspend_member(
    member_id: str,
    current_user: User = Depends(require_any_role("Chairman", "Vice-Chairman", "Admin")),
    db: Session = Depends(get_db)
):
    """Suspend a member (disable login)."""
    from app.services.member import suspend_member as suspend_member_service
    try:
        member = suspend_member_service(db, UUID(member_id), current_user.id)
        return {"message": "Member suspended successfully", "member_id": str(member.id)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to suspend member: {str(e)}")


@router.post("/members/{member_id}/activate")
def reactivate_member(
    member_id: str,
    current_user: User = Depends(require_any_role("Chairman", "Vice-Chairman", "Admin")),
    db: Session = Depends(get_db)
):
    """Reactivate a suspended member."""
    try:
        member = activate_member(db, UUID(member_id), current_user.id)
        # activate_member already commits, so no need to commit again
        return {"message": "Member reactivated successfully", "member_id": str(member.id)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reactivate member: {str(e)}")


@router.post("/committee/assign")
def assign_committee_role(
    user_id: str,
    role_name: str,
    current_user: User = Depends(require_any_role("Chairman", "Vice-Chairman")),
    db: Session = Depends(get_db)
):
    """Assign a committee role to a user."""
    from app.services.rbac import assign_role
    user_role = assign_role(db, user_id, role_name, current_user.id)
    return {"message": "Role assigned successfully", "user_role": user_role}


@router.get("/constitution")
def get_constitution(
    current_user: User = Depends(require_any_role("Chairman", "Vice-Chairman", "Admin")),
    db: Session = Depends(get_db)
):
    """Get current active constitution version (if any)."""
    current = (
        db.query(ConstitutionDocumentVersion)
        .filter(ConstitutionDocumentVersion.is_active == "1")
        .order_by(ConstitutionDocumentVersion.uploaded_at.desc())
        .first()
    )
    if not current:
        return {"current": None}
    return {
        "current": {
            "id": str(current.id),
            "version_number": current.version_number,
            "uploaded_at": current.uploaded_at.isoformat(),
            "description": current.description,
        }
    }


def _delete_old_constitution_data(db: Session) -> List[str]:
    """Deactivate old versions, delete old RAG chunks, remove old files. Returns list of deleted file paths."""
    deleted_paths: List[str] = []
    # Deactivate all existing constitution versions
    old_versions = (
        db.query(ConstitutionDocumentVersion)
        .filter(ConstitutionDocumentVersion.is_active == "1")
        .all()
    )
    for v in old_versions:
        v.is_active = "0"
        if v.document_path and os.path.isfile(v.document_path):
            deleted_paths.append(v.document_path)

    # Delete RAG data for constitution (embeddings first, then chunks)
    chunks = db.query(DocumentChunk).filter(DocumentChunk.document_name == "constitution").all()
    chunk_ids = [c.id for c in chunks]
    if chunk_ids:
        db.query(DocumentEmbedding).filter(DocumentEmbedding.chunk_id.in_(chunk_ids)).delete(
            synchronize_session=False
        )
        db.query(DocumentChunk).filter(DocumentChunk.document_name == "constitution").delete()

    db.commit()

    for p in deleted_paths:
        try:
            os.remove(p)
        except OSError:
            pass
    return deleted_paths


@router.post("/constitution/upload")
def upload_constitution(
    file: UploadFile = File(...),
    version_number: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    current_user: User = Depends(require_any_role("Chairman", "Vice-Chairman")),
    db: Session = Depends(get_db)
):
    """Upload or replace constitution PDF. Old version is deactivated, file removed, RAG refreshed."""
    from app.ai.ingestion import ingest_document

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are accepted",
        )

    version = version_number or datetime.utcnow().strftime("%Y%m%d")
    safe_name = "".join(c for c in file.filename if c.isalnum() or c in "._- ") or "constitution"
    CONSTITUTION_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    file_path = CONSTITUTION_UPLOADS_DIR / f"constitution_{version}_{ts}_{safe_name}"

    # Replace old: deactivate, delete RAG, remove old files
    _delete_old_constitution_data(db)

    # Save new file
    content = file.file.read()
    with open(file_path, "wb") as f:
        f.write(content)
    file_path_str = str(file_path)

    # Create new version record
    doc_version = ConstitutionDocumentVersion(
        version_number=version,
        document_path=file_path_str,
        uploaded_by=current_user.id,
        description=description or None,
        is_active="1",
    )
    db.add(doc_version)
    db.commit()
    db.refresh(doc_version)

    # Ingest into RAG for AI chat
    try:
        ingest_document(db, "constitution", version, file_path_str)
    except Exception as e:
        # Rollback version and remove file so user can retry
        db.delete(doc_version)
        db.commit()
        try:
            os.remove(file_path_str)
        except OSError:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Constitution saved but RAG ingestion failed: {str(e)}. Please retry.",
        ) from e

    return {
        "message": "Constitution uploaded successfully",
        "version_id": str(doc_version.id),
        "version_number": version,
    }


@router.get("/cycles/{cycle_id}/phases")
def get_cycle_phases(
    cycle_id: str,
    current_user: User = Depends(require_any_role("Chairman", "Vice-Chairman")),
    db: Session = Depends(get_db)
):
    """Get cycle phases configuration."""
    from app.models.cycle import CyclePhase
    phases = db.query(CyclePhase).filter(CyclePhase.cycle_id == cycle_id).all()
    return phases


@router.post("/cycles/{cycle_id}/phases/{phase_id}/open")
def open_phase(
    cycle_id: str,
    phase_id: str,
    current_user: User = Depends(require_any_role("Chairman", "Vice-Chairman")),
    db: Session = Depends(get_db)
):
    """Open a cycle phase."""
    from app.services.cycle import open_phase
    phase = open_phase(db, phase_id)
    return {"message": "Phase opened successfully", "phase": phase}


@router.post("/cycles/{cycle_id}/phases/{phase_id}/close")
def close_phase(
    cycle_id: str,
    phase_id: str,
    current_user: User = Depends(require_any_role("Chairman", "Vice-Chairman")),
    db: Session = Depends(get_db)
):
    """Close a cycle phase."""
    from app.services.cycle import close_phase
    phase = close_phase(db, phase_id)
    return {"message": "Phase closed successfully", "phase": phase}


@router.get("/cycles")
def list_cycles(
    current_user: User = Depends(require_any_role("Chairman", "Vice-Chairman")),
    db: Session = Depends(get_db)
):
    """List all cycles."""
    from app.models.cycle import Cycle
    cycles = db.query(Cycle).order_by(Cycle.year.desc()).all()
    return [
        {
            "id": str(c.id),
            "year": c.year,
            "start_date": c.start_date.isoformat(),
            "end_date": c.end_date.isoformat(),
            "status": c.status.value,
            "created_at": c.created_at.isoformat(),
        }
        for c in cycles
    ]


@router.post("/cycles", response_model=CycleResponse)
def create_cycle(
    config: CycleConfigRequest,
    current_user: User = Depends(require_any_role("Chairman", "Vice-Chairman")),
    db: Session = Depends(get_db)
):
    """Create a new cycle with phase configurations and credit rating scheme."""
    from app.models.cycle import Cycle, CyclePhase, PhaseType, CycleStatus
    from app.models.policy import (
        CreditRatingScheme, CreditRatingTier, BorrowingLimitPolicy,
        CreditRatingInterestRange
    )
    from datetime import datetime
    
    # Check if cycle year already exists
    existing = db.query(Cycle).filter(Cycle.year == config.cycle.year).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cycle for year {config.cycle.year} already exists"
        )
    
    # Calculate end_date (1 year from start_date)
    end_date = date(
        config.cycle.start_date.year + 1,
        config.cycle.start_date.month,
        config.cycle.start_date.day
    )
    
    # Create cycle
    cycle = Cycle(
        year=config.cycle.year,
        start_date=config.cycle.start_date,
        end_date=end_date,
        status=CycleStatus.DRAFT,
        social_fund_required=Decimal(str(config.cycle.social_fund_required)) if config.cycle.social_fund_required is not None else None,
        admin_fund_required=Decimal(str(config.cycle.admin_fund_required)) if config.cycle.admin_fund_required is not None else None,
        created_by=current_user.id
    )
    db.add(cycle)
    db.flush()  # Get cycle.id
    
    # Create phase configurations
    phase_order_map = {
        PhaseType.DECLARATION: "1",
        PhaseType.LOAN_APPLICATION: "2",
        PhaseType.DEPOSITS: "3",
    }
    
    for phase_config in config.phase_configs:
        try:
            phase_type = PhaseType(phase_config.phase_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid phase type: {phase_config.phase_type}"
            )
        
        phase = CyclePhase(
            cycle_id=cycle.id,
            phase_type=phase_type,
            phase_order=phase_order_map.get(phase_type, "0"),
            monthly_start_day=phase_config.monthly_start_day,
            is_open=False
        )
        db.add(phase)
    
    # Create credit rating scheme if provided
    if config.credit_rating_scheme:
        scheme = CreditRatingScheme(
            name=config.credit_rating_scheme.name,
            description=config.credit_rating_scheme.description,
            effective_from=config.cycle.start_date
        )
        db.add(scheme)
        db.flush()  # Get scheme.id
        
        # Create tiers with borrowing limits
        for tier_data in config.credit_rating_scheme.tiers:
            tier = CreditRatingTier(
                scheme_id=scheme.id,
                tier_name=tier_data.tier_name,
                tier_order=tier_data.tier_order,
                description=tier_data.description
            )
            db.add(tier)
            db.flush()  # Get tier.id
            
            # Create borrowing limit policy
            borrowing_limit = BorrowingLimitPolicy(
                tier_id=tier.id,
                multiplier=tier_data.multiplier,
                effective_from=config.cycle.start_date
            )
            db.add(borrowing_limit)
            
            # Create interest rates for this tier
            # If no interest_ranges specified, create a default one
            if not tier_data.interest_ranges:
                # Create default rate for all terms
                interest_range = CreditRatingInterestRange(
                    tier_id=tier.id,
                    cycle_id=cycle.id,
                    term_months=None,  # All terms
                    effective_rate_percent=Decimal("12.00")
                )
                db.add(interest_range)
            else:
                # Create rates as specified for this tier
                for range_data in tier_data.interest_ranges:
                    interest_range = CreditRatingInterestRange(
                        tier_id=tier.id,
                        cycle_id=cycle.id,
                        term_months=range_data.term_months,
                        effective_rate_percent=range_data.effective_rate_percent
                    )
                    db.add(interest_range)
    
    db.commit()
    db.refresh(cycle)
    
    return {
        "id": str(cycle.id),
        "year": cycle.year,
        "start_date": cycle.start_date,
        "end_date": cycle.end_date,
        "status": cycle.status.value,
        "created_at": cycle.created_at.isoformat(),
    }


@router.get("/cycles/{cycle_id}")
def get_cycle(
    cycle_id: str,
    current_user: User = Depends(require_any_role("Chairman", "Vice-Chairman")),
    db: Session = Depends(get_db)
):
    """Get cycle details with phases and credit rating scheme."""
    from app.models.cycle import Cycle, CyclePhase
    from app.models.policy import CreditRatingScheme, CreditRatingTier, BorrowingLimitPolicy, CreditRatingInterestRange
    
    try:
        cycle_uuid = UUID(cycle_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid cycle ID format"
        )
    
    cycle = db.query(Cycle).filter(Cycle.id == cycle_uuid).first()
    if not cycle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cycle not found"
        )
    
    # Get phases
    phases = db.query(CyclePhase).filter(CyclePhase.cycle_id == cycle.id).all()
    
    # Get credit rating scheme (if any)
    scheme = db.query(CreditRatingScheme).filter(
        CreditRatingScheme.effective_from <= cycle.end_date
    ).order_by(CreditRatingScheme.effective_from.desc()).first()
    
    result = {
        "id": str(cycle.id),
        "year": cycle.year,
        "start_date": cycle.start_date.isoformat(),
        "end_date": cycle.end_date.isoformat(),
        "status": cycle.status.value,
        "created_at": cycle.created_at.isoformat(),
        "social_fund_required": float(cycle.social_fund_required) if cycle.social_fund_required else None,
        "admin_fund_required": float(cycle.admin_fund_required) if cycle.admin_fund_required else None,
        "phases": [
            {
                "id": str(p.id),
                "phase_type": p.phase_type.value,
                "monthly_start_day": p.monthly_start_day,
            }
            for p in phases
        ],
    }
    
    if scheme:
        tiers = db.query(CreditRatingTier).filter(
            CreditRatingTier.scheme_id == scheme.id
        ).order_by(CreditRatingTier.tier_order).all()
        
        scheme_data = {
            "id": str(scheme.id),
            "name": scheme.name,
            "description": scheme.description,
            "tiers": []
        }
        
        for tier in tiers:
            # Get borrowing limit
            borrowing_limit = db.query(BorrowingLimitPolicy).filter(
                BorrowingLimitPolicy.tier_id == tier.id
            ).order_by(BorrowingLimitPolicy.effective_from.desc()).first()
            
            # Get interest ranges
            interest_ranges = db.query(CreditRatingInterestRange).filter(
                CreditRatingInterestRange.tier_id == tier.id,
                CreditRatingInterestRange.cycle_id == cycle.id
            ).all()
            
            tier_data = {
                "id": str(tier.id),
                "tier_name": tier.tier_name,
                "tier_order": tier.tier_order,
                "description": tier.description,
                "multiplier": float(borrowing_limit.multiplier) if borrowing_limit else None,
                "interest_ranges": [
                    {
                        "id": str(ir.id),
                        "term_months": ir.term_months,
                        "effective_rate_percent": float(ir.effective_rate_percent),
                    }
                    for ir in interest_ranges
                ]
            }
            scheme_data["tiers"].append(tier_data)
        
        result["credit_rating_scheme"] = scheme_data
    
    return result


@router.put("/cycles/{cycle_id}", response_model=CycleResponse)
def update_cycle(
    cycle_id: str,
    config: CycleUpdateRequest,
    current_user: User = Depends(require_any_role("Chairman", "Vice-Chairman")),
    db: Session = Depends(get_db)
):
    """Update an existing cycle."""
    from app.models.cycle import Cycle, CyclePhase, PhaseType, CycleStatus
    from app.models.policy import (
        CreditRatingScheme, CreditRatingTier, BorrowingLimitPolicy,
        CreditRatingInterestRange, MemberCreditRating
    )
    
    try:
        cycle_uuid = UUID(cycle_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid cycle ID format"
        )
    
    cycle = db.query(Cycle).filter(Cycle.id == cycle_uuid).first()
    if not cycle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cycle not found"
        )
    
    # Update cycle basic info
    if config.cycle.year:
        # Check if year already exists for another cycle
        existing = db.query(Cycle).filter(
            Cycle.year == config.cycle.year,
            Cycle.id != cycle_uuid
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cycle for year {config.cycle.year} already exists"
            )
        cycle.year = config.cycle.year
    
    if config.cycle.start_date:
        cycle.start_date = config.cycle.start_date
        # Recalculate end_date
        cycle.end_date = date(
            cycle.start_date.year + 1,
            cycle.start_date.month,
            cycle.start_date.day
        )
    
    if config.cycle.status:
        try:
            new_status = CycleStatus(config.cycle.status.lower())
            cycle.status = new_status
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {config.cycle.status}"
            )
    
    # Update fund requirements if provided
    # Check if field was explicitly set in the request (not just default None)
    cycle_data = config.cycle.model_dump(exclude_unset=True)
    if 'social_fund_required' in cycle_data:
        if cycle_data['social_fund_required'] is not None:
            cycle.social_fund_required = Decimal(str(cycle_data['social_fund_required']))
        else:
            cycle.social_fund_required = None  # Explicitly clear it
    
    if 'admin_fund_required' in cycle_data:
        if cycle_data['admin_fund_required'] is not None:
            cycle.admin_fund_required = Decimal(str(cycle_data['admin_fund_required']))
        else:
            cycle.admin_fund_required = None  # Explicitly clear it
    
    # Update phase configurations if provided
    if config.phase_configs:
        # Delete existing phases
        db.query(CyclePhase).filter(CyclePhase.cycle_id == cycle.id).delete()
        
        # Create new phases
        phase_order_map = {
            PhaseType.DECLARATION: "1",
            PhaseType.LOAN_APPLICATION: "2",
            PhaseType.DEPOSITS: "3",
        }
        
        for phase_config in config.phase_configs:
            try:
                phase_type = PhaseType(phase_config.phase_type)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid phase type: {phase_config.phase_type}"
                )
            
            phase = CyclePhase(
                cycle_id=cycle.id,
                phase_type=phase_type,
                phase_order=phase_order_map.get(phase_type, "0"),
                monthly_start_day=phase_config.monthly_start_day,
                is_open=False
            )
            db.add(phase)
    
    # Update credit rating scheme if provided
    if config.credit_rating_scheme:
        # Find existing scheme linked to this cycle (if any) BEFORE deleting
        existing_interest_range = db.query(CreditRatingInterestRange).filter(
            CreditRatingInterestRange.cycle_id == cycle.id
        ).first()
        
        existing_scheme = None
        if existing_interest_range:
            # Get the tier and then the scheme
            tier = db.query(CreditRatingTier).filter(
                CreditRatingTier.id == existing_interest_range.tier_id
            ).first()
            if tier:
                existing_scheme = db.query(CreditRatingScheme).filter(
                    CreditRatingScheme.id == tier.scheme_id
                ).first()
        
        # Check if a scheme with the same name already exists
        scheme_by_name = db.query(CreditRatingScheme).filter(
            CreditRatingScheme.name == config.credit_rating_scheme.name
        ).first()
        
        if scheme_by_name:
            # Use existing scheme (update description and effective_from)
            scheme = scheme_by_name
            scheme.description = config.credit_rating_scheme.description
            scheme.effective_from = cycle.start_date
            
            # Delete existing interest ranges for this cycle
            db.query(CreditRatingInterestRange).filter(
                CreditRatingInterestRange.cycle_id == cycle.id
            ).delete()
            
            # Delete member credit ratings for this cycle first (to avoid FK constraint when deleting tiers)
            existing_tiers = db.query(CreditRatingTier).filter(
                CreditRatingTier.scheme_id == scheme.id
            ).all()
            
            tier_ids = [t.id for t in existing_tiers] if existing_tiers else []
            if tier_ids:
                # Delete member credit ratings for this cycle and these tiers
                db.query(MemberCreditRating).filter(
                    MemberCreditRating.tier_id.in_(tier_ids),
                    MemberCreditRating.cycle_id == cycle.id
                ).delete(synchronize_session=False)
            
            # Delete existing tiers for this scheme (they will be recreated)
            # First, delete ALL related data for these tiers
            if tier_ids:
                # Delete ALL interest ranges for these tiers (for all cycles, not just this one)
                db.query(CreditRatingInterestRange).filter(
                    CreditRatingInterestRange.tier_id.in_(tier_ids)
                ).delete(synchronize_session=False)
                
                # Delete ALL borrowing limits for these tiers (not just for this cycle's start date)
                db.query(BorrowingLimitPolicy).filter(
                    BorrowingLimitPolicy.tier_id.in_(tier_ids)
                ).delete(synchronize_session=False)
            
            # Delete the tiers for this scheme
            # Note: This will fail if tiers are used by other cycles (via MemberCreditRating)
            # In that case, the error will be caught and reported
            if tier_ids:
                db.query(CreditRatingTier).filter(
                    CreditRatingTier.id.in_(tier_ids)
                ).delete(synchronize_session=False)
        else:
            # Delete existing interest ranges for this cycle (if any)
            db.query(CreditRatingInterestRange).filter(
                CreditRatingInterestRange.cycle_id == cycle.id
            ).delete()
            
            # Create new scheme
            scheme = CreditRatingScheme(
                name=config.credit_rating_scheme.name,
                description=config.credit_rating_scheme.description,
                effective_from=cycle.start_date
            )
            db.add(scheme)
            db.flush()  # Get scheme.id
        
        # Create new tiers with borrowing limits and interest ranges
        for tier_data in config.credit_rating_scheme.tiers:
            tier = CreditRatingTier(
                scheme_id=scheme.id,
                tier_name=tier_data.tier_name,
                tier_order=tier_data.tier_order,
                description=tier_data.description
            )
            db.add(tier)
            db.flush()  # Get tier.id
            
            # Create borrowing limit policy
            borrowing_limit = BorrowingLimitPolicy(
                tier_id=tier.id,
                multiplier=tier_data.multiplier,
                effective_from=cycle.start_date
            )
            db.add(borrowing_limit)
            
            # Create interest rates for this tier
            # If no interest_ranges specified, create a default one
            if not tier_data.interest_ranges:
                # Create default rate for all terms
                interest_range = CreditRatingInterestRange(
                    tier_id=tier.id,
                    cycle_id=cycle.id,
                    term_months=None,  # All terms
                    effective_rate_percent=Decimal("12.00")
                )
                db.add(interest_range)
            else:
                # Create rates as specified for this tier
                for range_data in tier_data.interest_ranges:
                    interest_range = CreditRatingInterestRange(
                        tier_id=tier.id,
                        cycle_id=cycle.id,
                        term_months=range_data.term_months,
                        effective_rate_percent=range_data.effective_rate_percent
                    )
                    db.add(interest_range)
    
    try:
        db.commit()
        db.refresh(cycle)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating cycle: {str(e)}"
        )
    
    return {
        "id": str(cycle.id),
        "year": cycle.year,
        "start_date": cycle.start_date,
        "end_date": cycle.end_date,
        "status": cycle.status.value,
        "created_at": cycle.created_at.isoformat(),
    }


@router.put("/cycles/{cycle_id}/activate")
def activate_cycle_endpoint(
    cycle_id: str,
    current_user: User = Depends(require_any_role("Chairman", "Vice-Chairman")),
    db: Session = Depends(get_db)
):
    """
    Activate a cycle (set status to ACTIVE and deactivate all other cycles).
    
    When a new cycle is activated:
    1. All other ACTIVE cycles are automatically set to DRAFT
    2. The selected cycle becomes ACTIVE
    3. Account balances carry forward from previous cycles via the ledger
    4. Members can now make declarations and apply for loans in the new cycle
    
    Note: Only cycles from the current year or future years can be activated.
    Cycles from previous years cannot be activated.
    """
    from app.services.cycle import activate_cycle
    from app.models.cycle import Cycle
    from datetime import date
    
    try:
        cycle_uuid = UUID(cycle_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid cycle ID format"
        )
    
    # Check if cycle is from a previous year before activating
    cycle = db.query(Cycle).filter(Cycle.id == cycle_uuid).first()
    if not cycle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cycle not found"
        )
    
    current_year = date.today().year
    try:
        cycle_year = int(cycle.year)
        if cycle_year < current_year:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot activate cycles from previous years. This cycle is from {cycle_year}."
            )
    except (ValueError, TypeError):
        # If year is not a valid integer, allow activation (might be a string like "2024-2025")
        pass
    
    try:
        cycle = activate_cycle(db, cycle_uuid, current_user.id)
        return {
            "message": "Cycle activated successfully. All other cycles have been deactivated.",
            "cycle": {
                "id": str(cycle.id),
                "year": cycle.year,
                "status": cycle.status.value
            }
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.put("/cycles/{cycle_id}/close")
def close_cycle_endpoint(
    cycle_id: str,
    current_user: User = Depends(require_any_role("Chairman", "Vice-Chairman")),
    db: Session = Depends(get_db)
):
    """
    Close a cycle at the end of its period.
    
    When a cycle is closed:
    1. Cycle status is set to CLOSED
    2. All phases in the cycle are closed
    3. No new declarations or loan applications can be made for this cycle
    4. Account balances are preserved in the ledger and carry forward
    5. Historical data (declarations, loans) remain tied to this cycle
    
    Note: Account balances are NOT reset - they carry forward to the next cycle
    via the double-entry ledger system. Only cycle-specific activities are closed.
    """
    from app.services.cycle import close_cycle
    
    try:
        cycle_uuid = UUID(cycle_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid cycle ID format"
        )
    
    try:
        cycle = close_cycle(db, cycle_uuid, current_user.id)
        return {
            "message": "Cycle closed successfully. All phases have been closed.",
            "cycle": {
                "id": str(cycle.id),
                "year": cycle.year,
                "status": cycle.status.value
            }
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.put("/cycles/{cycle_id}/reopen")
def reopen_cycle_endpoint(
    cycle_id: str,
    current_user: User = Depends(require_any_role("Chairman", "Vice-Chairman")),
    db: Session = Depends(get_db)
):
    """
    Reopen a closed cycle (change status from CLOSED to DRAFT).
    
    This allows the cycle to be activated again if needed.
    Only cycles from the current year or future years can be reopened.
    Cycles from previous years cannot be reopened.
    """
    from app.services.cycle import reopen_cycle
    
    try:
        cycle_uuid = UUID(cycle_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid cycle ID format"
        )
    
    try:
        cycle = reopen_cycle(db, cycle_uuid, current_user.id)
        return {
            "message": "Cycle reopened successfully. You can now activate it if needed.",
            "cycle": {
                "id": str(cycle.id),
                "year": cycle.year,
                "status": cycle.status.value
            }
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# User Management Endpoints
@router.get("/users", response_model=List[UserListItem])
def list_users(
    current_user: User = Depends(require_any_role("Chairman", "Vice-Chairman", "Admin")),
    db: Session = Depends(get_db)
):
    """List all users (Chairman/Vice-Chairman/Admin only)."""
    users = db.query(User).all()
    return [
        UserListItem(
            id=str(user.id),
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            role=user.role.value if user.role else "member",
            approved=user.approved
        )
        for user in users
    ]


@router.put("/users/{user_id}/approve")
def approve_user(
    user_id: str,
    current_user: User = Depends(require_any_role("Chairman", "Vice-Chairman", "Admin")),
    db: Session = Depends(get_db)
):
    """Approve a user (Chairman/Vice-Chairman/Admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.approved = True
    db.commit()
    db.refresh(user)
    return {
        "message": "User approved successfully",
        "user": {
            "id": str(user.id),
            "email": user.email,
            "approved": user.approved
        }
    }


@router.put("/users/{user_id}/suspend")
def suspend_user(
    user_id: str,
    current_user: User = Depends(require_any_role("Chairman", "Vice-Chairman", "Admin")),
    db: Session = Depends(get_db)
):
    """Suspend/disable a user (Chairman/Vice-Chairman/Admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.approved = False
    db.commit()
    return {"message": "User suspended successfully"}


@router.put("/users/{user_id}/role")
def update_user_role(
    user_id: str,
    role_update: UserRoleUpdate,
    current_user: User = Depends(require_any_role("Chairman", "Vice-Chairman", "Admin")),
    db: Session = Depends(get_db)
):
    """Update a user's role (Chairman/Vice-Chairman/Admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Validate role
    try:
        new_role = UserRoleEnum(role_update.role.lower())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role. Must be one of: {', '.join([r.value for r in UserRoleEnum])}"
        )
    
    user.role = new_role
    db.commit()
    db.refresh(user)
    
    return {
        "message": "User role updated successfully",
        "user": {
            "id": str(user.id),
            "email": user.email,
            "role": user.role.value
        }
    }


@router.get("/credit-rating-tiers/{cycle_id}")
def get_credit_rating_tiers_for_cycle(
    cycle_id: str,
    current_user: User = Depends(require_any_role("Chairman", "Vice-Chairman", "Admin")),
    db: Session = Depends(get_db)
):
    """Get all credit rating tiers for a specific cycle."""
    from app.models.cycle import Cycle, CycleStatus
    from app.models.policy import CreditRatingScheme, CreditRatingTier, BorrowingLimitPolicy, CreditRatingInterestRange
    
    try:
        cycle_uuid = UUID(cycle_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid cycle ID format")
    
    cycle = db.query(Cycle).filter(Cycle.id == cycle_uuid).first()
    if not cycle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cycle not found")
    
    # Find scheme for this cycle
    scheme = db.query(CreditRatingScheme).filter(
        CreditRatingScheme.effective_from <= cycle.end_date
    ).order_by(CreditRatingScheme.effective_from.desc()).first()
    
    if not scheme:
        return []
    
    # Get all tiers for this scheme
    tiers = db.query(CreditRatingTier).filter(
        CreditRatingTier.scheme_id == scheme.id
    ).order_by(CreditRatingTier.tier_order).all()
    
    result = []
    for tier in tiers:
        # Get borrowing limit for this tier
        borrowing_limit = db.query(BorrowingLimitPolicy).filter(
            BorrowingLimitPolicy.tier_id == tier.id,
            BorrowingLimitPolicy.effective_from <= cycle.end_date
        ).order_by(BorrowingLimitPolicy.effective_from.desc()).first()
        
        result.append({
            "id": str(tier.id),
            "tier_name": tier.tier_name,
            "tier_order": tier.tier_order,
            "description": tier.description,
            "multiplier": float(borrowing_limit.multiplier) if borrowing_limit else None
        })
    
    return result


@router.post("/members/{member_id}/credit-rating")
def assign_credit_rating(
    member_id: str,
    tier_id: str = Form(...),
    cycle_id: str = Form(...),
    notes: Optional[str] = Form(None),
    current_user: User = Depends(require_any_role("Chairman", "Vice-Chairman", "Admin")),
    db: Session = Depends(get_db)
):
    """Assign a credit rating tier to a member for a specific cycle. 
    If member_id is actually a user_id and no member profile exists, one will be created automatically."""
    from app.models.policy import MemberCreditRating, CreditRatingTier, CreditRatingScheme
    from app.models.cycle import Cycle
    from app.services.member import get_member_profile_by_user_id
    
    try:
        member_uuid = UUID(member_id)
        tier_uuid = UUID(tier_id)
        cycle_uuid = UUID(cycle_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ID format")
    
    # Try to find member by member_id first
    member = db.query(MemberProfile).filter(MemberProfile.id == member_uuid).first()
    
    # If not found, try to find by user_id (in case member_id is actually a user_id)
    if not member:
        user = db.query(User).filter(User.id == member_uuid).first()
        if user:
            # Check if user has a member profile
            member = get_member_profile_by_user_id(db, user.id)
            # If still no member profile, create one automatically
            if not member:
                member = MemberProfile(
                    user_id=user.id,
                    status=MemberStatus.ACTIVE,
                    activated_by=current_user.id,
                    activated_at=datetime.utcnow()
                )
                db.add(member)
                db.commit()
                db.refresh(member)
    
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member or user not found")
    
    # Verify tier exists and get scheme
    tier = db.query(CreditRatingTier).filter(CreditRatingTier.id == tier_uuid).first()
    if not tier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credit rating tier not found")
    
    scheme = db.query(CreditRatingScheme).filter(CreditRatingScheme.id == tier.scheme_id).first()
    if not scheme:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credit rating scheme not found")
    
    # Verify cycle exists
    cycle = db.query(Cycle).filter(Cycle.id == cycle_uuid).first()
    if not cycle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cycle not found")
    
    # Check if rating already exists for this member and cycle
    existing_rating = db.query(MemberCreditRating).filter(
        MemberCreditRating.member_id == member_uuid,
        MemberCreditRating.cycle_id == cycle_uuid
    ).first()
    
    if existing_rating:
        # Update existing rating
        existing_rating.tier_id = tier_uuid
        existing_rating.scheme_id = scheme.id
        existing_rating.assigned_by = current_user.id
        existing_rating.assigned_at = datetime.utcnow()
        if notes:
            existing_rating.notes = notes
        db.commit()
        db.refresh(existing_rating)
        return {
            "message": "Credit rating updated successfully",
            "rating_id": str(existing_rating.id)
        }
    else:
        # Create new rating
        rating = MemberCreditRating(
            member_id=member_uuid,
            cycle_id=cycle_uuid,
            tier_id=tier_uuid,
            scheme_id=scheme.id,
            assigned_by=current_user.id,
            notes=notes
        )
        db.add(rating)
        db.commit()
        db.refresh(rating)
        return {
            "message": "Credit rating assigned successfully",
            "rating_id": str(rating.id)
        }


@router.get("/members/{member_id}/credit-rating/{cycle_id}")
def get_member_credit_rating(
    member_id: str,
    cycle_id: str,
    current_user: User = Depends(require_any_role("Chairman", "Vice-Chairman", "Admin")),
    db: Session = Depends(get_db)
):
    """Get a member's credit rating for a specific cycle."""
    from app.models.policy import MemberCreditRating, CreditRatingTier
    
    try:
        member_uuid = UUID(member_id)
        cycle_uuid = UUID(cycle_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ID format")
    
    rating = db.query(MemberCreditRating).filter(
        MemberCreditRating.member_id == member_uuid,
        MemberCreditRating.cycle_id == cycle_uuid
    ).first()
    
    if not rating:
        return None
    
    tier = db.query(CreditRatingTier).filter(CreditRatingTier.id == rating.tier_id).first()
    
    return {
        "id": str(rating.id),
        "tier_id": str(rating.tier_id),
        "tier_name": tier.tier_name if tier else None,
        "tier_order": tier.tier_order if tier else None,
        "notes": rating.notes,
        "assigned_at": rating.assigned_at.isoformat() if rating.assigned_at else None
    }
