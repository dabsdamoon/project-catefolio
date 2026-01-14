/* eslint-disable react-refresh/only-export-components */
import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from 'react'
import type {
  Team,
  TeamMembership,
  TeamMember,
  TeamInvite,
  TeamMembershipStatus,
  TeamRole,
} from './types'

interface DeleteAccountResult {
  deleted_jobs: number
  deleted_entities: number
  left_team: boolean
}

interface TeamContextType {
  team: Team | null
  membership: TeamMembership | null
  members: TeamMember[]
  invites: TeamInvite[]
  loading: boolean
  error: string | null
  isAdmin: boolean
  isMember: boolean
  isSolo: boolean

  // Actions
  createTeam: (name: string) => Promise<Team>
  updateTeam: (name: string) => Promise<Team>
  leaveTeam: () => Promise<void>
  joinTeam: (inviteCode: string) => Promise<Team>
  deleteAccount: () => Promise<DeleteAccountResult>

  // Member management
  refreshMembers: () => Promise<void>
  updateMemberRole: (userId: string, role: TeamRole) => Promise<void>
  removeMember: (userId: string) => Promise<void>

  // Invite management
  createInvite: (maxUses?: number, expiresHours?: number) => Promise<TeamInvite>
  revokeInvite: (inviteCode: string) => Promise<void>
  refreshInvites: () => Promise<void>

  // Refresh team data
  refreshTeam: () => Promise<void>
}

const TeamContext = createContext<TeamContextType | undefined>(undefined)

interface TeamProviderProps {
  children: ReactNode
  apiFetch: (url: string, options?: RequestInit) => Promise<Response>
  apiBaseUrl: string
}

