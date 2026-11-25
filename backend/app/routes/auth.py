"""Authentication endpoints for Sign In, Register, Forgot Password, and Session Management."""

from typing import Optional
from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

from backend.app.core.config import settings
from backend.app.services.auth_service import (
    auth_service,
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    ResetCodeError,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


class UserProfile(BaseModel):
    user_id: str
    full_name: str
    email: str
    registration_no: str = ""
    created_at: str


class RegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100)
    email: str = Field(..., min_length=5, max_length=150)
    password: str = Field(..., min_length=6, max_length=128)
    registration_no: Optional[str] = Field(default="", max_length=40)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=150)
    password: str = Field(..., min_length=1, max_length=128)


class AuthResponse(BaseModel):
    user: UserProfile
    access_token: str


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=150)


class ForgotPasswordResponse(BaseModel):
    message: str
    dev_reset_code: Optional[str] = None
    expires_in_minutes: int = 15


class ResetPasswordRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=150)
    reset_code: str = Field(..., min_length=6, max_length=12)
    new_password: str = Field(..., min_length=6, max_length=128)


class MessageResponse(BaseModel):
    message: str


def _extract_bearer_token(authorization: Optional[str]) -> str:
    if not authorization:
        return ""
    parts = authorization.strip().split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return ""


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest) -> AuthResponse:
    """Register a new UniMind student/user account."""
    if "@" not in request.email or "." not in request.email.split("@")[-1]:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Please enter a valid email address.")
    try:
        user, token = auth_service.register_user(
            full_name=request.full_name,
            email=request.email,
            password=request.password,
            registration_no=request.registration_no,
        )
        return AuthResponse(user=UserProfile(**user), access_token=token)
    except EmailAlreadyExistsError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err)) from err


@router.post("/login", response_model=AuthResponse, status_code=status.HTTP_200_OK)
async def login(request: LoginRequest) -> AuthResponse:
    """Sign in with email and password."""
    try:
        user, token = auth_service.login_user(email=request.email, password=request.password)
        return AuthResponse(user=UserProfile(**user), access_token=token)
    except InvalidCredentialsError as err:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(err)) from err


@router.post("/forgot-password", response_model=ForgotPasswordResponse, status_code=status.HTTP_200_OK)
async def forgot_password(request: ForgotPasswordRequest) -> ForgotPasswordResponse:
    """Issue a time-limited 6-digit reset verification code for password recovery."""
    try:
        otp_code = auth_service.request_password_reset(email=request.email)
        return ForgotPasswordResponse(
            message="Verification code generated. Valid for 15 minutes.",
            dev_reset_code=otp_code if settings.ENVIRONMENT == "development" else None,
            expires_in_minutes=15,
        )
    except ResetCodeError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err


@router.post("/reset-password", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def reset_password(request: ResetPasswordRequest) -> MessageResponse:
    """Reset password using the email + verification code."""
    try:
        auth_service.reset_password(
            email=request.email,
            reset_code=request.reset_code,
            new_password=request.new_password,
        )
        return MessageResponse(message="Password updated successfully. You can now sign in.")
    except ResetCodeError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err


@router.get("/me", response_model=UserProfile, status_code=status.HTTP_200_OK)
async def get_me(authorization: Optional[str] = Header(default=None)) -> UserProfile:
    """Verify current session token and return authenticated user profile."""
    token = _extract_bearer_token(authorization)
    user = auth_service.get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated or session expired.")
    return UserProfile(**user)


@router.post("/logout", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def logout(authorization: Optional[str] = Header(default=None)) -> MessageResponse:
    """Invalidate the current bearer session."""
    token = _extract_bearer_token(authorization)
    auth_service.logout_token(token)
    return MessageResponse(message="Signed out successfully.")
