import { useMemo } from 'react'
import { useAuth } from '../auth/AuthContext'
import App from '../App'
import { createApiFetch } from '../api/apiFetch'

const API_ENDPOINTS = {
  local: 'http://localhost:8000',
  cloud: import.meta.env.VITE_API_BASE || 'http://localhost:8000',
}

export default function AuthenticatedApp() {
  const { user, getToken, signOut } = useAuth()

  const apiFetch = useMemo(
    () => createApiFetch({ mode: 'authenticated', getToken }),
    [getToken]
  )

  return (
    <App
      apiFetch={apiFetch}
      apiEndpoints={API_ENDPOINTS}
      isDemo={false}
      userDisplayName={user?.displayName || user?.email || 'User'}
      userPhotoURL={user?.photoURL}
      onSignOut={signOut}
    />
  )
}
