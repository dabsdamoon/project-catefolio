/**
 * Team feature types
 */

export type TeamRole = 'admin' | 'member'

export interface Team {
  id: string
  name: string
  owner_id: string
  created_at: string
  updated_at: string
  member_count: number
}

export interface TeamMembership {
  id: string
  team_id: string
  user_id: string
  role: TeamRole
  joined_at: string
  invited_by: string | null
  status: 'active' | 'pending'
}

export interface TeamMember {
  user_id: string
  email: string | null
  name: string | null
  role: TeamRole
  joined_at: string
  is_owner: boolean
}

export interface TeamInvite {
  id: string
  team_id: string
  created_by: string
  created_at: string
  expires_at: string | null
  max_uses: number
  use_count: number
  is_active: boolean
  invite_url: string
}

export interface TeamMembershipStatus {
  team: Team | null
  membership: TeamMembership | null
  is_member: boolean
  is_admin: boolean
}

export interface InviteInfo {
  team_name: string
  member_count: number
  is_valid: boolean
  already_in_team: boolean
  current_team_name: string | null
}
