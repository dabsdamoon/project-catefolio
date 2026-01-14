import { useMemo } from 'react'
import { useAuth } from '../auth/AuthContext'
import { createApiFetch } from '../api/apiFetch'
import JoinTeamPage from '../team/JoinTeamPage'

const API_ENDPOINTS = {
  local: 'http://localhost:8000',
  cloud: import.meta.env.VITE_API_BASE || 'http://localhost:8000',
}

const getStoredApiMode = (): 'local' | 'cloud' => {
  const stored = localStorage.getItem('catefolio_api_mode')
  return stored === 'cloud' ? 'cloud' : 'local'
}

export default function JoinTeamWrapper() {
  const { getToken } = useAuth()
  const apiMode = getStoredApiMode()
  const apiBaseUrl = API_ENDPOINTS[apiMode]

  const apiFetch = useMemo(
    () => createApiFetch({ mode: 'authenticated', getToken }),
    [getToken]
  )

  return (
    <JoinTeamPage
      apiFetch={apiFetch}
      apiBaseUrl={apiBaseUrl}
    />
  )
}
