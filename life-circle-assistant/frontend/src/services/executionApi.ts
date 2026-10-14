import { API_BASE_URL } from '../constants/facilities'
import type { ExecutionLedger } from '../types/report'

export type UncertainCheckpoint = { call_key: string; operation: string; updated_at: string }
export type RetryAuthorization = { status: 'retry_authorized'; disclosure: string; budget_reset?: false }
export type ExecutionSettlement = { version: number; amount_cny: number; bill_reference: string; reviewer: string; evidence: string; usage_sha256: string; created_at: string; scope: 'execution_total'; currency: 'CNY' }
export type SettlementInput = { amount_cny: string | number; bill_reference: string; reviewer: string; evidence: string; expected_version: number; expected_usage_sha256: string; scope: 'execution_total' }

async function request<T>(executionId: string, suffix: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}/api/executions/${encodeURIComponent(executionId)}${suffix}`, body === undefined ? undefined : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  const payload = await response.json()
  if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : '执行账本核对失败，请检查输入并重新读取账本')
  return payload as T
}

export const fetchUncertainCheckpoints = (id: string) => request<{ items: UncertainCheckpoint[] }>(id, '/uncertain-checkpoints')
export const authorizeCheckpointRetry = (id: string, callKey: string, reviewer: string, evidence: string) => request<RetryAuthorization>(id, '/reconcile', { call_key: callKey, reviewer, evidence })
export const fetchExecutionLedger = (id: string) => request<ExecutionLedger>(id, '')
export const fetchExecutionSettlements = (id: string) => request<{ items: ExecutionSettlement[] }>(id, '/settlements')
export const recordExecutionSettlement = (id: string, input: SettlementInput) => request<ExecutionSettlement>(id, '/settlements', input)
