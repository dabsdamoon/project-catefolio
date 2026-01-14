import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router'
import type { InviteInfo } from './types'
import './JoinTeamPage.css'

interface JoinTeamPageProps {
  apiFetch: (url: string, options?: RequestInit) => Promise<Response>
  apiBaseUrl: string
}

export default function JoinTeamPage({ apiFetch, apiBaseUrl }: JoinTeamPageProps) {
  const { inviteCode } = useParams<{ inviteCode: string }>()
  const navigate = useNavigate()

  const [inviteInfo, setInviteInfo] = useState<InviteInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [joining, setJoining] = useState(false)

  useEffect(() => {
    const fetchInviteInfo = async () => {
      if (!inviteCode) {
        setError('Invalid invite link')
        setLoading(false)
        return
      }

      try {
        const response = await apiFetch(`${apiBaseUrl}/teams/invite/${inviteCode}`)
        if (!response.ok) {
          const data = await response.json().catch(() => ({}))
          throw new Error(data.detail || 'Invalid invite')
        }

        const data: InviteInfo = await response.json()
        setInviteInfo(data)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load invite')
      } finally {
        setLoading(false)
      }
    }

    fetchInviteInfo()
  }, [inviteCode, apiFetch, apiBaseUrl])

  const handleJoin = async () => {
    if (!inviteCode) return

    setJoining(true)
    setError(null)

    try {
      const response = await apiFetch(`${apiBaseUrl}/teams/join`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ invite_code: inviteCode }),
      })

      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data.detail || 'Failed to join team')
      }

      // Redirect to home after joining
      navigate('/')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to join team')
    } finally {
      setJoining(false)
    }
  }

  if (loading) {
    return (
      <div className="join-team-page">
        <div className="join-team-card">
          <div className="join-team-loading">Loading invite...</div>
        </div>
      </div>
    )
  }

  if (error || !inviteInfo) {
    return (
      <div className="join-team-page">
        <div className="join-team-card">
          <div className="join-team-error-icon">!</div>
          <h2>{error || 'Invalid invite'}</h2>
          <p className="join-team-error-message">
            This invite link is no longer valid.
            It may have expired or been revoked.
          </p>
          <button className="join-team-button secondary" onClick={() => navigate('/')}>
            Go to Dashboard
          </button>
        </div>
      </div>
    )
  }

  if (inviteInfo.already_in_team) {
    return (
      <div className="join-team-page">
        <div className="join-team-card">
          <div className="join-team-warning-icon">!</div>
          <h2>Already in a team</h2>
          <p className="join-team-warning-message">
            You're already a member of "{inviteInfo.current_team_name}".
            <br />
            Leave your current team to join a new one.
          </p>
          <button className="join-team-button secondary" onClick={() => navigate('/')}>
            Go to Team Settings
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="join-team-page">
      <div className="join-team-card">
        <p className="join-team-subtitle">You've been invited to join</p>
        <h2 className="join-team-name">{inviteInfo.team_name}</h2>
        <p className="join-team-members">{inviteInfo.member_count} member{inviteInfo.member_count !== 1 ? 's' : ''}</p>

        {error && <div className="join-team-action-error">{error}</div>}

        <button
          className="join-team-button primary"
          onClick={handleJoin}
          disabled={joining}
        >
          {joining ? 'Joining...' : 'Join Team'}
        </button>

        <button className="join-team-button ghost" onClick={() => navigate('/')}>
          Back to Dashboard
        </button>
      </div>
    </div>
  )
}
