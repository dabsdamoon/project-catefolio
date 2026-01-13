export type AuthMode = 'authenticated' | 'demo'

export interface ApiConfig {
  mode: AuthMode
  getToken?: () => Promise<string | null>
  demoUserId?: string
}

export function createApiFetch(config: ApiConfig) {
  return async (url: string, options: RequestInit = {}): Promise<Response> => {
    const headers = new Headers(options.headers)

    if (config.mode === 'authenticated' && config.getToken) {
      const token = await config.getToken()
      if (!token) {
        throw new Error('Not authenticated')
      }
      headers.set('Authorization', `Bearer ${token}`)
    } else if (config.mode === 'demo' && config.demoUserId) {
      headers.set('X-Demo-User-Id', config.demoUserId)
    }

    return fetch(url, { ...options, headers })
  }
}

const DEMO_STORAGE_KEY = 'catefolio_demo_user_id'

export function getDemoUserId(): string {
  let userId = localStorage.getItem(DEMO_STORAGE_KEY)
  if (!userId) {
    userId = `session_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`
    localStorage.setItem(DEMO_STORAGE_KEY, userId)
  }
  return userId
}
