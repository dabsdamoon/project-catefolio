"""
Team API Routes

API endpoints for team management, membership, and invites.
"""

import os
from typing import Optional

import firebase_admin
from firebase_admin import auth as firebase_auth
from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.firebase_auth import FirebaseUser, get_current_user
from app.repositories.team_repo import TeamRepository, get_team_repo
from app.schemas.team_models import (
    CreateInviteRequest,
    JoinTeamRequest,
    TeamCreate,
    TeamInviteResponse,
    TeamMemberResponse,
    TeamMembershipResponse,
    TeamResponse,
    TeamRole,
    TeamUpdate,
    UpdateMemberRoleRequest,
)

router = APIRouter(prefix="/teams", tags=["teams"])


def _get_invite_base_url() -> str:
    """Get the base URL for invite links."""
    # Use environment variable or default
    return os.environ.get("FRONTEND_URL", "http://localhost:5173")


def _ensure_firebase_initialized():
    """Ensure Firebase Admin SDK is initialized."""
    if not firebase_admin._apps:
        firebase_admin.initialize_app()


def _get_user_details(user_id: str) -> tuple[Optional[str], Optional[str]]:
    """
    Fetch user email and display name from Firebase Auth.

    Args:
        user_id: Firebase user UID

    Returns:
        Tuple of (email, display_name). Returns (None, None) if user not found
        or if it's a demo user.
    """
    # Handle demo users (they don't exist in Firebase Auth)
    if user_id.startswith("demo_"):
        demo_id = user_id.replace("demo_", "", 1)
        return (f"{demo_id}@demo.catefolio.local", f"Demo User ({demo_id})")

    try:
        _ensure_firebase_initialized()
        user_record = firebase_auth.get_user(user_id)
        return (user_record.email, user_record.display_name)
    except firebase_auth.UserNotFoundError:
        return (None, None)
    except Exception as e:
        # Log error for debugging
        print(f"[team_routes] Error fetching user details for {user_id}: {e}")
        return (None, None)


def _build_invite_url(invite_code: str) -> str:
    """Build the full invite URL."""
    base_url = _get_invite_base_url()
    return f"{base_url}/join/{invite_code}"


def _require_team_membership(
    user: FirebaseUser,
    team_repo: TeamRepository,
) -> tuple[dict, dict]:
    """
    Require that the user is a member of a team.

    Returns:
        Tuple of (team, membership)

    Raises:
        HTTPException 404 if user is not in a team
    """
    membership = team_repo.get_user_membership(user.uid)
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You are not a member of any team",
        )

    team = team_repo.get_team(membership["team_id"])
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found",
        )

    return team, membership


def _require_team_admin(
    user: FirebaseUser,
    team_repo: TeamRepository,
) -> tuple[dict, dict]:
    """
    Require that the user is an admin of their team.

    Returns:
        Tuple of (team, membership)

    Raises:
        HTTPException 404 if not in team, 403 if not admin
    """
    team, membership = _require_team_membership(user, team_repo)

    if membership.get("role") != TeamRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires team admin privileges",
        )

    return team, membership


# =============================================================================
# Team Management
# =============================================================================


@router.post("", response_model=TeamResponse)
def create_team(
    payload: TeamCreate,
    user: FirebaseUser = Depends(get_current_user),
    team_repo: TeamRepository = Depends(get_team_repo),
) -> TeamResponse:
    """Create a new team. The creator becomes the owner and admin."""
    # Check if user is already in a team
    existing = team_repo.get_user_membership(user.uid)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are already a member of a team. Leave your current team first.",
        )

    team = team_repo.create_team(name=payload.name.strip(), owner_id=user.uid)
    return TeamResponse(**team)


@router.get("/me", response_model=TeamMembershipResponse)
def get_my_team(
    user: FirebaseUser = Depends(get_current_user),
    team_repo: TeamRepository = Depends(get_team_repo),
) -> TeamMembershipResponse:
    """Get the current user's team membership status."""
    membership = team_repo.get_user_membership(user.uid)

    if not membership:
        return TeamMembershipResponse(
            team=None,
            membership=None,
            is_member=False,
            is_admin=False,
        )

    team = team_repo.get_team(membership["team_id"])
    if not team:
        return TeamMembershipResponse(
            team=None,
            membership=None,
            is_member=False,
            is_admin=False,
        )

    return TeamMembershipResponse(
        team=TeamResponse(**team),
        membership=membership,
        is_member=True,
        is_admin=membership.get("role") == TeamRole.ADMIN.value,
    )


