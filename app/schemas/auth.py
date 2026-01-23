from pydantic import BaseModel, EmailStr
from typing import Optional, List


class UserRegister(BaseModel):
    email: EmailStr
    password: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None
    nrc_number: Optional[str] = None
    physical_address: Optional[str] = None
    bank_account: Optional[str] = None
    bank_name: Optional[str] = None
    bank_branch: Optional[str] = None
    first_name_next_of_kin: Optional[str] = None
    last_name_next_of_kin: Optional[str] = None
    phone_number_next_of_kin: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    approved: Optional[bool] = None
    roles: Optional[List[str]] = None
    phone_number: Optional[str] = None
    nrc_number: Optional[str] = None
    physical_address: Optional[str] = None
    bank_account: Optional[str] = None
    bank_name: Optional[str] = None
    bank_branch: Optional[str] = None
    first_name_next_of_kin: Optional[str] = None
    last_name_next_of_kin: Optional[str] = None
    phone_number_next_of_kin: Optional[str] = None
    
    @classmethod
    def from_orm(cls, obj):
        """Convert ORM object to response model."""
        return cls(
            id=str(obj.id),
            email=obj.email,
            first_name=obj.first_name,
            last_name=obj.last_name,
            approved=obj.approved,
            phone_number=obj.phone_number,
            nrc_number=obj.nrc_number,
            physical_address=obj.physical_address,
            bank_account=obj.bank_account,
            bank_name=obj.bank_name,
            bank_branch=obj.bank_branch,
            first_name_next_of_kin=obj.first_name_next_of_kin,
            last_name_next_of_kin=obj.last_name_next_of_kin,
            phone_number_next_of_kin=obj.phone_number_next_of_kin
        )
    
    class Config:
        from_attributes = True


class UserProfileUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None
    nrc_number: Optional[str] = None
    physical_address: Optional[str] = None
    bank_account: Optional[str] = None
    bank_name: Optional[str] = None
    bank_branch: Optional[str] = None
    first_name_next_of_kin: Optional[str] = None
    last_name_next_of_kin: Optional[str] = None
    phone_number_next_of_kin: Optional[str] = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str
