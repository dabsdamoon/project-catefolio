# Team Feature Implementation Plan

## Overview

This plan outlines the implementation of a team collaboration feature for Catefolio, allowing users to share transaction data, entities, and categories within a team.

### Requirements

| Requirement | Decision |
|------------|----------|
| Data Sharing | Share all data (jobs, transactions, entities, categories) within team |
| Membership | Invite via shareable link |
| Multi-team | Single team only per user |
| Roles | Admin & Member (two-tier) |
| Initial Admin | Team creator becomes Owner and Admin |

---

## 1. Firebase Data Schema

### 1.1 New Collections

#### `teams` Collection

```
teams/{team_id}
├── id: string                    # Same as document ID
├── name: string                  # Team display name
├── owner_id: string              # UID of team creator (Admin)
├── created_at: string            # ISO timestamp
├── updated_at: string            # ISO timestamp
└── member_count: number          # Denormalized count for display
```

#### `team_memberships` Collection

```
team_memberships/{membership_id}
├── id: string                    # Same as document ID
├── team_id: string               # Reference to teams collection
├── user_id: string               # Firebase Auth UID
├── role: "admin" | "member"      # User's role in the team
├── joined_at: string             # ISO timestamp
├── invited_by: string            # UID of user who invited (nullable for creator)
└── status: "active" | "pending"  # Membership status
```

