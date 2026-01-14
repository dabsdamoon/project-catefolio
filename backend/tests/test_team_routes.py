"""Integration tests for Team API routes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_team_repo():
    """Mock TeamRepository for testing."""
    mock_repo = MagicMock()

    # Default responses - no team membership (solo user)
    mock_repo.get_user_membership.return_value = None
    mock_repo.get_team.return_value = None
    mock_repo.list_team_members.return_value = []
    mock_repo.list_team_invites.return_value = []

    return mock_repo


@pytest.fixture
def team_client(mock_team_repo) -> TestClient:
    """Create test client with mocked team repository."""
    from app.main import app
    from app.repositories.team_repo import get_team_repo

    # Mock Firebase user details lookup function
    def get_user_details(user_id: str):
        if user_id.startswith("demo_"):
            demo_id = user_id.replace("demo_", "", 1)
            return (f"{demo_id}@demo.catefolio.local", f"Demo User ({demo_id})")
        return (f"{user_id}@test.com", f"Test User ({user_id})")

    # Use FastAPI dependency override
    app.dependency_overrides[get_team_repo] = lambda: mock_team_repo

    with patch("app.api.team_routes._get_user_details", side_effect=get_user_details):
        client = TestClient(app)
        # Use demo mode for authentication
        client.headers["X-Demo-User-Id"] = "test-user"
        yield client

    # Clean up override
    app.dependency_overrides.pop(get_team_repo, None)


class TestTeamCreation:
    """Tests for team creation by solo users."""

    def test_create_team_success(self, team_client, mock_team_repo):
        """Solo user can create a new team."""
        now = datetime.now(timezone.utc).isoformat()
        created_team = {
            "id": "team-123",
            "name": "My Test Team",
            "owner_id": "demo_test-user",
            "created_at": now,
            "updated_at": now,
            "member_count": 1,
        }
        mock_team_repo.create_team.return_value = created_team

        response = team_client.post("/teams", json={"name": "My Test Team"})

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "My Test Team"
        assert data["id"] == "team-123"
        mock_team_repo.create_team.assert_called_once()

    def test_create_team_already_in_team(self, team_client, mock_team_repo):
        """User already in a team cannot create another."""
        mock_team_repo.get_user_membership.return_value = {
            "team_id": "existing-team",
            "user_id": "demo_test-user",
            "role": "member",
        }

        response = team_client.post("/teams", json={"name": "New Team"})

        assert response.status_code == 400
        assert "already a member" in response.json()["detail"]

    def test_create_team_empty_name(self, team_client, mock_team_repo):
        """Team name cannot be empty."""
        response = team_client.post("/teams", json={"name": ""})

        assert response.status_code == 422  # Validation error


class TestGetMyTeam:
    """Tests for getting current user's team membership."""

    def test_get_my_team_solo_user(self, team_client, mock_team_repo):
        """Solo user gets empty team membership."""
        mock_team_repo.get_user_membership.return_value = None

        response = team_client.get("/teams/me")

        assert response.status_code == 200
        data = response.json()
        assert data["is_member"] is False
        assert data["is_admin"] is False
        assert data["team"] is None

    def test_get_my_team_member(self, team_client, mock_team_repo):
        """Team member gets their membership info."""
        mock_team_repo.get_user_membership.return_value = {
            "team_id": "team-123",
            "user_id": "demo_test-user",
            "role": "member",
            "joined_at": datetime.now(timezone.utc).isoformat(),
        }
        mock_team_repo.get_team.return_value = {
            "id": "team-123",
            "name": "Test Team",
            "owner_id": "owner-user",
            "member_count": 3,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        response = team_client.get("/teams/me")

        assert response.status_code == 200
        data = response.json()
        assert data["is_member"] is True
        assert data["is_admin"] is False
        assert data["team"]["name"] == "Test Team"

    def test_get_my_team_admin(self, team_client, mock_team_repo):
        """Team admin gets admin flag."""
        mock_team_repo.get_user_membership.return_value = {
            "team_id": "team-123",
            "user_id": "demo_test-user",
            "role": "admin",
            "joined_at": datetime.now(timezone.utc).isoformat(),
        }
        mock_team_repo.get_team.return_value = {
            "id": "team-123",
            "name": "Test Team",
            "owner_id": "demo_test-user",
            "member_count": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        response = team_client.get("/teams/me")

        assert response.status_code == 200
        data = response.json()
        assert data["is_member"] is True
        assert data["is_admin"] is True


class TestInviteGeneration:
    """Tests for invite link generation."""

    def test_create_invite_as_admin(self, team_client, mock_team_repo):
        """Admin can create invite links."""
        now = datetime.now(timezone.utc).isoformat()
        mock_team_repo.get_user_membership.return_value = {
            "team_id": "team-123",
            "user_id": "demo_test-user",
            "role": "admin",
        }
        mock_team_repo.get_team.return_value = {
            "id": "team-123",
            "name": "Test Team",
            "owner_id": "demo_test-user",
            "member_count": 1,
            "created_at": now,
            "updated_at": now,
        }
        mock_team_repo.create_invite.return_value = {
            "id": "invite-abc123",
            "team_id": "team-123",
            "created_by": "demo_test-user",
            "created_at": now,
            "expires_at": None,
            "max_uses": 0,
            "use_count": 0,
            "is_active": True,
        }

        response = team_client.post("/teams/me/invites")

        assert response.status_code == 200
        data = response.json()
        assert "invite_url" in data
        assert data["is_active"] is True
        mock_team_repo.create_invite.assert_called_once()

    def test_create_invite_as_member_forbidden(self, team_client, mock_team_repo):
        """Regular member cannot create invites."""
        mock_team_repo.get_user_membership.return_value = {
            "team_id": "team-123",
            "user_id": "demo_test-user",
            "role": "member",  # Not admin
        }
        mock_team_repo.get_team.return_value = {
            "id": "team-123",
            "name": "Test Team",
            "owner_id": "other-user",
            "member_count": 2,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        response = team_client.post("/teams/me/invites")

        assert response.status_code == 403
        assert "admin" in response.json()["detail"].lower()

    def test_list_invites_as_admin(self, team_client, mock_team_repo):
        """Admin can list team invites."""
        now = datetime.now(timezone.utc).isoformat()
        mock_team_repo.get_user_membership.return_value = {
            "team_id": "team-123",
            "user_id": "demo_test-user",
            "role": "admin",
        }
        mock_team_repo.get_team.return_value = {
            "id": "team-123",
            "name": "Test Team",
            "owner_id": "demo_test-user",
            "member_count": 1,
            "created_at": now,
            "updated_at": now,
        }
        mock_team_repo.list_team_invites.return_value = [
            {
                "id": "invite-1",
                "team_id": "team-123",
                "created_by": "demo_test-user",
                "created_at": now,
                "expires_at": None,
                "max_uses": 0,
                "use_count": 2,
                "is_active": True,
            }
        ]

        response = team_client.get("/teams/me/invites")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["use_count"] == 2


class TestJoinTeam:
    """Tests for joining a team via invite."""

    def test_join_team_success(self, team_client, mock_team_repo):
        """User can join team with valid invite."""
        now = datetime.now(timezone.utc).isoformat()
        mock_team_repo.get_user_membership.return_value = None  # Not in a team
        mock_team_repo.validate_invite.return_value = (
            True,
            "",
            {
                "id": "invite-abc",
                "team_id": "team-123",
                "created_by": "owner-user",
                "is_active": True,
            },
        )
        mock_team_repo.get_team.return_value = {
            "id": "team-123",
            "name": "Join This Team",
            "owner_id": "owner-user",
            "member_count": 2,
            "created_at": now,
            "updated_at": now,
        }
        mock_team_repo.add_member.return_value = {
            "id": "membership-456",
            "team_id": "team-123",
            "user_id": "demo_test-user",
            "role": "member",
            "joined_at": now,
        }

        response = team_client.post("/teams/join", json={"invite_code": "invite-abc"})

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Join This Team"
        mock_team_repo.add_member.assert_called_once()
        mock_team_repo.use_invite.assert_called_once_with("invite-abc")

    def test_join_team_already_in_team(self, team_client, mock_team_repo):
        """User already in a team cannot join another."""
        mock_team_repo.get_user_membership.return_value = {
            "team_id": "existing-team",
            "user_id": "demo_test-user",
            "role": "member",
        }

        response = team_client.post("/teams/join", json={"invite_code": "invite-abc"})

        assert response.status_code == 400
        assert "already a member" in response.json()["detail"]

    def test_join_team_invalid_invite(self, team_client, mock_team_repo):
        """Cannot join with invalid invite code."""
        mock_team_repo.get_user_membership.return_value = None
        mock_team_repo.validate_invite.return_value = (False, "Invite not found", None)

        response = team_client.post("/teams/join", json={"invite_code": "bad-code"})

        assert response.status_code == 400
        assert "not found" in response.json()["detail"].lower()

    def test_join_team_expired_invite(self, team_client, mock_team_repo):
        """Cannot join with expired invite."""
        mock_team_repo.get_user_membership.return_value = None
        mock_team_repo.validate_invite.return_value = (
            False,
            "This invite has expired",
            None,
        )

        response = team_client.post("/teams/join", json={"invite_code": "expired-code"})

        assert response.status_code == 400
        assert "expired" in response.json()["detail"].lower()


class TestMembersList:
    """Tests for listing team members."""

    def test_list_members_with_details(self, team_client, mock_team_repo):
        """Members list includes email and name from Firebase."""
        now = datetime.now(timezone.utc).isoformat()
        mock_team_repo.get_user_membership.return_value = {
            "team_id": "team-123",
            "user_id": "demo_test-user",
            "role": "member",
        }
        mock_team_repo.get_team.return_value = {
            "id": "team-123",
            "name": "Test Team",
            "owner_id": "demo_owner",
            "member_count": 2,
            "created_at": now,
            "updated_at": now,
        }
        mock_team_repo.list_team_members.return_value = [
            {
                "user_id": "demo_owner",
                "role": "admin",
                "joined_at": now,
            },
            {
                "user_id": "demo_test-user",
                "role": "member",
                "joined_at": now,
            },
        ]

        response = team_client.get("/teams/me/members")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

        # Verify email addresses are returned (from mocked _get_user_details)
        emails = [m["email"] for m in data]
        assert "owner@demo.catefolio.local" in emails
        assert "test-user@demo.catefolio.local" in emails

        # Verify owner flag
        owner = next(m for m in data if m["user_id"] == "demo_owner")
        assert owner["is_owner"] is True

    def test_list_members_not_in_team(self, team_client, mock_team_repo):
        """Solo user cannot list members."""
        mock_team_repo.get_user_membership.return_value = None

        response = team_client.get("/teams/me/members")

        assert response.status_code == 404


class TestMemberRoleChange:
    """Tests for changing member roles (admin only)."""

    def test_promote_member_to_admin(self, team_client, mock_team_repo):
        """Admin can promote member to admin."""
        now = datetime.now(timezone.utc).isoformat()
        mock_team_repo.get_user_membership.return_value = {
            "team_id": "team-123",
            "user_id": "demo_test-user",
            "role": "admin",
        }
        mock_team_repo.get_team.return_value = {
            "id": "team-123",
            "name": "Test Team",
            "owner_id": "demo_test-user",
            "member_count": 2,
            "created_at": now,
            "updated_at": now,
        }
        mock_team_repo.update_member_role.return_value = {
            "user_id": "other-user",
            "role": "admin",
            "joined_at": now,
        }

        response = team_client.put(
            "/teams/me/members/other-user/role",
            json={"role": "admin"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "admin"

    def test_demote_admin_to_member(self, team_client, mock_team_repo):
        """Admin can demote another admin (if not owner)."""
        now = datetime.now(timezone.utc).isoformat()
        mock_team_repo.get_user_membership.return_value = {
            "team_id": "team-123",
            "user_id": "demo_test-user",
            "role": "admin",
        }
        mock_team_repo.get_team.return_value = {
            "id": "team-123",
            "name": "Test Team",
            "owner_id": "demo_test-user",  # Current user is owner
            "member_count": 2,
            "created_at": now,
            "updated_at": now,
        }
        mock_team_repo.update_member_role.return_value = {
            "user_id": "other-admin",
            "role": "member",
            "joined_at": now,
        }

        response = team_client.put(
            "/teams/me/members/other-admin/role",
            json={"role": "member"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "member"

    def test_cannot_change_owner_role(self, team_client, mock_team_repo):
        """Cannot change the owner's role."""
        now = datetime.now(timezone.utc).isoformat()
        mock_team_repo.get_user_membership.return_value = {
            "team_id": "team-123",
            "user_id": "demo_test-user",
            "role": "admin",
        }
        mock_team_repo.get_team.return_value = {
            "id": "team-123",
            "name": "Test Team",
            "owner_id": "the-owner",  # Different user is owner
            "member_count": 2,
            "created_at": now,
            "updated_at": now,
        }

        response = team_client.put(
            "/teams/me/members/the-owner/role",
            json={"role": "member"},
        )

        assert response.status_code == 400
        assert "owner" in response.json()["detail"].lower()

    def test_member_cannot_change_roles(self, team_client, mock_team_repo):
        """Regular member cannot change roles."""
        now = datetime.now(timezone.utc).isoformat()
        mock_team_repo.get_user_membership.return_value = {
            "team_id": "team-123",
            "user_id": "demo_test-user",
            "role": "member",  # Not admin
        }
        mock_team_repo.get_team.return_value = {
            "id": "team-123",
            "name": "Test Team",
            "owner_id": "owner-user",
            "member_count": 2,
            "created_at": now,
            "updated_at": now,
        }

        response = team_client.put(
            "/teams/me/members/other-user/role",
            json={"role": "admin"},
        )

        assert response.status_code == 403


class TestLeaveTeam:
    """Tests for leaving a team."""

    def test_member_leave_team(self, team_client, mock_team_repo):
        """Regular member can leave team."""
        now = datetime.now(timezone.utc).isoformat()
        mock_team_repo.get_user_membership.return_value = {
            "team_id": "team-123",
            "user_id": "demo_test-user",
            "role": "member",
        }
        mock_team_repo.get_team.return_value = {
            "id": "team-123",
            "name": "Test Team",
            "owner_id": "owner-user",  # Different user is owner
            "member_count": 2,
            "created_at": now,
            "updated_at": now,
        }
        mock_team_repo.remove_member.return_value = True

        response = team_client.delete("/teams/me")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "left"
        mock_team_repo.remove_member.assert_called_once()

    def test_owner_leave_with_other_admins(self, team_client, mock_team_repo):
        """Owner can leave if there are other admins."""
        now = datetime.now(timezone.utc).isoformat()
        mock_team_repo.get_user_membership.return_value = {
            "team_id": "team-123",
            "user_id": "demo_test-user",
            "role": "admin",
        }
        mock_team_repo.get_team.return_value = {
            "id": "team-123",
            "name": "Test Team",
            "owner_id": "demo_test-user",  # Current user is owner
            "member_count": 2,
            "created_at": now,
            "updated_at": now,
        }
        mock_team_repo.list_team_members.return_value = [
            {"user_id": "demo_test-user", "role": "admin"},
            {"user_id": "other-admin", "role": "admin"},  # Another admin exists
        ]
        mock_team_repo.remove_member.return_value = True

        response = team_client.delete("/teams/me")

        assert response.status_code == 200
        # Ownership should be transferred
        mock_team_repo.update_team.assert_called()

    def test_owner_cannot_leave_without_other_admins(self, team_client, mock_team_repo):
        """Owner cannot leave if they're the only admin with members."""
        now = datetime.now(timezone.utc).isoformat()
        mock_team_repo.get_user_membership.return_value = {
            "team_id": "team-123",
            "user_id": "demo_test-user",
            "role": "admin",
        }
        mock_team_repo.get_team.return_value = {
            "id": "team-123",
            "name": "Test Team",
            "owner_id": "demo_test-user",
            "member_count": 2,
            "created_at": now,
            "updated_at": now,
        }
        mock_team_repo.list_team_members.return_value = [
            {"user_id": "demo_test-user", "role": "admin"},
            {"user_id": "regular-member", "role": "member"},  # No other admins
        ]

        response = team_client.delete("/teams/me")

        assert response.status_code == 400
        assert "promote another admin" in response.json()["detail"].lower()

    def test_last_member_deletes_team(self, team_client, mock_team_repo):
        """Last member leaving deletes the team."""
        now = datetime.now(timezone.utc).isoformat()
        mock_team_repo.get_user_membership.return_value = {
            "team_id": "team-123",
            "user_id": "demo_test-user",
            "role": "admin",
        }
        mock_team_repo.get_team.return_value = {
            "id": "team-123",
            "name": "Test Team",
            "owner_id": "demo_test-user",
            "member_count": 1,
            "created_at": now,
            "updated_at": now,
        }
        mock_team_repo.list_team_members.return_value = [
            {"user_id": "demo_test-user", "role": "admin"},
        ]
        mock_team_repo.delete_team.return_value = True

        response = team_client.delete("/teams/me")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "team_deleted"
        mock_team_repo.delete_team.assert_called_once_with("team-123")


class TestRemoveMember:
    """Tests for removing team members (admin only)."""

    def test_admin_remove_member(self, team_client, mock_team_repo):
        """Admin can remove a member."""
        now = datetime.now(timezone.utc).isoformat()
        mock_team_repo.get_user_membership.return_value = {
            "team_id": "team-123",
            "user_id": "demo_test-user",
            "role": "admin",
        }
        mock_team_repo.get_team.return_value = {
            "id": "team-123",
            "name": "Test Team",
            "owner_id": "demo_test-user",
            "member_count": 2,
            "created_at": now,
            "updated_at": now,
        }
        mock_team_repo.remove_member.return_value = True

        response = team_client.delete("/teams/me/members/other-member")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "removed"
        assert data["user_id"] == "other-member"

    def test_cannot_remove_owner(self, team_client, mock_team_repo):
        """Cannot remove the team owner."""
        now = datetime.now(timezone.utc).isoformat()
        mock_team_repo.get_user_membership.return_value = {
            "team_id": "team-123",
            "user_id": "demo_test-user",
            "role": "admin",
        }
        mock_team_repo.get_team.return_value = {
            "id": "team-123",
            "name": "Test Team",
            "owner_id": "the-owner",
            "member_count": 2,
            "created_at": now,
            "updated_at": now,
        }

        response = team_client.delete("/teams/me/members/the-owner")

        assert response.status_code == 400
        assert "owner" in response.json()["detail"].lower()

    def test_cannot_remove_self(self, team_client, mock_team_repo):
        """Cannot use remove endpoint to leave (use DELETE /teams/me instead)."""
        now = datetime.now(timezone.utc).isoformat()
        mock_team_repo.get_user_membership.return_value = {
            "team_id": "team-123",
            "user_id": "demo_test-user",
            "role": "admin",
        }
        mock_team_repo.get_team.return_value = {
            "id": "team-123",
            "name": "Test Team",
            "owner_id": "other-owner",
            "member_count": 2,
            "created_at": now,
            "updated_at": now,
        }

        response = team_client.delete("/teams/me/members/demo_test-user")

        assert response.status_code == 400
        assert "DELETE /teams/me" in response.json()["detail"]


class TestInviteInfo:
    """Tests for getting invite information."""

    def test_get_invite_info_valid(self, team_client, mock_team_repo):
        """Can get info about valid invite."""
        now = datetime.now(timezone.utc).isoformat()
        mock_team_repo.get_user_membership.return_value = None
        mock_team_repo.validate_invite.return_value = (
            True,
            "",
            {
                "id": "invite-abc",
                "team_id": "team-123",
            },
        )
        mock_team_repo.get_team.return_value = {
            "id": "team-123",
            "name": "Joinable Team",
            "owner_id": "owner",
            "member_count": 5,
            "created_at": now,
            "updated_at": now,
        }

        response = team_client.get("/teams/invite/invite-abc")

        assert response.status_code == 200
        data = response.json()
        assert data["team_name"] == "Joinable Team"
        assert data["member_count"] == 5
        assert data["is_valid"] is True
        assert data["already_in_team"] is False

    def test_get_invite_info_already_in_team(self, team_client, mock_team_repo):
        """Shows warning if user already in a team."""
        now = datetime.now(timezone.utc).isoformat()
        mock_team_repo.get_user_membership.return_value = {
            "team_id": "current-team",
            "user_id": "demo_test-user",
            "role": "member",
        }
        mock_team_repo.validate_invite.return_value = (
            True,
            "",
            {
                "id": "invite-abc",
                "team_id": "team-123",
            },
        )
        mock_team_repo.get_team.side_effect = lambda team_id: {
            "team-123": {
                "id": "team-123",
                "name": "New Team",
                "owner_id": "owner",
                "member_count": 3,
                "created_at": now,
                "updated_at": now,
            },
            "current-team": {
                "id": "current-team",
                "name": "Current Team",
                "owner_id": "other",
                "member_count": 2,
                "created_at": now,
                "updated_at": now,
            },
        }.get(team_id)

        response = team_client.get("/teams/invite/invite-abc")

        assert response.status_code == 200
        data = response.json()
        assert data["already_in_team"] is True
        assert data["current_team_name"] == "Current Team"

    def test_get_invite_info_invalid(self, team_client, mock_team_repo):
        """Invalid invite returns error."""
        mock_team_repo.validate_invite.return_value = (
            False,
            "Invite not found",
            None,
        )

        response = team_client.get("/teams/invite/bad-code")

        assert response.status_code == 400


class TestRevokeInvite:
    """Tests for revoking invites."""

    def test_revoke_invite_success(self, team_client, mock_team_repo):
        """Admin can revoke an invite."""
        now = datetime.now(timezone.utc).isoformat()
        mock_team_repo.get_user_membership.return_value = {
            "team_id": "team-123",
            "user_id": "demo_test-user",
            "role": "admin",
        }
        mock_team_repo.get_team.return_value = {
            "id": "team-123",
            "name": "Test Team",
            "owner_id": "demo_test-user",
            "member_count": 1,
            "created_at": now,
            "updated_at": now,
        }
        mock_team_repo.get_invite.return_value = {
            "id": "invite-abc",
            "team_id": "team-123",
            "is_active": True,
        }

        response = team_client.delete("/teams/me/invites/invite-abc")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "revoked"
        mock_team_repo.deactivate_invite.assert_called_once_with("invite-abc")

    def test_revoke_other_team_invite_fails(self, team_client, mock_team_repo):
        """Cannot revoke invite from another team."""
        now = datetime.now(timezone.utc).isoformat()
        mock_team_repo.get_user_membership.return_value = {
            "team_id": "team-123",
            "user_id": "demo_test-user",
            "role": "admin",
        }
        mock_team_repo.get_team.return_value = {
            "id": "team-123",
            "name": "Test Team",
            "owner_id": "demo_test-user",
            "member_count": 1,
            "created_at": now,
            "updated_at": now,
        }
        mock_team_repo.get_invite.return_value = {
            "id": "invite-xyz",
            "team_id": "other-team",  # Different team
            "is_active": True,
        }

        response = team_client.delete("/teams/me/invites/invite-xyz")

        assert response.status_code == 404
