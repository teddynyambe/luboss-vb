from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.core.dependencies import require_any_role, get_current_user
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
    member_id: Optional[str] = None
    member_status: Optional[str] = None
    member_activated_at: Optional[str] = None
    
    class Config:
        from_attributes = True


@router.get("/members")
def get_all_members(
    status: Optional[str] = None,
    current_user: User = Depends(require_any_role("Chairman", "Vice-Chairman", "Treasurer", "Admin")),
    db: Session = Depends(get_db)
):
    """Get list of all members, optionally filtered by status (active, inactive).
    Automatically syncs User.approved with MemberProfile.status to fix discrepancies."""
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
        
        # Format response with user data and auto-sync discrepancies
        from app.services.member import sync_user_and_member_status
        result = []
        for member in members:
            user = db.query(User).filter(User.id == member.user_id).first()
            
            # Auto-sync if there's a discrepancy
            if user:
                sync_user_and_member_status(db, member.user_id)
                # Refresh member to get updated status
                db.refresh(member)
            
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
    """Get list of inactive members (deprecated - use /members?status=inactive)."""
    return get_all_members(status="inactive", current_user=current_user, db=db)


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
    """Deactivate a member (set status to INACTIVE)."""
    from app.services.member import suspend_member as suspend_member_service
    try:
        member = suspend_member_service(db, UUID(member_id), current_user.id)
        return {"message": "Member deactivated successfully", "member_id": str(member.id)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to deactivate member: {str(e)}")


@router.post("/members/{member_id}/activate")
def reactivate_member(
    member_id: str,
    current_user: User = Depends(require_any_role("Chairman", "Vice-Chairman", "Admin")),
    db: Session = Depends(get_db)
):
    """Reactivate an inactive member."""
    try:
        member = activate_member(db, UUID(member_id), current_user.id)
        # activate_member already commits, so no need to commit again
        return {"message": "Member reactivated successfully", "member_id": str(member.id)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reactivate member: {str(e)}")


@router.post("/members/{member_id}/toggle-status")
def toggle_member_status_endpoint(
    member_id: str,
    current_user: User = Depends(require_any_role("Chairman", "Vice-Chairman", "Admin")),
    db: Session = Depends(get_db)
):
    """Toggle member status between Active and In-Active."""
    from app.services.member import toggle_member_status
    try:
        member = toggle_member_status(db, UUID(member_id), current_user.id)
        status_text = "activated" if member.status == MemberStatus.ACTIVE else "deactivated"
        return {
            "message": f"Member {status_text} successfully",
            "member_id": str(member.id),
            "status": member.status.value
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to toggle member status: {str(e)}")


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
    try:
        cycle_uuid = UUID(cycle_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid cycle ID format")
    phases = db.query(CyclePhase).filter(CyclePhase.cycle_id == cycle_uuid).all()
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
    current_user: User = Depends(require_any_role("Chairman", "Vice-Chairman", "Admin")),
    db: Session = Depends(get_db)
):
    """List all cycles."""
    from app.models.cycle import Cycle, CyclePhase
    from sqlalchemy.orm import load_only
    
    try:
        cycles = db.query(Cycle).order_by(Cycle.year.desc()).all()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading cycles: {str(e)}")
    
    result = []
    for c in cycles:
        try:
            # Try to load with all columns first
            phases = db.query(CyclePhase).filter(CyclePhase.cycle_id == c.id).all()
        except Exception:
            # If that fails (columns don't exist), load only existing columns
            try:
                phases = db.query(CyclePhase).options(
                    load_only(
                        CyclePhase.id,
                        CyclePhase.phase_type,
                        CyclePhase.monthly_start_day,
                        CyclePhase.monthly_end_day,
                        CyclePhase.penalty_amount
                    )
                ).filter(CyclePhase.cycle_id == c.id).all()
            except Exception:
                # If even that fails, return empty phases
                phases = []
        
        phase_list = []
        for p in phases:
            phase_dict = {
                "id": str(p.id),
                "phase_type": p.phase_type.value,
                "monthly_start_day": p.monthly_start_day,
                "monthly_end_day": getattr(p, 'monthly_end_day', None),
                "penalty_amount": float(getattr(p, 'penalty_amount', None)) if getattr(p, 'penalty_amount', None) else None,
            }
            # Safely get new fields that might not exist in database yet
            try:
                penalty_type_id = getattr(p, 'penalty_type_id', None)
                phase_dict["penalty_type_id"] = str(penalty_type_id) if penalty_type_id else None
            except Exception:
                phase_dict["penalty_type_id"] = None
            
            try:
                phase_dict["auto_apply_penalty"] = getattr(p, 'auto_apply_penalty', False)
            except Exception:
                phase_dict["auto_apply_penalty"] = None
            
            phase_list.append(phase_dict)
        
        cycle_data = {
            "id": str(c.id),
            "year": c.year,
            "start_date": c.start_date.isoformat(),
            "end_date": c.end_date.isoformat(),
            "status": c.status.value,
            "created_at": c.created_at.isoformat(),
            "phases": phase_list,
        }
        result.append(cycle_data)
    return result


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
        
        phase_kwargs = {
            "cycle_id": cycle.id,
            "phase_type": phase_type,
            "phase_order": phase_order_map.get(phase_type, "0"),
            "monthly_start_day": phase_config.monthly_start_day,
            "monthly_end_day": phase_config.monthly_end_day,
            "penalty_amount": Decimal(str(phase_config.penalty_amount)) if phase_config.penalty_amount is not None else None,
            "is_open": False
        }
        # Only add new fields if they're provided (will fail if columns don't exist - migration needed)
        if phase_config.penalty_type_id:
            try:
                phase_kwargs["penalty_type_id"] = UUID(phase_config.penalty_type_id)
            except Exception:
                pass  # Column might not exist yet
        if phase_config.auto_apply_penalty is not None:
            try:
                phase_kwargs["auto_apply_penalty"] = phase_config.auto_apply_penalty
            except Exception:
                pass  # Column might not exist yet
        
        phase = CyclePhase(**phase_kwargs)
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
    from sqlalchemy import text
    import logging
    
    try:
        cycle_uuid = UUID(cycle_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid cycle ID format"
        )
    
    try:
        cycle = db.query(Cycle).filter(Cycle.id == cycle_uuid).first()
        if not cycle:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cycle not found"
            )
        
        # Get phases - use raw SQL to avoid issues with missing columns
        phases = []
        try:
            # First try using ORM
            phases = db.query(CyclePhase).filter(CyclePhase.cycle_id == cycle.id).all()
        except Exception as e:
            # If ORM fails (likely due to missing columns), use raw SQL
            logging.warning(f"ORM query failed, using raw SQL: {str(e)}")
            try:
                sql = text("""
                    SELECT id, phase_type, monthly_start_day, monthly_end_day, penalty_amount
                    FROM cycle_phase
                    WHERE cycle_id = :cycle_id
                """)
                rows = db.execute(sql, {"cycle_id": str(cycle.id)}).fetchall()
                # Create simple objects from the rows
                class SimplePhase:
                    def __init__(self, row_data):
                        self.id = row_data[0]
                        # Create a simple enum-like object
                        class PhaseType:
                            def __init__(self, value):
                                self.value = value
                        self.phase_type = PhaseType(row_data[1])
                        self.monthly_start_day = row_data[2]
                        self.monthly_end_day = row_data[3]
                        self.penalty_amount = row_data[4]
                        self.penalty_type_id = None
                        self.auto_apply_penalty = None
                phases = [SimplePhase(row) for row in rows]
            except Exception as e2:
                # If even raw SQL fails, log and return empty phases
                logging.error(f"Error loading phases with raw SQL: {str(e2)}")
                phases = []
    
        phase_list = []
        for p in phases:
            phase_dict = {
                "id": str(p.id),
                "phase_type": p.phase_type.value,
                "monthly_start_day": p.monthly_start_day,
                "monthly_end_day": getattr(p, 'monthly_end_day', None),
                "penalty_amount": float(getattr(p, 'penalty_amount', None)) if getattr(p, 'penalty_amount', None) else None,
            }
            # Safely get new fields that might not exist in database yet
            try:
                penalty_type_id = getattr(p, 'penalty_type_id', None)
                phase_dict["penalty_type_id"] = str(penalty_type_id) if penalty_type_id else None
            except Exception:
                phase_dict["penalty_type_id"] = None
            
            try:
                phase_dict["auto_apply_penalty"] = getattr(p, 'auto_apply_penalty', False)
            except Exception:
                phase_dict["auto_apply_penalty"] = None
            
            phase_list.append(phase_dict)
    
        result = {
            "id": str(cycle.id),
            "year": cycle.year,
            "start_date": cycle.start_date.isoformat(),
            "end_date": cycle.end_date.isoformat(),
            "status": cycle.status.value,
            "created_at": cycle.created_at.isoformat(),
            "social_fund_required": float(cycle.social_fund_required) if cycle.social_fund_required else None,
            "admin_fund_required": float(cycle.admin_fund_required) if cycle.admin_fund_required else None,
            "phases": phase_list,
        }
        
        # Get credit rating scheme (if any)
        scheme = db.query(CreditRatingScheme).filter(
            CreditRatingScheme.effective_from <= cycle.end_date
        ).order_by(CreditRatingScheme.effective_from.desc()).first()
        
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
                ).order_by(CreditRatingInterestRange.term_months.asc()).all()
                
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
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error in get_cycle: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error loading cycle: {str(e)}"
        )


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
            
            phase_kwargs = {
                "cycle_id": cycle.id,
                "phase_type": phase_type,
                "phase_order": phase_order_map.get(phase_type, "0"),
                "monthly_start_day": phase_config.monthly_start_day,
                "monthly_end_day": phase_config.monthly_end_day,
                "penalty_amount": Decimal(str(phase_config.penalty_amount)) if phase_config.penalty_amount is not None else None,
                "is_open": False
            }
            # Only add new fields if they're provided (will fail if columns don't exist - migration needed)
            if phase_config.penalty_type_id:
                try:
                    phase_kwargs["penalty_type_id"] = UUID(phase_config.penalty_type_id)
                except Exception:
                    pass  # Column might not exist yet
            if phase_config.auto_apply_penalty is not None:
                try:
                    phase_kwargs["auto_apply_penalty"] = phase_config.auto_apply_penalty
                except Exception:
                    pass  # Column might not exist yet
            
            phase = CyclePhase(**phase_kwargs)
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
        from app.core.audit import write_audit_log
        write_audit_log(
            user_name=f"{current_user.first_name or ''} {current_user.last_name or ''}".strip(),
            user_role=current_user.role.value if current_user.role else "chairman",
            action="Cycle activated",
            details=f"year={cycle.year}"
        )
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
        from app.core.audit import write_audit_log
        write_audit_log(
            user_name=f"{current_user.first_name or ''} {current_user.last_name or ''}".strip(),
            user_role=current_user.role.value if current_user.role else "chairman",
            action="Cycle closed",
            details=f"year={cycle.year}"
        )
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
    """List all users (Chairman/Vice-Chairman/Admin only).
    Automatically syncs User.approved with MemberProfile.status to fix discrepancies.
    Returns users with member profile information included."""
    from app.services.member import sync_user_and_member_status
    try:
        users = db.query(User).all()
        
        # Auto-sync discrepancies for users with member profiles
        for user in users:
            try:
                member_profile = db.query(MemberProfile).filter(MemberProfile.user_id == user.id).first()
                if member_profile:
                    sync_user_and_member_status(db, user.id)
                    # Refresh user to get updated approved status
                    db.refresh(user)
            except Exception as e:
                # Log but don't fail the entire request if sync fails for one user
                import logging
                logging.error(f"Failed to sync user {user.id}: {str(e)}")
                continue
        
        # Build response with member information
        result = []
        for user in users:
            try:
                member_profile = db.query(MemberProfile).filter(MemberProfile.user_id == user.id).first()
                user_dict = {
                    "id": str(user.id),
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "role": user.role.value if user.role else "member",
                    "approved": user.approved
                }
                # Add member information if available
                if member_profile:
                    user_dict["member_id"] = str(member_profile.id)
                    user_dict["member_status"] = member_profile.status.value
                    user_dict["member_activated_at"] = member_profile.activated_at.isoformat() if member_profile.activated_at else None
                result.append(user_dict)
            except Exception as e:
                # Log but continue processing other users
                import logging
                logging.error(f"Failed to process user {user.id}: {str(e)}")
                continue
        
        return result
    except Exception as e:
        import logging
        logging.error(f"Error in list_users: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list users: {str(e)}")