**Required Indexes:**
- `user_id` + `status` (finding user's active team)
- `team_id` + `status` (listing team members)

#### `team_invites` Collection

```
team_invites/{invite_code}
├── id: string                    # Same as document ID (the shareable code)
├── team_id: string               # Reference to teams collection
├── created_by: string            # UID of invite creator
├── created_at: string            # ISO timestamp
├── expires_at: string | null     # Optional expiry timestamp
├── max_uses: number              # Maximum uses (0 = unlimited)
├── use_count: number             # Current usage count
└── is_active: boolean            # Can be deactivated by admin
```

### 1.2 Data Ownership Approach

The existing collections (`jobs`, `entities`, `categories`) **retain their `user_id` field**. The key insight:

- `user_id` identifies the **owner** of the data
- **Access scope** is determined by team membership

**Query Logic:**
- If user is in a team → query data for ALL team member `user_id` values
- If user is solo → query only their own `user_id`

**Benefits:**
- No migration of existing data required
- Data attribution preserved (who uploaded what)
- Users leaving teams retain their data
- Enables "uploaded by" attribution

### 1.3 Team Creation Flow

When a user creates a team:

1. **Create team document** in `teams` collection:
   - `owner_id` = creator's `user_id`
   - `member_count` = 1

2. **Create membership document** in `team_memberships`:
   - `user_id` = creator's `user_id`
   - `team_id` = new team's ID
   - `role` = "admin"
   - `invited_by` = null (self-created)
   - `status` = "active"

The creator is automatically the **Owner** (cannot be removed without transferring ownership) and **Admin** (can manage team settings, members, invites).

---

## 2. UI/UX Design

### 2.1 Navigation Update

Add "Team" to the sidebar navigation (after Exports):

```
┌─────────────────────┐
│  Dashboard          │
│  Upload Data        │
│  Categories         │
│  Exports            │
│  Team           👥3 │  ← New navigation item with member count badge
└─────────────────────┘
```

Add team indicator in user section:

```
┌─────────────────────┐
│  👥 Finance Team    │  ← Team name indicator
├─────────────────────┤
│  Avatar  John Doe   │
│          Sign Out   │
└─────────────────────┘
```

### 2.2 Team Page - No Team State

```
┌──────────────────────────────────────────────────────┐
│  Team                                                │
├──────────────────────────────────────────────────────┤
│                                                      │
│  You're not part of a team yet                       │
│                                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │  Create a New Team                             │  │
│  │                                                │  │
│  │  Team Name: [_____________________________]    │  │
│  │                                                │  │
│  │  [Create Team]                                 │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  ─────────────── or ───────────────                  │
│                                                      │
│  Have an invite link?                                │
│  [________________________________] [Join Team]     │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### 2.3 Team Page - Admin View

```
┌──────────────────────────────────────────────────────┐
│  Team: Finance Team                          [Edit]  │
├──────────────────────────────────────────────────────┤
│                                                      │
│  Members (3)                                         │
│  ┌────────────────────────────────────────────────┐  │
│  │  👤  john@email.com         Admin     (Owner)  │  │
│  │  👤  jane@email.com         Member    [▼] [×]  │  │
│  │  👤  bob@email.com          Member    [▼] [×]  │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  Invite Members                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │  [Generate Invite Link]                        │  │
│  │                                                │  │
│  │  Active Invites:                               │  │
│  │  ┌──────────────────────────────────────────┐  │  │
│  │  │ Created Jan 10  •  2/10 uses  [Copy][×]  │  │  │
│  │  │ Created Jan 12  •  0/∞ uses   [Copy][×]  │  │  │
│  │  └──────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  ────────────────────────────────────                │
│                                                      │
│  [Leave Team]                                        │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### 2.4 Team Page - Member View

```
┌──────────────────────────────────────────────────────┐
│  Team: Finance Team                                  │
├──────────────────────────────────────────────────────┤
│                                                      │
│  Members (3)                                         │
│  ┌────────────────────────────────────────────────┐  │
│  │  👤  john@email.com         Admin     (Owner)  │  │
│  │  👤  jane@email.com         Member    (You)    │  │
│  │  👤  bob@email.com          Member             │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  ────────────────────────────────────                │
│                                                      │
│  [Leave Team]                                        │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### 2.5 Join Team Page (Route: `/join/:inviteCode`)

```
┌──────────────────────────────────────────────────────┐
│                                                      │
│            You've been invited to join               │
│                                                      │
│                  Finance Team                        │
│                   3 members                          │
│                                                      │
│              [Join Team]                             │
│                                                      │
│              ← Back to Dashboard                     │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### 2.6 Error States

**Already in a team:**
```
You're already a member of "Marketing Team".
Leave your current team to join a new one.
[Go to Team Settings]
```

**Invalid invite:**
```
This invite link is no longer valid.
It may have expired or been revoked.
[Go to Dashboard]
```

**Invite exhausted:**
```
This invite link has reached its maximum uses.
Ask your team admin for a new invite.
[Go to Dashboard]
```

---

## 3. Backend API Design

### 3.1 New Endpoints

| Method | Path | Description | Role Required |
|--------|------|-------------|---------------|
| POST | `/teams` | Create a new team | Any |
| GET | `/teams/me` | Get current user's team | Any |
| PUT | `/teams/me` | Update team name | Admin |
| DELETE | `/teams/me` | Leave current team | Any |
| GET | `/teams/me/members` | List team members | Any |
| PUT | `/teams/me/members/{id}/role` | Change member role | Admin |
| DELETE | `/teams/me/members/{id}` | Remove member | Admin |
| POST | `/teams/me/invites` | Create invite link | Admin |
| GET | `/teams/me/invites` | List active invites | Admin |
| DELETE | `/teams/me/invites/{code}` | Revoke invite | Admin |
| POST | `/teams/join` | Join team via invite code | Any |

### 3.2 Response Models

```python
class TeamRole(str, Enum):
    ADMIN = "admin"
    MEMBER = "member"

class TeamResponse(BaseModel):
    id: str
    name: str
    owner_id: str
    created_at: str
    member_count: int

class TeamMemberResponse(BaseModel):
    user_id: str
    email: str | None
    name: str | None
    role: TeamRole
    joined_at: str
    is_owner: bool

class TeamInviteResponse(BaseModel):
    id: str                    # The invite code
    team_id: str
    created_at: str
    expires_at: str | None
    max_uses: int
    use_count: int
    is_active: bool
    invite_url: str            # Full URL for sharing

class JoinTeamRequest(BaseModel):
    invite_code: str
```

### 3.3 Modified Existing Endpoints

These endpoints need to query data across team member `user_id`s:

- `GET /jobs` - List jobs for user or team
- `GET /transactions` - Get all transactions for user or team
- `GET /entities` - List entities for user or team
- `GET /categories` - Get categories (user-specific, then team, then default)

**Implementation approach:**

```python
def get_data_scope_user_ids(user: FirebaseUser, team_repo: TeamRepository) -> list[str]:
    """Get list of user_ids the current user can access."""
    membership = team_repo.get_user_membership(user.uid)
    if membership and membership["status"] == "active":
        return team_repo.get_team_member_ids(membership["team_id"])
    return [user.uid]
```

---

## 4. Implementation Phases

### Phase 1: Backend Foundation
- Create Pydantic models for teams
- Implement `TeamRepository` class
- Create team API routes
- Add unit tests

### Phase 2: Invite System
- Implement secure invite code generation
- Invite validation and usage tracking
- Invite management endpoints

### Phase 3: Frontend Team Context
- Create `TeamContext` provider
- Integrate with `AuthContext`
- Add team state to app

### Phase 4: Frontend Team UI
- Build `TeamPage` component
- Build `JoinTeamPage` component
- Add team indicator and navigation

### Phase 5: Data Scope Integration
- Modify backend queries to support team scope
- Update frontend to reflect team data
- Handle deduplication across team members

### Phase 6: Testing & Polish
- End-to-end testing
- Error handling
- Edge cases

---

## 5. Key Considerations

### 5.1 Security

- **Invite codes:** Use `secrets.token_urlsafe(16)` for secure random codes
- **Permission checks:** Verify team membership and role on every operation
- **Data isolation:** `get_data_scope_user_ids` must never leak unauthorized data

### 5.2 Edge Cases

| Scenario | Handling |
|----------|----------|
| Last admin leaves | Require promoting another admin first, or delete team |
| Owner leaves | Must transfer ownership or delete team |
| User already in team | Error: "Leave current team first" |
| Expired invite | Clear error message |
| Exhausted invite | Clear error message |

### 5.3 Performance

- **Denormalization:** Store `member_count` on team document
- **Batch queries:** Firestore `in` queries limited to 30 values; batch for larger teams
- **Caching:** Consider caching team membership to avoid DB lookup per request

### 5.4 Demo Mode

- Demo users can create/join demo teams
- Demo teams cannot include real users
- Prevents data leakage between demo and production

---

## 6. File Structure

### New Files

```
backend/
├── app/
│   ├── api/
│   │   └── team_routes.py          # Team API endpoints
│   ├── repositories/
│   │   └── team_repo.py            # Team repository
│   ├── auth/
│   │   └── permissions.py          # Role-based permissions
│   └── schemas/
│       └── team_models.py          # Pydantic models
└── migrations/
    └── m_YYYYMMDD_001_team_indexes.py

web/src/
├── team/
│   └── TeamContext.tsx             # Team context provider
├── pages/
│   ├── TeamPage.tsx                # Team management page
│   ├── TeamPage.css
│   └── JoinTeamPage.tsx            # Invite accept page
└── types/
    └── team.ts                     # Team TypeScript types
```

### Modified Files

```
backend/
├── app/
│   ├── api/routes.py               # Add team-scoped data queries
│   └── repositories/firestore_repo.py  # Add multi-user query methods
└── main.py                         # Register team router

web/src/
├── main.tsx                        # Add TeamProvider, join route
├── App.tsx                         # Add team nav item, team view
└── auth/AuthContext.tsx            # (Optional) team integration
```

---

## 7. Firestore Indexes

Add to `firestore.indexes.json`:

```json
{
  "indexes": [
    {
      "collectionGroup": "team_memberships",
      "queryScope": "COLLECTION",
      "fields": [
        { "fieldPath": "user_id", "order": "ASCENDING" },
        { "fieldPath": "status", "order": "ASCENDING" }
      ]
    },
    {
      "collectionGroup": "team_memberships",
      "queryScope": "COLLECTION",
      "fields": [
        { "fieldPath": "team_id", "order": "ASCENDING" },
        { "fieldPath": "status", "order": "ASCENDING" }
      ]
    },
    {
      "collectionGroup": "team_invites",
      "queryScope": "COLLECTION",
      "fields": [
        { "fieldPath": "team_id", "order": "ASCENDING" },
        { "fieldPath": "is_active", "order": "ASCENDING" }
      ]
    }
  ]
}
```
