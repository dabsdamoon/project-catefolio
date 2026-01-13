/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from 'react'
import {
  type User,
  onAuthStateChanged,
  signInWithPopup,
  signOut as firebaseSignOut,
  getIdToken,
} from 'firebase/auth'
import { auth, googleProvider } from '../firebase/config'

interface AuthContextType {
  user: User | null
  loading: boolean
  signInWithGoogle: () => Promise<void>
  signOut: () => Promise<void>
  getToken: () => Promise<string | null>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (firebaseUser) => {
      setUser(firebaseUser)
      setLoading(false)
    })
    return unsubscribe
  }, [])

  const signInWithGoogle = useCallback(async () => {
    await signInWithPopup(auth, googleProvider)
  }, [])

  const signOut = useCallback(async () => {
    await firebaseSignOut(auth)
  }, [])

  const getToken = useCallback(async (): Promise<string | null> => {
    if (!user) return null
    try {
      return await getIdToken(user, false)
    } catch (error) {
      console.error('Failed to get token:', error)
      return null
    }
  }, [user])

  return (
    <AuthContext.Provider value={{ user, loading, signInWithGoogle, signOut, getToken }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
