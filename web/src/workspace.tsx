import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, type Workspace } from './api'
import { useAuth } from './auth'

interface WsState {
  workspaces: Workspace[]
  current: Workspace | null          // null = all workspaces
  setCurrent: (id: string | null) => void
  reload: () => Promise<void>
  loading: boolean
  error: unknown                     // last failure loading the workspace list
  qs: string                         // "?workspace_id=…" or ""
}

const Ctx = createContext<WsState>(null!)
const KEY = 'cc.workspace'

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { me } = useAuth()
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [currentId, setCurrentId] = useState<string | null>(() => { try { return localStorage.getItem(KEY) } catch { return null } })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<unknown>(null)

  const reload = useCallback(async () => {
    if (!me) { setWorkspaces([]); setLoading(false); return }
    try {
      const ws = await api.get<Workspace[]>('/cc/workspaces')
      setWorkspaces(ws)
      setError(null)
      if (currentId && !ws.some(w => w.id === currentId)) setCurrentId(null)
    } catch (err) {
      setError(err)   // a failed load is an error, not "you have no workspaces"
    } finally { setLoading(false) }
  }, [me, currentId])

  useEffect(() => { reload() }, [reload])

  const setCurrent = (id: string | null) => {
    setCurrentId(id)
    try { id ? localStorage.setItem(KEY, id) : localStorage.removeItem(KEY) } catch { /* ignore */ }
  }
  const current = workspaces.find(w => w.id === currentId) ?? null
  const qs = current ? `?workspace_id=${current.id}` : ''
  return <Ctx.Provider value={{ workspaces, current, setCurrent, reload, loading, error, qs }}>{children}</Ctx.Provider>
}

export function useWorkspace() { return useContext(Ctx) }
