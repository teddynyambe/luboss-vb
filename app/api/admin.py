from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.core.dependencies import require_admin, get_current_user
from app.models.user import User, UserRoleEnum
from app.models.system import SystemSettings
from pydantic import BaseModel
from typing import Optional, Dict, List

router = APIRouter(prefix="/api/admin", tags=["admin"])


class SystemSettingsResponse(BaseModel):
    settings: Dict[str, str]
    
    class Config:
        from_attributes = True


class SystemSettingsUpdate(BaseModel):
    settings: Dict[str, str]


@router.get("/settings", response_model=SystemSettingsResponse)
def get_settings(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Get system settings (Admin only)."""
    settings = db.query(SystemSettings).all()
    settings_dict = {s.setting_key: s.setting_value for s in settings}
    return {"settings": settings_dict}


@router.put("/settings")
def update_settings(
    settings_update: SystemSettingsUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Update system settings (Admin only)."""
    for key, value in settings_update.settings.items():
        setting = db.query(SystemSettings).filter(
            SystemSettings.setting_key == key
        ).first()
        
        if setting:
            setting.setting_value = value
            setting.updated_by = current_user.id
        else:
            setting = SystemSettings(
                setting_key=key,
                setting_value=value,
                setting_type="general",
                updated_by=current_user.id
            )
            db.add(setting)
    
    db.commit()
    return {"message": "Settings updated successfully"}


