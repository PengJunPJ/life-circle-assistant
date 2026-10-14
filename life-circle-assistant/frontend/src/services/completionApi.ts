import { API_BASE_URL } from '../constants/facilities'
import type { ActiveSampling, Audience, AudienceReport, Combination, Governance, NativeIsochroneCapability, PlanningConstraints, PlanningDemand, PlanningOptimization, ReviewDecision, SamplingStrategy, TrustedCandidate } from '../types/completion'
import type { Report } from '../types/report'
import type { SemanticReview } from '../types/aiExtensions'

async function request<T>(reportId: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}/api/reports/${encodeURIComponent(reportId)}${path}`, body === undefined ? undefined : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  const payload = await response.json()
  if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : payload.error || '操作未完成，请检查输入和数据条件')
  return payload as T
}
export const fetchGovernance = (id: string) => request<Governance>(id, '/governance')
export const runSemanticReview = (id: string) => request<SemanticReview>(id, '/ai/semantic-review', { use_model: true })
export const decideSemanticReview = (id: string, body: ReviewDecision) => request<Governance>(id, '/governance/decisions', body)
export const recomputeCatalog = (id: string) => request<{ report_id: string; report: Report; catalog_version: number }>(id, '/governance/recompute', {})
export const submitObservation = (id: string, body: { text: string; image_base64?: string; mime_type?: string; lng?: number; lat?: number }) => request(id, '/observations', body)
export const decideObservation = (id: string, observationId: string, body: { decision: 'accept' | 'reject' | 'correct'; reviewer: string; reason: string; category?: string; name?: string; lng?: number; lat?: number; expected_version: number; kind?: string; facility_id?: string; first_grid_id?: string; second_grid_id?: string }) => request(id, `/observations/${encodeURIComponent(observationId)}/decision`, body)
export const generateAudienceReport = (id: string, audience: Audience, query: string) => request<AudienceReport>(id, '/audience-report', { audience, query })
export const runActiveSampling = (id: string, routePairBudget: number, gridSize: number, strategy: SamplingStrategy = 'active') => request<ActiveSampling>(id, '/experiments/active-sampling', { route_pair_budget: routePairBudget, grid_size: gridSize, strategy })
async function nativeRequest(body?: unknown): Promise<NativeIsochroneCapability> {
  const response = await fetch(`${API_BASE_URL}/api/map/isochrone-${body === undefined ? 'capability' : 'probe'}`, body === undefined ? undefined : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  const payload = await response.json()
  if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : '原生等时圈核验失败')
  return payload as NativeIsochroneCapability
}
export const fetchNativeIsochroneCapability = () => nativeRequest()
export const probeNativeIsochrone = (lng: number, lat: number, minutes: number, strategy: 'foot_fastest' | 'foot_shortest') => nativeRequest({ lng, lat, minutes, strategy })
export const fetchPlanningCandidates = (id: string) => request<{ items: TrustedCandidate[] }>(id, '/planning/candidates')
export const registerPlanningCandidates = (id: string, candidates: TrustedCandidate[]) => request<{ items: TrustedCandidate[] }>(id, '/planning/candidates', { candidates })
export const fetchPlanningDemand = (id: string) => request<{ items: PlanningDemand[] }>(id, '/planning/demand')
export const registerPlanningDemand = (id: string, items: PlanningDemand[]) => request<{ items: PlanningDemand[] }>(id, '/planning/demand', { items })
export const optimizePlanning = (id: string, constraints: PlanningConstraints) => request<PlanningOptimization>(id, '/planning/optimize', constraints)
export const recomputeCombination = (id: string, candidateIds: string[]) => request<Combination>(id, '/planning/combination', { candidate_ids: candidateIds })