@router.put("/users/{user_id}/approve")
def approve_user(
    user_id: str,
    current_user: User = Depends(require_any_role("Chairman", "Vice-Chairman", "Admin")),
    db: Session = Depends(get_db)
):
    """Approve a user (Chairman/Vice-Chairman/Admin only). Also activates member profile if one exists."""
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format")
    user = db.query(User).filter(User.id == user_uuid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Also activate member profile if one exists (this will also set user.approved = True)
    member_profile = db.query(MemberProfile).filter(MemberProfile.user_id == user.id).first()
    if member_profile and member_profile.status != MemberStatus.ACTIVE:
        from app.services.member import activate_member
        try:
            activate_member(db, member_profile.id, current_user.id)
            # activate_member already commits and sets user.approved, so we're done
            db.refresh(user)
            return {
                "message": "User approved successfully",
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "approved": user.approved
                }
            }
        except Exception as e:
            # If activation fails, still approve the user manually
            user.approved = True
            db.commit()
            db.refresh(user)
            return {
                "message": "User approved successfully (member activation failed)",
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "approved": user.approved
                }
            }
    else:
        # No member profile or already active, just approve the user
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
    """Suspend/disable a user (Chairman/Vice-Chairman/Admin only). Also suspends member profile if one exists."""
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format")
    user = db.query(User).filter(User.id == user_uuid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Also suspend member profile if one exists (this will also set user.approved = False)
    member_profile = db.query(MemberProfile).filter(MemberProfile.user_id == user.id).first()
    if member_profile and member_profile.status != MemberStatus.INACTIVE:
        from app.services.member import suspend_member
        try:
            suspend_member(db, member_profile.id, current_user.id)
            # suspend_member already commits and sets user.approved = False, so we're done
            return {"message": "User suspended successfully"}
        except Exception:
            # If suspension fails, still unapprove the user manually
            user.approved = False
            db.commit()
            return {"message": "User suspended successfully (member suspension failed)"}
    else:
        # No member profile or already suspended, just unapprove the user
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
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format")
    user = db.query(User).filter(User.id == user_uuid).first()
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


@router.get("/members/{member_id}/loan-terms")
def get_member_loan_terms(
    member_id: str,
    current_user: User = Depends(require_any_role("Chairman", "Vice-Chairman", "Treasurer", "Admin")),
    db: Session = Depends(get_db)
):
    """Get a member's available loan terms based on their credit rating for the active cycle."""
    from app.models.cycle import Cycle, CycleStatus
    from app.models.policy import MemberCreditRating, CreditRatingTier, CreditRatingInterestRange

    try:
        member_uuid = UUID(member_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid member ID format")

    active_cycle = db.query(Cycle).filter(Cycle.status == CycleStatus.ACTIVE).first()
    if not active_cycle:
        return {"available_terms": [], "message": "No active cycle"}

    credit_rating = db.query(MemberCreditRating).filter(
        MemberCreditRating.member_id == member_uuid,
        MemberCreditRating.cycle_id == active_cycle.id
    ).first()

    if not credit_rating:
        return {"available_terms": [], "message": "No credit rating assigned for this member"}

    tier = db.query(CreditRatingTier).filter(CreditRatingTier.id == credit_rating.tier_id).first()
    if not tier:
        return {"available_terms": [], "message": "Credit rating tier not found"}

    interest_ranges = db.query(CreditRatingInterestRange).filter(
        CreditRatingInterestRange.tier_id == tier.id,
        CreditRatingInterestRange.cycle_id == active_cycle.id
    ).all()

    available_terms = []
    for ir in interest_ranges:
        if ir.term_months is None:
            available_terms.append({
                "term_months": None,
                "term_label": "All Terms",
                "interest_rate": float(ir.effective_rate_percent)
            })
        else:
            available_terms.append({
                "term_months": ir.term_months,
                "term_label": f"{ir.term_months} Month{'s' if ir.term_months != '1' else ''}",
                "interest_rate": float(ir.effective_rate_percent)
            })

    available_terms.sort(key=lambda t: int(t["term_months"]) if t["term_months"] else 0)

    return {
        "available_terms": available_terms,
        "tier_name": tier.tier_name,
    }


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


# ─────────────────────────────────────────────────────────────
# Audit Log Endpoints
# ─────────────────────────────────────────────────────────────

@router.get("/audit/months")
def get_audit_months(
    current_user: User = Depends(require_any_role("Chairman", "Admin")),
):
    """List months for which audit log files exist, sorted descending."""
    from app.core.audit import LOGS_DIR
    import calendar

    if not LOGS_DIR.exists():
        return []

    months = []
    for f in LOGS_DIR.glob("audit_*.log"):
        stem = f.stem  # e.g. audit_2026_02
        parts = stem.split("_")
        if len(parts) == 3:
            try:
                year = int(parts[1])
                month = int(parts[2])
                label = f"{calendar.month_name[month]} {year}"
                months.append({"year": year, "month": month, "label": label})
            except (ValueError, IndexError):
                pass

    months.sort(key=lambda x: (x["year"], x["month"]), reverse=True)
    return months


@router.get("/audit/{year}/{month}")
def get_audit_log(
    year: int,
    month: int,
    current_user: User = Depends(require_any_role("Chairman", "Admin")),
):
    """Read audit log entries for a given year/month."""
    from app.core.audit import LOGS_DIR

    log_file = LOGS_DIR / f"audit_{year}_{month:02d}.log"
    if not log_file.exists():
        raise HTTPException(status_code=404, detail="No audit log for this month")

    lines_out = []
    with open(log_file, "r", encoding="utf-8") as f:
        for raw_line in f:
            raw_line = raw_line.rstrip("\n")
            if not raw_line:
                continue
            parts = raw_line.split(" | ", 4)
            if len(parts) == 5:
                lines_out.append({
                    "ts": parts[0],
                    "role": parts[1],
                    "name": parts[2],
                    "action": parts[3],
                    "details": parts[4],
                })
            else:
                lines_out.append({"ts": raw_line, "role": "", "name": "", "action": "", "details": ""})

    return {"lines": lines_out}


# ─────────────────────────────────────────────────────────────
# Reconciliation Endpoints
# ─────────────────────────────────────────────────────────────

class ReconcileRequest(BaseModel):
    member_id: str
    month: str  # YYYY-MM-DD
    savings_amount: float = 0.0
    social_fund: float = 0.0
    admin_fund: float = 0.0
    penalties: float = 0.0
    interest_on_loan: float = 0.0
    loan_repayment: float = 0.0
    loan_amount: float = 0.0
    loan_rate: float = 0.0
    loan_term_months: str = "1"  # e.g. "1", "2", "3", "4"


@router.get("/reconcile")
def get_reconcile(
    member_id: str,
    month: str,
    current_user: User = Depends(require_any_role("Chairman", "Treasurer", "Admin")),
    db: Session = Depends(get_db)
):
    """Get existing declaration / loan data for a member + month to pre-fill reconciliation form."""
    from app.models.transaction import Declaration, Loan, LoanStatus
    from app.models.cycle import Cycle, CycleStatus
    from sqlalchemy import extract, and_
    from datetime import date as date_type

    try:
        member_uuid = UUID(member_id)
        month_date = date_type.fromisoformat(month)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid member_id or month format (use YYYY-MM-DD)")

    today = date_type.today()
    if (month_date.year, month_date.month) > (today.year, today.month):
        raise HTTPException(status_code=400, detail="Cannot reconcile a future month")

    # Active cycle
    active_cycle = db.query(Cycle).filter(Cycle.status == CycleStatus.ACTIVE).first()

    # Declaration for member + month
    declaration = db.query(Declaration).filter(
        and_(
            Declaration.member_id == member_uuid,
            extract("year", Declaration.effective_month) == month_date.year,
            extract("month", Declaration.effective_month) == month_date.month,
        )
    ).first()

    # Loan disbursed in that month
    loan = db.query(Loan).filter(
        and_(
            Loan.member_id == member_uuid,
            extract("year", Loan.disbursement_date) == month_date.year,
            extract("month", Loan.disbursement_date) == month_date.month,
        )
    ).first()

    decl_out = {
        "savings_amount": float(declaration.declared_savings_amount or 0) if declaration else 0.0,
        "social_fund": float(declaration.declared_social_fund or 0) if declaration else 0.0,
        "admin_fund": float(declaration.declared_admin_fund or 0) if declaration else 0.0,
        "penalties": float(declaration.declared_penalties or 0) if declaration else 0.0,
        "interest_on_loan": float(declaration.declared_interest_on_loan or 0) if declaration else 0.0,
        "loan_repayment": float(declaration.declared_loan_repayment or 0) if declaration else 0.0,
        "status": declaration.status.value if declaration else None,
    }

    loan_out = {
        "loan_amount": float(loan.loan_amount or 0) if loan else 0.0,
        "loan_rate": float(loan.percentage_interest or 0) if loan else 0.0,
        "loan_term_months": loan.number_of_instalments or "1" if loan else "1",
    }

    return {"declaration": decl_out, "loan": loan_out}


@router.post("/reconcile")
def post_reconcile(
    body: ReconcileRequest,
    current_user: User = Depends(require_any_role("Chairman", "Treasurer", "Admin")),
    db: Session = Depends(get_db)
):
    """Save backlog financial data for a member + month, bypassing normal member flow."""
    from app.models.transaction import (
        Declaration, DeclarationStatus,
        DepositProof, DepositProofStatus, DepositApproval,
        Loan, LoanStatus,
    )
    from app.models.cycle import Cycle, CycleStatus
    from app.models.ledger import LedgerAccount, AccountType, JournalEntry, JournalLine
    from app.services.transaction import create_declaration, approve_deposit
    from app.services.accounting import create_journal_entry
    from app.core.audit import write_audit_log
    from sqlalchemy import extract, and_
    from datetime import date as date_type

    try:
        member_uuid = UUID(body.member_id)
        month_date = date_type.fromisoformat(body.month)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid member_id or month format (use YYYY-MM-DD)")

    today = date_type.today()
    if (month_date.year, month_date.month) > (today.year, today.month):
        raise HTTPException(status_code=400, detail="Cannot reconcile a future month")

    # 1. Active cycle
    active_cycle = db.query(Cycle).filter(Cycle.status == CycleStatus.ACTIVE).first()
    if not active_cycle:
        raise HTTPException(status_code=404, detail="No active cycle found")

    # 2. Load or create Declaration
    declaration = db.query(Declaration).filter(
        and_(
            Declaration.member_id == member_uuid,
            extract("year", Declaration.effective_month) == month_date.year,
            extract("month", Declaration.effective_month) == month_date.month,
        )
    ).first()

    if declaration:
        declaration.declared_savings_amount = Decimal(str(body.savings_amount))
        declaration.declared_social_fund = Decimal(str(body.social_fund))
        declaration.declared_admin_fund = Decimal(str(body.admin_fund))
        declaration.declared_penalties = Decimal(str(body.penalties))
        declaration.declared_interest_on_loan = Decimal(str(body.interest_on_loan))
        declaration.declared_loan_repayment = Decimal(str(body.loan_repayment))
        declaration.status = DeclarationStatus.PENDING
        db.flush()
    else:
        declaration = Declaration(
            member_id=member_uuid,
            cycle_id=active_cycle.id,
            effective_month=month_date,
            declared_savings_amount=Decimal(str(body.savings_amount)),
            declared_social_fund=Decimal(str(body.social_fund)),
            declared_admin_fund=Decimal(str(body.admin_fund)),
            declared_penalties=Decimal(str(body.penalties)),
            declared_interest_on_loan=Decimal(str(body.interest_on_loan)),
            declared_loan_repayment=Decimal(str(body.loan_repayment)),
            status=DeclarationStatus.PENDING,
        )
        db.add(declaration)
        db.flush()

    # 3. Reverse any existing DepositApproval journal entry
    existing_proof = db.query(DepositProof).filter(
        DepositProof.declaration_id == declaration.id
    ).order_by(DepositProof.uploaded_at.desc()).first()

    if existing_proof:
        existing_approval = db.query(DepositApproval).filter(
            DepositApproval.deposit_proof_id == existing_proof.id
        ).first()
        if existing_approval and existing_approval.journal_entry_id:
            old_entry = db.query(JournalEntry).filter(
                JournalEntry.id == existing_approval.journal_entry_id
            ).first()
            if old_entry:
                old_entry.reversed_by = current_user.id
                old_entry.reversed_at = datetime.now()
                db.flush()
        # Mark old proof superseded
        existing_proof.status = "superseded"
        db.flush()

    # 4. Create synthetic DepositProof
    total_amount = Decimal(str(
        body.savings_amount + body.social_fund + body.admin_fund +
        body.penalties + body.interest_on_loan + body.loan_repayment
    ))
    synthetic_proof = DepositProof(
        member_id=member_uuid,
        cycle_id=active_cycle.id,
        declaration_id=declaration.id,
        upload_path="reconciliation",
        amount=total_amount,
        status=DepositProofStatus.SUBMITTED.value,
    )
    db.add(synthetic_proof)
    db.flush()

    # 5. Look up ledger accounts
    bank_cash = db.query(LedgerAccount).filter(
        LedgerAccount.account_code == "BANK_CASH"
    ).first()
    if not bank_cash:
        raise HTTPException(status_code=500, detail="BANK_CASH ledger account not found")

    member_savings = db.query(LedgerAccount).filter(
        LedgerAccount.member_id == member_uuid,
        LedgerAccount.account_name.ilike("%savings%")
    ).first()
    if not member_savings:
        short_id = str(member_uuid).replace("-", "")[:8]
        member_savings = LedgerAccount(
            account_code=f"MEM_SAV_{short_id}",
            account_name=f"Member Savings - {member_uuid}",
            account_type=AccountType.LIABILITY,
            member_id=member_uuid,
            description=f"Savings account for member {member_uuid}",
        )
        db.add(member_savings)
        db.flush()

    member_social_fund = db.query(LedgerAccount).filter(
        LedgerAccount.member_id == member_uuid,
        LedgerAccount.account_name.ilike("%social fund%")
    ).first()
    if not member_social_fund and body.social_fund > 0:
        short_id = str(member_uuid).replace("-", "")[:8]
        member_social_fund = LedgerAccount(
            account_code=f"MEM_SOC_{short_id}",
            account_name=f"Member Social Fund - {member_uuid}",
            account_type=AccountType.LIABILITY,
            member_id=member_uuid,
            description=f"Social fund account for member {member_uuid}",
        )
        db.add(member_social_fund)
        db.flush()

    member_admin_fund = db.query(LedgerAccount).filter(
        LedgerAccount.member_id == member_uuid,
        LedgerAccount.account_name.ilike("%admin fund%")
    ).first()
    if not member_admin_fund and body.admin_fund > 0:
        short_id = str(member_uuid).replace("-", "")[:8]
        member_admin_fund = LedgerAccount(
            account_code=f"MEM_ADM_{short_id}",
            account_name=f"Member Admin Fund - {member_uuid}",
            account_type=AccountType.LIABILITY,
            member_id=member_uuid,
            description=f"Admin fund account for member {member_uuid}",
        )
        db.add(member_admin_fund)
        db.flush()

    interest_income = db.query(LedgerAccount).filter(
        LedgerAccount.account_code == "INTEREST_INCOME"
    ).first()

    loans_receivable = db.query(LedgerAccount).filter(
        LedgerAccount.account_code.like("LOANS_RECEIVABLE%")
    ).first()

    # 6. Approve the synthetic deposit proof (posts to ledger)
    try:
        approve_deposit(
            db=db,
            deposit_proof_id=synthetic_proof.id,
            approved_by=current_user.id,
            bank_cash_account_id=bank_cash.id,
            member_savings_account_id=member_savings.id,
            member_social_fund_account_id=member_social_fund.id if member_social_fund else None,
            member_admin_fund_account_id=member_admin_fund.id if member_admin_fund else None,
            interest_income_account_id=interest_income.id if interest_income else None,
            loans_receivable_account_id=loans_receivable.id if loans_receivable else None,
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to post reconciliation to ledger: {str(e)}")

    # Transfer any excess social/admin fund contributions to savings
    from app.services.transaction import post_excess_contributions
    post_excess_contributions(
        db=db,
        member_id=member_uuid,
        cycle=active_cycle,
        effective_month=month_date,
        approved_by=current_user.id,
    )

    # Backdate deposit journal entry to reconciliation month so B/F columns in group report are correct
    updated_approval = db.query(DepositApproval).filter(
        DepositApproval.deposit_proof_id == synthetic_proof.id
    ).first()
    if updated_approval and updated_approval.journal_entry_id:
        deposit_je = db.query(JournalEntry).filter(
            JournalEntry.id == updated_approval.journal_entry_id
        ).first()
        if deposit_je:
            from datetime import datetime as dt
            deposit_je.entry_date = dt.combine(month_date, dt.min.time())
            db.flush()

    # 7. Handle loan (if loan_amount > 0)
    if body.loan_amount > 0:
        existing_loan = db.query(Loan).filter(
            and_(
                Loan.member_id == member_uuid,
                extract("year", Loan.disbursement_date) == month_date.year,
                extract("month", Loan.disbursement_date) == month_date.month,
            )
        ).first()

        if existing_loan:
            # Update existing loan details
            existing_loan.loan_amount = Decimal(str(body.loan_amount))
            existing_loan.percentage_interest = Decimal(str(body.loan_rate))
            existing_loan.number_of_instalments = body.loan_term_months
            db.flush()
        else:
            if not loans_receivable:
                raise HTTPException(status_code=500, detail="LOANS_RECEIVABLE ledger account not found")

            new_loan = Loan(
                member_id=member_uuid,
                cycle_id=active_cycle.id,
                application_id=None,
                loan_amount=Decimal(str(body.loan_amount)),
                percentage_interest=Decimal(str(body.loan_rate)),
                number_of_instalments=body.loan_term_months,
                loan_status=LoanStatus.DISBURSED,
                disbursement_date=month_date,
                effective_month=month_date,
            )
            db.add(new_loan)
            db.flush()

            # Create disbursement journal entry: Debit LOANS_RECEIVABLE, Credit BANK_CASH
            from datetime import datetime as dt
            loan_je = create_journal_entry(
                db=db,
                description=f"Loan disbursement (reconciliation) for member {member_uuid} - {month_date}",
                source_type="loan_disbursement",
                source_ref=str(new_loan.id),
                lines=[
                    {
                        "account_id": loans_receivable.id,
                        "debit_amount": Decimal(str(body.loan_amount)),
                        "credit_amount": Decimal("0.00"),
                        "description": "Loan disbursed (reconciliation)",
                    },
                    {
                        "account_id": bank_cash.id,
                        "debit_amount": Decimal("0.00"),
                        "credit_amount": Decimal(str(body.loan_amount)),
                        "description": "Cash paid out for loan (reconciliation)",
                    },
                ],
                created_by=current_user.id,
            )
            # Backdate loan disbursement entry to reconciliation month
            loan_je.entry_date = dt.combine(month_date, dt.min.time())
            db.flush()

    # 8. Audit log
    write_audit_log(
        user_name=f"{current_user.first_name or ''} {current_user.last_name or ''}".strip(),
        user_role=current_user.role.value if current_user.role else "chairman",
        action="Reconciliation saved",
        details=f"member={body.member_id}, month={month_date.strftime('%Y-%m')}",
    )

    db.commit()
    return {"message": "Reconciliation saved successfully"}


# ---------------------------------------------------------------------------
# Ledger Initialisation
# ---------------------------------------------------------------------------

# ─────────────────────────────────────────────────────────────
# Loan Term Options Endpoints
# ─────────────────────────────────────────────────────────────

class LoanTermCreate(BaseModel):
    term_months: str


def _loan_terms_list(db: Session):
    from app.models.policy import LoanTermOption
    terms = db.query(LoanTermOption).order_by(
        LoanTermOption.sort_order, LoanTermOption.term_months
    ).all()
    return [{"term_months": t.term_months, "sort_order": t.sort_order} for t in terms]


@router.get("/settings/loan-terms")
def get_loan_terms(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all configured loan term options (any authenticated user)."""
    return _loan_terms_list(db)


@router.post("/settings/loan-terms")
def add_loan_term(
    body: LoanTermCreate,
    current_user: User = Depends(require_any_role("Chairman", "Vice-Chairman")),
    db: Session = Depends(get_db)
):
    """Add a new loan term option (Chairman/Vice-Chairman only)."""
    from app.models.policy import LoanTermOption

    # Validate: must be a positive integer string
    try:
        months_int = int(body.term_months)
        if months_int <= 0:
            raise ValueError
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="term_months must be a positive integer")

    term_str = str(months_int)

    existing = db.query(LoanTermOption).filter(LoanTermOption.term_months == term_str).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Term '{term_str}' already exists")

    new_term = LoanTermOption(term_months=term_str, sort_order=months_int)
    db.add(new_term)
    db.commit()
    return _loan_terms_list(db)


@router.delete("/settings/loan-terms/{term_months}")
def delete_loan_term(
    term_months: str,
    current_user: User = Depends(require_any_role("Chairman", "Vice-Chairman")),
    db: Session = Depends(get_db)
):
    """Delete a loan term option (Chairman/Vice-Chairman only)."""
    from app.models.policy import LoanTermOption

    term = db.query(LoanTermOption).filter(LoanTermOption.term_months == term_months).first()
    if not term:
        raise HTTPException(status_code=404, detail=f"Term '{term_months}' not found")

    db.delete(term)
    db.commit()
    return _loan_terms_list(db)


@router.post("/initialize-ledger")
def initialize_ledger(
    current_user: User = Depends(require_any_role("Chairman", "Admin")),
    db: Session = Depends(get_db),
):
    """Seed the global chart of accounts on a fresh install.

    Safe to call multiple times — accounts that already exist are skipped.
    Returns a summary of accounts created vs already present.
    """
    from app.models.ledger import LedgerAccount, AccountType

    GLOBAL_ACCOUNTS = [
        {
            "account_code": "BANK_CASH",
            "account_name": "Bank / Cash",
            "account_type": AccountType.ASSET,
            "description": "Main bank and cash account",
        },
        {
            "account_code": "LOANS_RECEIVABLE",
            "account_name": "Loans Receivable",
            "account_type": AccountType.ASSET,
            "description": "Outstanding member loans",
        },
        {
            "account_code": "INTEREST_INCOME",
            "account_name": "Interest Income",
            "account_type": AccountType.INCOME,
            "description": "Income from loan interest",
        },
        {
            "account_code": "PENALTY_INCOME",
            "account_name": "Penalty Income",
            "account_type": AccountType.INCOME,
            "description": "Income from member penalties",
        },
        {
            "account_code": "SOCIAL_FUND",
            "account_name": "Social Fund",
            "account_type": AccountType.LIABILITY,
            "description": "Group social fund pool",
        },
        {
            "account_code": "ADMIN_FUND",
            "account_name": "Administration Fund",
            "account_type": AccountType.LIABILITY,
            "description": "Group administration fund pool",
        },
        {
            "account_code": "EQUITY",
            "account_name": "Group Equity",
            "account_type": AccountType.EQUITY,
            "description": "Group retained earnings / equity",
        },
    ]

    created = []
    already_exists = []

    for acct in GLOBAL_ACCOUNTS:
        existing = db.query(LedgerAccount).filter(
            LedgerAccount.account_code == acct["account_code"]
        ).first()
        if existing:
            already_exists.append(acct["account_code"])
        else:
            new_acct = LedgerAccount(
                account_code=acct["account_code"],
                account_name=acct["account_name"],
                account_type=acct["account_type"],
                description=acct["description"],
                is_active=True,
            )
            db.add(new_acct)
            created.append(acct["account_code"])

    db.commit()

    return {
        "message": "Ledger initialised successfully",
        "created": created,
        "already_existed": already_exists,
    }
