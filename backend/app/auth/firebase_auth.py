"""
Firebase Authentication Middleware

Verifies Firebase ID tokens and extracts user information.
Supports demo mode with pseudo-IDs for testing.
"""

import os
from dataclasses import dataclass
from typing import Optional

import firebase_admin
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth


def _ensure_firebase_initialized():
    """Lazy Firebase initialization - only when actually needed for token verification."""
    if not firebase_admin._apps:
        firebase_admin.initialize_app()

# HTTP Bearer scheme for Authorization header
security = HTTPBearer(auto_error=False)

# Demo mode configuration
DEMO_MODE_ENABLED = os.environ.get("DEMO_MODE", "true").lower() == "true"
DEMO_USER_PREFIX = "demo_"


@dataclass
class FirebaseUser:
    """Represents an authenticated Firebase user."""

    uid: str
    email: Optional[str] = None
    name: Optional[str] = None
    picture: Optional[str] = None
    email_verified: bool = False
    is_demo: bool = False

    @classmethod
    def from_token(cls, decoded_token: dict) -> "FirebaseUser":
        """Create FirebaseUser from decoded Firebase ID token."""
        return cls(
            uid=decoded_token["uid"],
            email=decoded_token.get("email"),
            name=decoded_token.get("name"),
            picture=decoded_token.get("picture"),
            email_verified=decoded_token.get("email_verified", False),
            is_demo=False,
        )

    @classmethod
    def demo_user(cls, demo_id: str) -> "FirebaseUser":
        """Create a demo user with pseudo-ID."""
        return cls(
            uid=f"{DEMO_USER_PREFIX}{demo_id}",
            email=f"{demo_id}@demo.catefolio.local",
            name=f"Demo User ({demo_id})",
            email_verified=False,
            is_demo=True,
        )


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_demo_user_id: Optional[str] = Header(None, alias="X-Demo-User-Id"),
) -> FirebaseUser:
    """
    Dependency that verifies Firebase ID token and returns the current user.
    Supports demo mode with X-Demo-User-Id header.

    Usage:
        @router.get("/protected")
        def protected_route(user: FirebaseUser = Depends(get_current_user)):
            return {"user_id": user.uid}

    Demo mode:
        Send header: X-Demo-User-Id: my-demo-session
        Returns demo user with uid: demo_my-demo-session
    """
    # Check for demo mode first
    if DEMO_MODE_ENABLED and x_demo_user_id:
        return FirebaseUser.demo_user(x_demo_user_id)

    # Require real authentication if no demo header
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        _ensure_firebase_initialized()
        decoded_token = auth.verify_id_token(token)
        return FirebaseUser.from_token(decoded_token)
    except auth.InvalidIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_demo_user_id: Optional[str] = Header(None, alias="X-Demo-User-Id"),
) -> Optional[FirebaseUser]:
    """
    Dependency that optionally verifies Firebase ID token.
    Returns None if no token is provided (for public endpoints).
    Supports demo mode with X-Demo-User-Id header.

    Usage:
        @router.get("/public-or-private")
        def flexible_route(user: Optional[FirebaseUser] = Depends(get_optional_user)):
            if user:
                return {"user_id": user.uid}
            return {"message": "Anonymous access"}
    """
    # Check for demo mode first
    if DEMO_MODE_ENABLED and x_demo_user_id:
        return FirebaseUser.demo_user(x_demo_user_id)

    if credentials is None:
        return None

    try:
        _ensure_firebase_initialized()
        token = credentials.credentials
        decoded_token = auth.verify_id_token(token)
        return FirebaseUser.from_token(decoded_token)
    except Exception:
        return None