export function TeamProvider({ children, apiFetch, apiBaseUrl }: TeamProviderProps) {
  const [team, setTeam] = useState<Team | null>(null)
  const [membership, setMembership] = useState<TeamMembership | null>(null)
  const [members, setMembers] = useState<TeamMember[]>([])
  const [invites, setInvites] = useState<TeamInvite[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const isAdmin = membership?.role === 'admin'
  const isMember = !!membership
  const isSolo = !membership

  // Fetch team membership status
  const refreshTeam = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)

      const response = await apiFetch(`${apiBaseUrl}/teams/me`)
      if (!response.ok) {
        throw new Error('Failed to fetch team status')
      }

      const data: TeamMembershipStatus = await response.json()
      setTeam(data.team)
      setMembership(data.membership)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
      setTeam(null)
      setMembership(null)
    } finally {
      setLoading(false)
    }
  }, [apiFetch, apiBaseUrl])

  // Fetch team members
  const refreshMembers = useCallback(async () => {
    if (!team) {
      setMembers([])
      return
    }

    try {
      const response = await apiFetch(`${apiBaseUrl}/teams/me/members`)
      if (!response.ok) {
        throw new Error('Failed to fetch members')
      }

      const data: TeamMember[] = await response.json()
      setMembers(data)
    } catch (err) {
      console.error('Failed to fetch members:', err)
    }
  }, [apiFetch, apiBaseUrl, team])

  // Fetch team invites
  const refreshInvites = useCallback(async () => {
    if (!team || !isAdmin) {
      setInvites([])
      return
    }

    try {
      const response = await apiFetch(`${apiBaseUrl}/teams/me/invites`)
      if (!response.ok) {
        throw new Error('Failed to fetch invites')
      }

      const data: TeamInvite[] = await response.json()
      setInvites(data)
    } catch (err) {
      console.error('Failed to fetch invites:', err)
    }
  }, [apiFetch, apiBaseUrl, team, isAdmin])

  // Create team
  const createTeam = useCallback(
    async (name: string): Promise<Team> => {
      const response = await apiFetch(`${apiBaseUrl}/teams`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || 'Failed to create team')
      }

      const newTeam: Team = await response.json()
      await refreshTeam()
      return newTeam
    },
    [apiFetch, apiBaseUrl, refreshTeam]
  )

  // Update team
  const updateTeam = useCallback(
    async (name: string): Promise<Team> => {
      const response = await apiFetch(`${apiBaseUrl}/teams/me`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || 'Failed to update team')
      }

      const updatedTeam: Team = await response.json()
      setTeam(updatedTeam)
      return updatedTeam
    },
    [apiFetch, apiBaseUrl]
  )

  // Leave team
  const leaveTeam = useCallback(async () => {
    const response = await apiFetch(`${apiBaseUrl}/teams/me`, {
      method: 'DELETE',
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || 'Failed to leave team')
    }

    setTeam(null)
    setMembership(null)
    setMembers([])
    setInvites([])
  }, [apiFetch, apiBaseUrl])

  // Delete account (all user data)
  const deleteAccount = useCallback(async (): Promise<DeleteAccountResult> => {
    const response = await apiFetch(`${apiBaseUrl}/me`, {
      method: 'DELETE',
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || 'Failed to delete account')
    }

    const result: DeleteAccountResult = await response.json()

    // Clear local state
    setTeam(null)
    setMembership(null)
    setMembers([])
    setInvites([])

    return result
  }, [apiFetch, apiBaseUrl])

  // Join team
  const joinTeam = useCallback(
    async (inviteCode: string): Promise<Team> => {
      const response = await apiFetch(`${apiBaseUrl}/teams/join`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ invite_code: inviteCode }),
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || 'Failed to join team')
      }

      const joinedTeam: Team = await response.json()
      await refreshTeam()
      return joinedTeam
    },
    [apiFetch, apiBaseUrl, refreshTeam]
  )

  // Update member role
  const updateMemberRole = useCallback(
    async (userId: string, role: TeamRole) => {
      const response = await apiFetch(`${apiBaseUrl}/teams/me/members/${userId}/role`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role }),
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || 'Failed to update role')
      }

      await refreshMembers()
    },
    [apiFetch, apiBaseUrl, refreshMembers]
  )

  // Remove member
  const removeMember = useCallback(
    async (userId: string) => {
      const response = await apiFetch(`${apiBaseUrl}/teams/me/members/${userId}`, {
        method: 'DELETE',
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || 'Failed to remove member')
      }

      await refreshMembers()
      await refreshTeam() // Update member count
    },
    [apiFetch, apiBaseUrl, refreshMembers, refreshTeam]
  )

  // Create invite
  const createInvite = useCallback(
    async (maxUses: number = 0, expiresHours?: number): Promise<TeamInvite> => {
      const response = await apiFetch(`${apiBaseUrl}/teams/me/invites`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ max_uses: maxUses, expires_hours: expiresHours }),
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || 'Failed to create invite')
      }

      const invite: TeamInvite = await response.json()
      await refreshInvites()
      return invite
    },
    [apiFetch, apiBaseUrl, refreshInvites]
  )

  // Revoke invite
  const revokeInvite = useCallback(
    async (inviteCode: string) => {
      const response = await apiFetch(`${apiBaseUrl}/teams/me/invites/${inviteCode}`, {
        method: 'DELETE',
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || 'Failed to revoke invite')
      }

      await refreshInvites()
    },
    [apiFetch, apiBaseUrl, refreshInvites]
  )

  // Initial fetch
  useEffect(() => {
    refreshTeam()
  }, [refreshTeam])

  // Fetch members when team changes
  useEffect(() => {
    if (team) {
      refreshMembers()
    }
  }, [team, refreshMembers])

  // Fetch invites when team changes and user is admin
  useEffect(() => {
    if (team && isAdmin) {
      refreshInvites()
    }
  }, [team, isAdmin, refreshInvites])

  return (
    <TeamContext.Provider
      value={{
        team,
        membership,
        members,
        invites,
        loading,
        error,
        isAdmin,
        isMember,
        isSolo,
        createTeam,
        updateTeam,
        leaveTeam,
        joinTeam,
        deleteAccount,
        refreshMembers,
        updateMemberRole,
        removeMember,
        createInvite,
        revokeInvite,
        refreshInvites,
        refreshTeam,
      }}
    >
      {children}
    </TeamContext.Provider>
  )
}

export function useTeam() {
  const context = useContext(TeamContext)
  if (context === undefined) {
    throw new Error('useTeam must be used within a TeamProvider')
  }
  return context
}
