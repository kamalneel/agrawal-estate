"""
Authentication module for the Agrawal Estate Planner.
Simple password-based authentication with JWT tokens.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
import hashlib
import secrets

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from pydantic import BaseModel

from app.core.config import settings


# Security scheme
security = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    """Login request body."""
    password: str


class TokenResponse(BaseModel):
    """Token response."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class AuthError(HTTPException):
    """Authentication error."""
    def __init__(self, detail: str = "Authentication required"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


def hash_password(password: str) -> str:
    """Hash a password using SHA-256 with the secret key as salt."""
    salted = f"{settings.SECRET_KEY}:{password}"
    return hashlib.sha256(salted.encode()).hexdigest()


def verify_password(password: str) -> bool:
    """Verify the provided password matches the family password."""
    return hash_password(password) == settings.PASSWORD_HASH


def create_access_token(expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    expire = datetime.now(timezone.utc) + expires_delta
    
    payload = {
        "sub": "agrawal_family",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": secrets.token_hex(16),  # Unique token ID
    }
    
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        return payload
    except JWTError as e:
        if "expired" in str(e).lower():
            raise AuthError("Token has expired")
        raise AuthError("Invalid token")


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """
    Dependency to get the current authenticated user.
    Returns the decoded token payload if valid.
    """
    if credentials is None:
        raise AuthError("Authentication required")
    
    token = credentials.credentials
    return decode_token(token)


async def optional_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[dict]:
    """
    Optional authentication - returns None if not authenticated.
    Useful for endpoints that work differently for authenticated users.
    """
    if credentials is None:
        return None
    
    try:
        return decode_token(credentials.credentials)
    except AuthError:
        return None


def authenticate(password: str) -> TokenResponse:
    """
    Authenticate with password and return access token.
    """
    if not verify_password(password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password",
        )
    
    expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(expires_delta)
    
    return TokenResponse(
        access_token=access_token,
        expires_in=int(expires_delta.total_seconds()),
    )