@router.put("/me", response_model=TeamResponse)
def update_my_team(
    payload: TeamUpdate,
    user: FirebaseUser = Depends(get_current_user),
    team_repo: TeamRepository = Depends(get_team_repo),
) -> TeamResponse:
    """Update the current user's team. Requires admin role."""
    team, _ = _require_team_admin(user, team_repo)

    updated = team_repo.update_team(team["id"], {"name": payload.name.strip()})
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update team",
        )

    return TeamResponse(**updated)


@router.delete("/me")
def leave_team(
    user: FirebaseUser = Depends(get_current_user),
    team_repo: TeamRepository = Depends(get_team_repo),
) -> dict:
    """Leave the current team."""
    team, membership = _require_team_membership(user, team_repo)

    # Check if user is the owner
    if team["owner_id"] == user.uid:
        # Get other admins
        members = team_repo.list_team_members(team["id"])
        other_admins = [
            m for m in members
            if m["user_id"] != user.uid and m["role"] == TeamRole.ADMIN.value
        ]

        if not other_admins:
            # Check if there are other members
            other_members = [m for m in members if m["user_id"] != user.uid]
            if other_members:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="As the owner, you must promote another admin before leaving, or remove all other members first.",
                )
            # No other members, delete the team
            team_repo.delete_team(team["id"])
            return {"status": "team_deleted", "message": "You were the last member. Team has been deleted."}

        # Transfer ownership to another admin
        new_owner = other_admins[0]
        team_repo.update_team(team["id"], {"owner_id": new_owner["user_id"]})

    # Remove the user from the team
    team_repo.remove_member(team["id"], user.uid)

    return {"status": "left", "message": "You have left the team."}


# =============================================================================
# Member Management
# =============================================================================


@router.get("/me/members", response_model=list[TeamMemberResponse])
def list_members(
    user: FirebaseUser = Depends(get_current_user),
    team_repo: TeamRepository = Depends(get_team_repo),
) -> list[TeamMemberResponse]:
    """List all members of the current user's team."""
    team, _ = _require_team_membership(user, team_repo)

    members = team_repo.list_team_members(team["id"])

    result = []
    for m in members:
        email, name = _get_user_details(m["user_id"])
        result.append(
            TeamMemberResponse(
                user_id=m["user_id"],
                email=email,
                name=name,
                role=TeamRole(m["role"]),
                joined_at=m["joined_at"],
                is_owner=m["user_id"] == team["owner_id"],
            )
        )
    return result


@router.put("/me/members/{member_user_id}/role", response_model=TeamMemberResponse)
def update_member_role(
    member_user_id: str,
    payload: UpdateMemberRoleRequest,
    user: FirebaseUser = Depends(get_current_user),
    team_repo: TeamRepository = Depends(get_team_repo),
) -> TeamMemberResponse:
    """Update a member's role. Requires admin role."""
    team, _ = _require_team_admin(user, team_repo)

    # Cannot change owner's role
    if member_user_id == team["owner_id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change the owner's role",
        )

    # Cannot demote yourself if you're the last admin
    if member_user_id == user.uid and payload.role == TeamRole.MEMBER:
        members = team_repo.list_team_members(team["id"])
        admin_count = sum(1 for m in members if m["role"] == TeamRole.ADMIN.value)
        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot demote yourself. Promote another admin first.",
            )

    updated = team_repo.update_member_role(team["id"], member_user_id, payload.role.value)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found",
        )

    email, name = _get_user_details(updated["user_id"])
    return TeamMemberResponse(
        user_id=updated["user_id"],
        email=email,
        name=name,
        role=TeamRole(updated["role"]),
        joined_at=updated["joined_at"],
        is_owner=updated["user_id"] == team["owner_id"],
    )


