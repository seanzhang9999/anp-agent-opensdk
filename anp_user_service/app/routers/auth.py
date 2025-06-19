from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel

from ..models.schemas import LoginResponse, UserCredentials
from ..services.user_service import get_user_by_username, verify_password, get_user_personal_data_path

router = APIRouter()

class UserInfoRequest(BaseModel):
    username: str

class UserInfoResponse(BaseModel):
    success: bool
    username: str
    did: str = None
    message: str = None
@router.post("/login", response_model=LoginResponse)
async def login_for_access(form_data: UserCredentials):
    user_info = get_user_by_username(form_data.username)
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not verify_password(form_data.password, user_info):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    did = user_info.get("did")
    if not did:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User record is missing DID.",
        )
        
    personal_data_dir = get_user_personal_data_path(did=did)
    if not personal_data_dir or not personal_data_dir.exists():
        logger.debug(f"Warning: Personal data directory not found for user {form_data.username} (DID: {did}) at {personal_data_dir}")
    return LoginResponse(
        success=True,
        message="Login successful",
        user={"username": form_data.username, "did": did}
    )

@router.post("/userinfo", response_model=UserInfoResponse)
async def get_userinfo(request: UserInfoRequest):
    user_info = get_user_by_username(request.username)
    if not user_info:
        return UserInfoResponse(success=False, username=request.username, did=None, message="User not found")
    did = user_info.get("did")
    if not did:
        return UserInfoResponse(success=False, username=request.username, did=None, message="DID not found for user")
    return UserInfoResponse(success=True, username=request.username, did=did, message="User info fetched successfully")
