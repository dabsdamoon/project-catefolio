import { useMemo } from 'react'
import App from '../App'
import { createApiFetch, getDemoUserId } from '../api/apiFetch'

const API_ENDPOINTS = {
  local: 'http://localhost:8000',
  cloud: import.meta.env.VITE_API_BASE || 'http://localhost:8000',
}

export default function DemoApp() {
  const demoUserId = useMemo(() => getDemoUserId(), [])

  const apiFetch = useMemo(
    () => createApiFetch({ mode: 'demo', demoUserId }),
    [demoUserId]
  )

  return (
    <App
      apiFetch={apiFetch}
      apiEndpoints={API_ENDPOINTS}
      isDemo={true}
      userDisplayName="Demo User"
    />
  )
}
