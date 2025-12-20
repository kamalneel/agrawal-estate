"""
Authentication API routes.
"""

from fastapi import APIRouter, Response
from app.core.auth import LoginRequest, TokenResponse, authenticate, get_current_user, Depends

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """
    Authenticate with the family password.
    Returns a JWT token valid for 7 days.
    """
    return authenticate(request.password)


@router.post("/logout")
async def logout(response: Response):
    """
    Logout - client should discard the token.
    This endpoint is mainly for logging/audit purposes.
    """
    return {"message": "Logged out successfully"}


@router.get("/verify")
async def verify_token(user: dict = Depends(get_current_user)):
    """
    Verify the current token is valid.
    Returns token info if valid.
    """
    return {
        "valid": True,
        "user": user.get("sub"),
        "expires": user.get("exp"),
    }


@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    """
    Get current user info.
    """
    return {
        "family": "Agrawal",
        "authenticated": True,
    }