@router.delete("/me/members/{member_user_id}")
def remove_member(
    member_user_id: str,
    user: FirebaseUser = Depends(get_current_user),
    team_repo: TeamRepository = Depends(get_team_repo),
) -> dict:
    """Remove a member from the team. Requires admin role."""
    team, _ = _require_team_admin(user, team_repo)

    # Cannot remove the owner
    if member_user_id == team["owner_id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove the team owner",
        )

    # Cannot remove yourself via this endpoint
    if member_user_id == user.uid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use DELETE /teams/me to leave the team",
        )

    removed = team_repo.remove_member(team["id"], member_user_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found",
        )

    return {"status": "removed", "user_id": member_user_id}


# =============================================================================
# Invite Management
# =============================================================================


@router.post("/me/invites", response_model=TeamInviteResponse)
def create_invite(
    payload: CreateInviteRequest = CreateInviteRequest(),
    user: FirebaseUser = Depends(get_current_user),
    team_repo: TeamRepository = Depends(get_team_repo),
) -> TeamInviteResponse:
    """Create an invite link for the team. Requires admin role."""
    team, _ = _require_team_admin(user, team_repo)

    invite = team_repo.create_invite(
        team_id=team["id"],
        created_by=user.uid,
        max_uses=payload.max_uses,
        expires_hours=payload.expires_hours,
    )

    return TeamInviteResponse(
        **invite,
        invite_url=_build_invite_url(invite["id"]),
    )


@router.get("/me/invites", response_model=list[TeamInviteResponse])
def list_invites(
    user: FirebaseUser = Depends(get_current_user),
    team_repo: TeamRepository = Depends(get_team_repo),
) -> list[TeamInviteResponse]:
    """List all active invites for the team. Requires admin role."""
    team, _ = _require_team_admin(user, team_repo)

    invites = team_repo.list_team_invites(team["id"], active_only=True)

    return [
        TeamInviteResponse(
            **invite,
            invite_url=_build_invite_url(invite["id"]),
        )
        for invite in invites
    ]


@router.delete("/me/invites/{invite_code}")
def revoke_invite(
    invite_code: str,
    user: FirebaseUser = Depends(get_current_user),
    team_repo: TeamRepository = Depends(get_team_repo),
) -> dict:
    """Revoke an invite link. Requires admin role."""
    team, _ = _require_team_admin(user, team_repo)

    invite = team_repo.get_invite(invite_code)
    if not invite or invite["team_id"] != team["id"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invite not found",
        )

    team_repo.deactivate_invite(invite_code)
    return {"status": "revoked", "invite_code": invite_code}


# =============================================================================
# Join Team
# =============================================================================


@router.post("/join", response_model=TeamResponse)
def join_team(
    payload: JoinTeamRequest,
    user: FirebaseUser = Depends(get_current_user),
    team_repo: TeamRepository = Depends(get_team_repo),
) -> TeamResponse:
    """Join a team using an invite code."""
    # Check if user is already in a team
    existing = team_repo.get_user_membership(user.uid)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are already a member of a team. Leave your current team first.",
        )

    # Validate the invite
    is_valid, error_message, invite = team_repo.validate_invite(payload.invite_code)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message,
        )

    # Get the team
    team = team_repo.get_team(invite["team_id"])
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found",
        )

    # Add the user as a member
    team_repo.add_member(
        team_id=team["id"],
        user_id=user.uid,
        role=TeamRole.MEMBER.value,
        invited_by=invite["created_by"],
    )

    # Increment invite use count
    team_repo.use_invite(payload.invite_code)

    # Update member count
    team_repo._update_member_count(team["id"])

    # Refresh team data
    team = team_repo.get_team(team["id"])

    return TeamResponse(**team)


@router.get("/invite/{invite_code}")
def get_invite_info(
    invite_code: str,
    user: Optional[FirebaseUser] = Depends(get_current_user),
    team_repo: TeamRepository = Depends(get_team_repo),
) -> dict:
    """Get information about an invite (for preview before joining)."""
    is_valid, error_message, invite = team_repo.validate_invite(invite_code)

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message,
        )

    team = team_repo.get_team(invite["team_id"])
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found",
        )

    # Check if user is already in a team
    already_in_team = False
    current_team_name = None
    if user:
        existing = team_repo.get_user_membership(user.uid)
        if existing:
            already_in_team = True
            current_team = team_repo.get_team(existing["team_id"])
            current_team_name = current_team["name"] if current_team else None

    return {
        "team_name": team["name"],
        "member_count": team["member_count"],
        "is_valid": True,
        "already_in_team": already_in_team,
        "current_team_name": current_team_name,
    }
