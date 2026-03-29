from typing import Optional
from pydantic import BaseModel, EmailStr, ConfigDict

# Shared properties
class UserBase(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    role: Optional[str] = "viewer"
    is_active: Optional[bool] = True
    mfa_enabled: Optional[bool] = None

# Properties to receive via API on creation
class UserCreate(UserBase):
    username: str
    password: str
    role: str = "viewer"

# Properties to receive via API on update
class UserUpdate(UserBase):
    password: Optional[str] = None

# Properties to return to client
class UserResponse(UserBase):
    id: int
    eula_accepted: bool
    must_change_password: bool
    mfa_enabled: bool
    email_verified: bool

    model_config = ConfigDict(from_attributes=True)
