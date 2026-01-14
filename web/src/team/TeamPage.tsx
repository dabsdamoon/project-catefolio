import { useState } from 'react'
import { useTeam } from './TeamContext'
import type { TeamRole } from './types'
import './TeamPage.css'

export default function TeamPage() {
  const {
    team,
    members,
    invites,
    loading,
    error,
    isAdmin,
    isSolo,
    createTeam,
    updateTeam,
    leaveTeam,
    joinTeam,
    deleteAccount,
    updateMemberRole,
    removeMember,
    createInvite,
    revokeInvite,
  } = useTeam()

  const [newTeamName, setNewTeamName] = useState('')
  const [editTeamName, setEditTeamName] = useState('')
  const [isEditing, setIsEditing] = useState(false)
  const [inviteCode, setInviteCode] = useState('')
  const [actionLoading, setActionLoading] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [showLeaveConfirm, setShowLeaveConfirm] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [deleteConfirmText, setDeleteConfirmText] = useState('')
  const [copiedInvite, setCopiedInvite] = useState<string | null>(null)

  if (loading) {
    return (
      <div className="team-page">
        <div className="team-loading">
          <div className="team-loading-spinner" />
          <p>Loading team information...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="team-page">
        <div className="team-error">
          <div className="team-error-icon">!</div>
          <p>{error}</p>
        </div>
      </div>
    )
  }

  const handleCreateTeam = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newTeamName.trim()) return

    setActionLoading(true)
    setActionError(null)

    try {
      await createTeam(newTeamName.trim())
      setNewTeamName('')
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to create team')
    } finally {
      setActionLoading(false)
    }
  }

  const handleJoinTeam = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!inviteCode.trim()) return

    setActionLoading(true)
    setActionError(null)

    try {
      let code = inviteCode.trim()
      const urlMatch = code.match(/\/join\/([^/]+)$/)
      if (urlMatch) {
        code = urlMatch[1]
      }
      await joinTeam(code)
      setInviteCode('')
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to join team')
    } finally {
      setActionLoading(false)
    }
  }

  const handleUpdateTeam = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!editTeamName.trim()) return

    setActionLoading(true)
    setActionError(null)

    try {
      await updateTeam(editTeamName.trim())
      setIsEditing(false)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to update team')
    } finally {
      setActionLoading(false)
    }
  }

  const handleLeaveTeam = async () => {
    setActionLoading(true)
    setActionError(null)

    try {
      await leaveTeam()
      setShowLeaveConfirm(false)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to leave team')
    } finally {
      setActionLoading(false)
    }
  }

  const handleRoleChange = async (userId: string, newRole: TeamRole) => {
    setActionLoading(true)
    setActionError(null)

    try {
      await updateMemberRole(userId, newRole)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to update role')
    } finally {
      setActionLoading(false)
    }
  }

  const handleRemoveMember = async (userId: string) => {
    if (!confirm('Are you sure you want to remove this member?')) return

    setActionLoading(true)
    setActionError(null)

    try {
      await removeMember(userId)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to remove member')
    } finally {
      setActionLoading(false)
    }
  }

  const handleCreateInvite = async () => {
    setActionLoading(true)
    setActionError(null)

    try {
      await createInvite()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to create invite')
    } finally {
      setActionLoading(false)
    }
  }

  const handleRevokeInvite = async (code: string) => {
    setActionLoading(true)
    setActionError(null)

    try {
      await revokeInvite(code)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to revoke invite')
    } finally {
      setActionLoading(false)
    }
  }

  const handleCopyInvite = async (url: string, inviteId: string) => {
    try {
      await navigator.clipboard.writeText(url)
      setCopiedInvite(inviteId)
      setTimeout(() => setCopiedInvite(null), 2000)
    } catch (err) {
      console.error('Failed to copy:', err)
    }
  }

  const handleDeleteAccount = async () => {
    if (deleteConfirmText !== 'DELETE') return

    setActionLoading(true)
    setActionError(null)

    try {
      await deleteAccount()
      setShowDeleteConfirm(false)
      setDeleteConfirmText('')
      window.location.href = '/login'
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to delete account')
    } finally {
      setActionLoading(false)
    }
  }

  const getInitials = (email: string | null | undefined, name: string | null | undefined) => {
    if (name) {
      return name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)
    }
    if (email) {
      return email.slice(0, 2).toUpperCase()
    }
    return '?'
  }

  // Solo mode - user not in a team
  if (isSolo) {
    return (
      <div className="team-page">
        <div className="team-page-header">
          <h1>Team</h1>
          <p>Collaborate with others by creating or joining a team</p>
        </div>

        {actionError && <div className="team-action-error">{actionError}</div>}

        {/* Welcome Section */}
        <div className="team-solo-welcome">
          <div className="team-solo-welcome-icon">👥</div>
          <h2>You're not part of a team yet</h2>
          <p>Create your own team to invite others, or join an existing team using an invite link.</p>
        </div>

        {/* Create Team Card */}
        <div className="team-card">
          <div className="team-card-header">
            <div className="team-card-title">
              <div className="team-card-icon primary">✨</div>
              <h2>Create a New Team</h2>
            </div>
          </div>
          <p className="team-card-description">
            Start fresh by creating your own team. You'll become the team admin and can invite others to join.
          </p>
          <form onSubmit={handleCreateTeam} className="team-form">
            <div className="team-input-wrapper">
              <input
                type="text"
                value={newTeamName}
                onChange={(e) => setNewTeamName(e.target.value)}
                placeholder="Enter team name"
                className="team-input"
                disabled={actionLoading}
              />
            </div>
            <button
              type="submit"
              className="team-btn primary"
              disabled={actionLoading || !newTeamName.trim()}
            >
              {actionLoading ? 'Creating...' : 'Create Team'}
            </button>
          </form>
        </div>

        <div className="team-divider">or</div>

        {/* Join Team Card */}
        <div className="team-card">
          <div className="team-card-header">
            <div className="team-card-title">
              <div className="team-card-icon success">🔗</div>
              <h2>Join an Existing Team</h2>
            </div>
          </div>
          <p className="team-card-description">
            Got an invite link or code? Paste it below to join a team.
          </p>
          <form onSubmit={handleJoinTeam} className="team-form">
            <div className="team-input-wrapper">
              <input
                type="text"
                value={inviteCode}
                onChange={(e) => setInviteCode(e.target.value)}
                placeholder="Paste invite link or code"
                className="team-input"
                disabled={actionLoading}
              />
            </div>
            <button
              type="submit"
              className="team-btn secondary"
              disabled={actionLoading || !inviteCode.trim()}
            >
              {actionLoading ? 'Joining...' : 'Join Team'}
            </button>
          </form>
        </div>

        {/* Delete Account Card */}
        <div className="team-card danger" style={{ marginTop: '32px' }}>
          <div className="team-card-header">
            <div className="team-card-title">
              <div className="team-card-icon danger">⚠️</div>
              <h2>Danger Zone</h2>
            </div>
          </div>
          {showDeleteConfirm ? (
            <div className="team-confirm">
              <div className="team-confirm-icon">🗑️</div>
              <h3>Delete Your Account?</h3>
              <p>
                This will permanently delete all your data including jobs, transactions,
                entities, and categories. This action cannot be undone.
              </p>
              <p style={{ fontWeight: 500 }}>
                Type <strong>DELETE</strong> to confirm:
              </p>
              <div className="team-confirm-input">
                <input
                  type="text"
                  value={deleteConfirmText}
                  onChange={(e) => setDeleteConfirmText(e.target.value.toUpperCase())}
                  placeholder="DELETE"
                  className="team-input"
                  disabled={actionLoading}
                />
              </div>
              <div className="team-confirm-actions">
                <button
                  className="team-btn danger-solid"
                  onClick={handleDeleteAccount}
                  disabled={actionLoading || deleteConfirmText !== 'DELETE'}
                >
                  {actionLoading ? 'Deleting...' : 'Delete My Account'}
                </button>
                <button
                  className="team-btn secondary"
                  onClick={() => {
                    setShowDeleteConfirm(false)
                    setDeleteConfirmText('')
                  }}
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <>
              <p className="team-card-description">
                Once you delete your account, all your data will be permanently removed.
                Please be certain before proceeding.
              </p>
              <button
                className="team-btn danger"
                onClick={() => setShowDeleteConfirm(true)}
              >
                Delete Account
              </button>
            </>
          )}
        </div>
      </div>
    )
  }

  // Team mode - user is in a team
  return (
    <div className="team-page">
      <div className="team-page-header">
        <h1>Team</h1>
        <p>Manage your team members and settings</p>
      </div>

      {actionError && <div className="team-action-error">{actionError}</div>}

      {/* Team Header */}
      <div className="team-header">
        {isEditing ? (
          <form onSubmit={handleUpdateTeam} className="team-edit-form">
            <input
              type="text"
              value={editTeamName}
              onChange={(e) => setEditTeamName(e.target.value)}
              className="team-input"
              autoFocus
              placeholder="Team name"
            />
            <button type="submit" className="team-btn primary" disabled={actionLoading}>
              Save
            </button>
            <button
              type="button"
              className="team-btn secondary"
              onClick={() => setIsEditing(false)}
            >
              Cancel
            </button>
          </form>
        ) : (
          <>
            <div className="team-header-info">
              <div className="team-header-avatar">👥</div>
              <div className="team-header-text">
                <h1>{team?.name}</h1>
                <p>{team?.member_count || members.length} member{(team?.member_count || members.length) !== 1 ? 's' : ''}</p>
              </div>
            </div>
            {isAdmin && (
              <div className="team-header-actions">
                <button
                  className="team-btn ghost"
                  onClick={() => {
                    setEditTeamName(team?.name || '')
                    setIsEditing(true)
                  }}
                >
                  Edit Name
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {/* Members Card */}
      <div className="team-card">
        <div className="team-card-header">
          <div className="team-card-title">
            <div className="team-card-icon primary">👤</div>
            <h2>Team Members</h2>
          </div>
        </div>
        <div className="team-members-list">
          {members.map((member) => (
            <div key={member.user_id} className="team-member-item">
              <div className="team-member-info">
                <div className={`team-member-avatar ${member.is_owner ? 'owner' : ''}`}>
                  {member.is_owner ? '👑' : getInitials(member.email, member.name)}
                </div>
                <div className="team-member-details">
                  <span className="team-member-name">
                    {member.name || member.email || member.user_id}
                    {member.is_owner && (
                      <span className="team-member-badge owner">Owner</span>
                    )}
                  </span>
                  {member.email && member.name && (
                    <span className="team-member-email">{member.email}</span>
                  )}
                  {!member.is_owner && (
                    <span className={`team-member-badge ${member.role}`}>
                      {member.role}
                    </span>
                  )}
                </div>
              </div>
              {isAdmin && !member.is_owner && (
                <div className="team-member-actions">
                  <select
                    value={member.role}
                    onChange={(e) => handleRoleChange(member.user_id, e.target.value as TeamRole)}
                    disabled={actionLoading}
                    className="team-role-select"
                  >
                    <option value="admin">Admin</option>
                    <option value="member">Member</option>
                  </select>
                  <button
                    className="team-btn danger sm icon-only"
                    onClick={() => handleRemoveMember(member.user_id)}
                    disabled={actionLoading}
                    title="Remove member"
                  >
                    ×
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Invites Card (Admin only) */}
      {isAdmin && (
        <div className="team-card">
          <div className="team-card-header">
            <div className="team-card-title">
              <div className="team-card-icon success">🔗</div>
              <h2>Invite Members</h2>
            </div>
            <button
              className="team-btn primary sm"
              onClick={handleCreateInvite}
              disabled={actionLoading}
            >
              Generate Link
            </button>
          </div>
          <p className="team-card-description">
            Create invite links to share with people you want to join your team.
          </p>

          {invites.length === 0 ? (
            <div className="team-invites-empty">
              No active invite links. Generate one to invite members.
            </div>
          ) : (
            <div className="team-invites-list">
              {invites.map((invite) => (
                <div key={invite.id} className="team-invite-item">
                  <div className="team-invite-info">
                    <span className="team-invite-code">{invite.id.slice(0, 8)}...</span>
                    <div className="team-invite-meta">
                      <span>Created {new Date(invite.created_at).toLocaleDateString()}</span>
                      <span>{invite.use_count}/{invite.max_uses === 0 ? '∞' : invite.max_uses} uses</span>
                    </div>
                  </div>
                  <div className="team-invite-actions">
                    <button
                      className={`team-btn secondary sm ${copiedInvite === invite.id ? 'team-copy-success' : ''}`}
                      onClick={() => handleCopyInvite(invite.invite_url, invite.id)}
                    >
                      {copiedInvite === invite.id ? 'Copied!' : 'Copy'}
                    </button>
                    <button
                      className="team-btn danger sm"
                      onClick={() => handleRevokeInvite(invite.id)}
                      disabled={actionLoading}
                    >
                      Revoke
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Leave Team Card */}
      <div className="team-card danger">
        <div className="team-card-header">
          <div className="team-card-title">
            <div className="team-card-icon warning">🚪</div>
            <h2>Leave Team</h2>
          </div>
        </div>
        {showLeaveConfirm ? (
          <div className="team-confirm">
            <div className="team-confirm-icon">🚪</div>
            <h3>Leave {team?.name}?</h3>
            <p>
              You will lose access to shared team data. You can rejoin later with a new invite.
            </p>
            <div className="team-confirm-actions">
              <button
                className="team-btn danger-solid"
                onClick={handleLeaveTeam}
                disabled={actionLoading}
              >
                {actionLoading ? 'Leaving...' : 'Yes, Leave Team'}
              </button>
              <button
                className="team-btn secondary"
                onClick={() => setShowLeaveConfirm(false)}
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <>
            <p className="team-card-description">
              Leave this team and work solo. Your personal data will remain, but you'll lose access to shared team data.
            </p>
            <button
              className="team-btn danger"
              onClick={() => setShowLeaveConfirm(true)}
            >
              Leave Team
            </button>
          </>
        )}
      </div>

      {/* Delete Account Card */}
      <div className="team-card danger">
        <div className="team-card-header">
          <div className="team-card-title">
            <div className="team-card-icon danger">⚠️</div>
            <h2>Danger Zone</h2>
          </div>
        </div>
        {showDeleteConfirm ? (
          <div className="team-confirm">
            <div className="team-confirm-icon">🗑️</div>
            <h3>Delete Your Account?</h3>
            <p>
              This will permanently delete all your data including jobs, transactions,
              entities, and categories. You will also be removed from this team.
              This action cannot be undone.
            </p>
            <p style={{ fontWeight: 500 }}>
              Type <strong>DELETE</strong> to confirm:
            </p>
            <div className="team-confirm-input">
              <input
                type="text"
                value={deleteConfirmText}
                onChange={(e) => setDeleteConfirmText(e.target.value.toUpperCase())}
                placeholder="DELETE"
                className="team-input"
                disabled={actionLoading}
              />
            </div>
            <div className="team-confirm-actions">
              <button
                className="team-btn danger-solid"
                onClick={handleDeleteAccount}
                disabled={actionLoading || deleteConfirmText !== 'DELETE'}
              >
                {actionLoading ? 'Deleting...' : 'Delete My Account'}
              </button>
              <button
                className="team-btn secondary"
                onClick={() => {
                  setShowDeleteConfirm(false)
                  setDeleteConfirmText('')
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <>
            <p className="team-card-description">
              Once you delete your account, all your data will be permanently removed.
              Please be certain before proceeding.
            </p>
            <button
              className="team-btn danger"
              onClick={() => setShowDeleteConfirm(true)}
            >
              Delete Account
            </button>
          </>
        )}
      </div>
    </div>
  )
}
