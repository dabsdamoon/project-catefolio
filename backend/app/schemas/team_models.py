"""
Team Feature Models

Pydantic models for team management, membership, and invites.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TeamRole(str, Enum):
    """Team member roles."""

    ADMIN = "admin"
    MEMBER = "member"


class MembershipStatus(str, Enum):
    """Team membership status."""

    ACTIVE = "active"
    PENDING = "pending"


# =============================================================================
# Request Models
# =============================================================================


class TeamCreate(BaseModel):
    """Request model for creating a team."""

    name: str = Field(..., min_length=1, max_length=100, description="Team name")


class TeamUpdate(BaseModel):
    """Request model for updating a team."""

    name: str = Field(..., min_length=1, max_length=100, description="New team name")


class JoinTeamRequest(BaseModel):
    """Request model for joining a team via invite code."""

    invite_code: str = Field(..., description="The invite code from the invite link")


class UpdateMemberRoleRequest(BaseModel):
    """Request model for updating a member's role."""

    role: TeamRole = Field(..., description="The new role for the member")


class CreateInviteRequest(BaseModel):
    """Request model for creating an invite link."""

    max_uses: int = Field(
        default=0,
        ge=0,
        description="Maximum number of uses (0 = unlimited)",
    )
    expires_hours: Optional[int] = Field(
        default=None,
        ge=1,
        description="Hours until expiration (None = no expiration)",
    )


# =============================================================================
# Response Models
# =============================================================================


class TeamResponse(BaseModel):
    """Response model for team information."""

    id: str
    name: str
    owner_id: str
    created_at: str
    updated_at: str
    member_count: int


class TeamMemberResponse(BaseModel):
    """Response model for team member information."""

    user_id: str
    email: Optional[str] = None
    name: Optional[str] = None
    role: TeamRole
    joined_at: str
    is_owner: bool


class TeamInviteResponse(BaseModel):
    """Response model for team invite information."""

    id: str  # The invite code
    team_id: str
    created_by: str
    created_at: str
    expires_at: Optional[str] = None
    max_uses: int
    use_count: int
    is_active: bool
    invite_url: str  # Full URL for sharing


class TeamMembershipResponse(BaseModel):
    """Response model for current user's membership status."""

    team: Optional[TeamResponse] = None
    membership: Optional[dict] = None
    is_member: bool = False
    is_admin: bool = False
