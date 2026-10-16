import { API_BASE_URL } from '../constants/facilities'
import type { ConversationTurn, Workspace, WorkspaceState } from '../types/workspace'

export class WorkspaceApiError extends Error {
  constructor(public status: number, message: string) { super(message); this.name = 'WorkspaceApiError' }
}

async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}/api/workspaces${path}`, body === undefined ? undefined : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })
  const payload = await response.json()
  if (!response.ok) throw new WorkspaceApiError(response.status, typeof payload.detail === 'string' ? payload.detail : payload.detail?.message || payload.error || '对话工作台请求失败')
  return payload as T
}

export const createWorkspace = (state: WorkspaceState) => request<Workspace>('', { state })
export const getWorkspace = (id: string) => request<Workspace>(`/${encodeURIComponent(id)}`)
export const updateWorkspace = (id: string, expectedRevision: number, state: WorkspaceState) => request<Workspace>(`/${encodeURIComponent(id)}/state`, { expected_revision: expectedRevision, state })
export const getWorkspaceMessages = (id: string) => request<{ items: ConversationTurn[] }>(`/${encodeURIComponent(id)}/messages`)
export const sendWorkspaceMessage = (id: string, requestId: string, expectedRevision: number, message: string, confirmToken?: string) => request<ConversationTurn>(`/${encodeURIComponent(id)}/messages`, { request_id: requestId, expected_revision: expectedRevision, message, ...(confirmToken ? { confirm_token: confirmToken } : {}) })
