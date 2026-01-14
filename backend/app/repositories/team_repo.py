"""
Team Repository

Repository implementation for team management using Firestore.

Collections:
    teams/{team_id}                  - Team metadata
    team_memberships/{membership_id} - User-team relationships
    team_invites/{invite_code}       - Shareable invite links
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import uuid4

import firebase_admin
from firebase_admin import firestore
from google.cloud.firestore_v1 import FieldFilter

from app.schemas.team_models import MembershipStatus, TeamRole


class TeamRepository:
    """Repository for team-related operations."""

    def __init__(self) -> None:
        if not firebase_admin._apps:
            firebase_admin.initialize_app()

        self.db = firestore.client()

        # Collection references
        self.teams_collection = "teams"
        self.memberships_collection = "team_memberships"
        self.invites_collection = "team_invites"

    # =========================================================================
    # Team CRUD
    # =========================================================================

    def create_team(self, name: str, owner_id: str) -> dict[str, Any]:
        """
        Create a new team and add the creator as admin/owner.

        Args:
            name: Team display name
            owner_id: User ID of the team creator

        Returns:
            Created team data
        """
        now = datetime.now(timezone.utc).isoformat()
        team_id = str(uuid4())

        team_data = {
            "id": team_id,
            "name": name,
            "owner_id": owner_id,
            "created_at": now,
            "updated_at": now,
            "member_count": 1,
        }

        # Create team document
        self.db.collection(self.teams_collection).document(team_id).set(team_data)

        # Add creator as admin member
        self.add_member(
            team_id=team_id,
            user_id=owner_id,
            role=TeamRole.ADMIN.value,
            invited_by=None,
        )

        return team_data

    def get_team(self, team_id: str) -> Optional[dict[str, Any]]:
        """
        Get a team by ID.

        Args:
            team_id: Team's unique identifier

        Returns:
            Team data or None if not found
        """
        doc = self.db.collection(self.teams_collection).document(team_id).get()
        if not doc.exists:
            return None
        return doc.to_dict()

    def update_team(self, team_id: str, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        """
        Update a team's data.

        Args:
            team_id: Team's unique identifier
            data: Fields to update

        Returns:
            Updated team data or None if not found
        """
        doc_ref = self.db.collection(self.teams_collection).document(team_id)
        doc = doc_ref.get()

        if not doc.exists:
            return None

        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        doc_ref.update(data)

        return doc_ref.get().to_dict()

    def delete_team(self, team_id: str) -> bool:
        """
        Delete a team and all associated memberships and invites.

        Args:
            team_id: Team's unique identifier

        Returns:
            True if deleted, False otherwise
        """
        doc_ref = self.db.collection(self.teams_collection).document(team_id)
        doc = doc_ref.get()

        if not doc.exists:
            return False

        # Delete all memberships
        memberships = self.db.collection(self.memberships_collection).where(
            filter=FieldFilter("team_id", "==", team_id)
        )
        for membership in memberships.stream():
            membership.reference.delete()

        # Delete all invites
        invites = self.db.collection(self.invites_collection).where(
            filter=FieldFilter("team_id", "==", team_id)
        )
        for invite in invites.stream():
            invite.reference.delete()

        # Delete team
        doc_ref.delete()
        return True

    # =========================================================================
    # Membership Operations
    # =========================================================================

    def add_member(
        self,
        team_id: str,
        user_id: str,
        role: str,
        invited_by: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Add a member to a team.

        Args:
            team_id: Team's unique identifier
            user_id: New member's user ID
            role: Member's role ("admin" or "member")
            invited_by: User ID of who invited them (None for creator)

        Returns:
            Created membership data
        """
        now = datetime.now(timezone.utc).isoformat()
        membership_id = str(uuid4())

        membership_data = {
            "id": membership_id,
            "team_id": team_id,
            "user_id": user_id,
            "role": role,
            "joined_at": now,
            "invited_by": invited_by,
            "status": MembershipStatus.ACTIVE.value,
        }

        self.db.collection(self.memberships_collection).document(membership_id).set(
            membership_data
        )

        return membership_data

    def remove_member(self, team_id: str, user_id: str) -> bool:
        """
        Remove a member from a team.

        Args:
            team_id: Team's unique identifier
            user_id: Member's user ID to remove

        Returns:
            True if removed, False otherwise
        """
        query = (
            self.db.collection(self.memberships_collection)
            .where(filter=FieldFilter("team_id", "==", team_id))
            .where(filter=FieldFilter("user_id", "==", user_id))
            .where(filter=FieldFilter("status", "==", MembershipStatus.ACTIVE.value))
            .limit(1)
        )

        docs = list(query.stream())
        if not docs:
            return False

        docs[0].reference.delete()

        # Update member count
        self._update_member_count(team_id)

        return True

    def update_member_role(
        self,
        team_id: str,
        user_id: str,
        role: str,
    ) -> Optional[dict[str, Any]]:
        """
        Update a member's role.

        Args:
            team_id: Team's unique identifier
            user_id: Member's user ID
            role: New role

        Returns:
            Updated membership data or None if not found
        """
        query = (
            self.db.collection(self.memberships_collection)
            .where(filter=FieldFilter("team_id", "==", team_id))
            .where(filter=FieldFilter("user_id", "==", user_id))
            .where(filter=FieldFilter("status", "==", MembershipStatus.ACTIVE.value))
            .limit(1)
        )

        docs = list(query.stream())
        if not docs:
            return None

        doc_ref = docs[0].reference
        doc_ref.update({"role": role})

        return doc_ref.get().to_dict()

    def get_user_team(self, user_id: str) -> Optional[dict[str, Any]]:
        """
        Get the team a user belongs to.

        Args:
            user_id: User's unique identifier

        Returns:
            Team data or None if user is not in a team
        """
        membership = self.get_user_membership(user_id)
        if not membership:
            return None

        return self.get_team(membership["team_id"])

    def get_user_membership(self, user_id: str) -> Optional[dict[str, Any]]:
        """
        Get a user's active team membership.

        Args:
            user_id: User's unique identifier

        Returns:
            Membership data or None if not in a team
        """
        query = (
            self.db.collection(self.memberships_collection)
            .where(filter=FieldFilter("user_id", "==", user_id))
            .where(filter=FieldFilter("status", "==", MembershipStatus.ACTIVE.value))
            .limit(1)
        )

        docs = list(query.stream())
        if not docs:
            return None

        return docs[0].to_dict()

    def list_team_members(self, team_id: str) -> list[dict[str, Any]]:
        """
        List all members of a team.

        Args:
            team_id: Team's unique identifier

        Returns:
            List of membership data
        """
        query = (
            self.db.collection(self.memberships_collection)
            .where(filter=FieldFilter("team_id", "==", team_id))
            .where(filter=FieldFilter("status", "==", MembershipStatus.ACTIVE.value))
        )

        return [doc.to_dict() for doc in query.stream()]

    def get_team_member_ids(self, team_id: str) -> list[str]:
        """
        Get all user IDs for a team.

        Used for team-scoped data queries.

        Args:
            team_id: Team's unique identifier

        Returns:
            List of user IDs
        """
        members = self.list_team_members(team_id)
        return [m["user_id"] for m in members]

    def _update_member_count(self, team_id: str) -> None:
        """Update the denormalized member count on a team."""
        count = len(self.list_team_members(team_id))
        self.db.collection(self.teams_collection).document(team_id).update(
            {"member_count": count}
        )

    # =========================================================================
    # Invite Operations
    # =========================================================================

    def create_invite(
        self,
        team_id: str,
        created_by: str,
        max_uses: int = 0,
        expires_hours: Optional[int] = None,
    ) -> dict[str, Any]:
        """
        Create an invite link for a team.

        Args:
            team_id: Team's unique identifier
            created_by: User ID creating the invite
            max_uses: Maximum uses (0 = unlimited)
            expires_hours: Hours until expiration (None = no expiry)

        Returns:
            Created invite data
        """
        now = datetime.now(timezone.utc)
        invite_code = secrets.token_urlsafe(16)

        expires_at = None
        if expires_hours:
            expires_at = (now + timedelta(hours=expires_hours)).isoformat()

        invite_data = {
            "id": invite_code,
            "team_id": team_id,
            "created_by": created_by,
            "created_at": now.isoformat(),
            "expires_at": expires_at,
            "max_uses": max_uses,
            "use_count": 0,
            "is_active": True,
        }

        self.db.collection(self.invites_collection).document(invite_code).set(
            invite_data
        )

        return invite_data

    def get_invite(self, invite_code: str) -> Optional[dict[str, Any]]:
        """
        Get an invite by code.

        Args:
            invite_code: The invite code

        Returns:
            Invite data or None if not found
        """
        doc = self.db.collection(self.invites_collection).document(invite_code).get()
        if not doc.exists:
            return None
        return doc.to_dict()

    def validate_invite(self, invite_code: str) -> tuple[bool, str, Optional[dict]]:
        """
        Validate an invite code.

        Args:
            invite_code: The invite code to validate

        Returns:
            Tuple of (is_valid, error_message, invite_data)
        """
        invite = self.get_invite(invite_code)

        if not invite:
            return False, "Invite not found", None

        if not invite.get("is_active"):
            return False, "This invite has been revoked", None

        # Check expiration
        expires_at = invite.get("expires_at")
        if expires_at:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > expiry:
                return False, "This invite has expired", None

        # Check max uses
        max_uses = invite.get("max_uses", 0)
        use_count = invite.get("use_count", 0)
        if max_uses > 0 and use_count >= max_uses:
            return False, "This invite has reached its maximum uses", None

        return True, "", invite

    def use_invite(self, invite_code: str) -> bool:
        """
        Increment the use count of an invite.

        Args:
            invite_code: The invite code

        Returns:
            True if incremented, False otherwise
        """
        doc_ref = self.db.collection(self.invites_collection).document(invite_code)
        doc = doc_ref.get()

        if not doc.exists:
            return False

        doc_ref.update({"use_count": firestore.Increment(1)})
        return True

    def deactivate_invite(self, invite_code: str) -> bool:
        """
        Deactivate an invite.

        Args:
            invite_code: The invite code

        Returns:
            True if deactivated, False otherwise
        """
        doc_ref = self.db.collection(self.invites_collection).document(invite_code)
        doc = doc_ref.get()

        if not doc.exists:
            return False

        doc_ref.update({"is_active": False})
        return True

    def list_team_invites(self, team_id: str, active_only: bool = True) -> list[dict]:
        """
        List all invites for a team.

        Args:
            team_id: Team's unique identifier
            active_only: Only return active invites

        Returns:
            List of invite data
        """
        query = self.db.collection(self.invites_collection).where(
            filter=FieldFilter("team_id", "==", team_id)
        )

        if active_only:
            query = query.where(filter=FieldFilter("is_active", "==", True))

        return [doc.to_dict() for doc in query.stream()]


# Singleton instance
_team_repo: Optional[TeamRepository] = None


def get_team_repo() -> TeamRepository:
    """Get the singleton TeamRepository instance."""
    global _team_repo
    if _team_repo is None:
        _team_repo = TeamRepository()
    return _team_repo
