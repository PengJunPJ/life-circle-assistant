import { API_BASE_URL } from '../constants/facilities'
import type { ReportComparison } from '../types/comparison'
import type { ReportHistoryResponse } from '../types/history'
import type { CenterSelectionMethod, LocationApiResponse, LocationCandidate } from '../types/location'
import type { AnalysisMode, AnalysisMinutes, AnalysisTask, MapConfig, Report } from '../types/report'
import type { SimulationResult, SimulationSelectionMethod } from '../types/simulation'

async function parseResponse<T>(response: Response): Promise<T> {
  const payload = await response.json()
  if (!response.ok) throw new Error(payload.detail || payload.error || '请求失败')
  return payload as T
}

export async function fetchMapConfig() {
  return parseResponse<MapConfig>(await fetch(`${API_BASE_URL}/api/map/config`))
}

export async function searchAddressCandidates(address: string) {
  const payload = await parseResponse<{
    source: string
    provider: string
    candidates: { lng: number; lat: number; address: string }[]
  }>(
    await fetch(`${API_BASE_URL}/api/geocode?address=${encodeURIComponent(address)}&city=广州`),
  )
  return payload.candidates.map<LocationCandidate>((candidate) => ({
    ...candidate,
    source: payload.source,
    provider: payload.provider,
  }))
}

export async function reverseGeocode(lng: number, lat: number) {
  return parseResponse<LocationApiResponse>(
    await fetch(`${API_BASE_URL}/api/locations/reverse?lng=${encodeURIComponent(lng)}&lat=${encodeURIComponent(lat)}`),
  )
}

export async function createAnalysis(params: {
  lng: number
  lat: number
  minutes: AnalysisMinutes
  mode: AnalysisMode
  categories: string[]
  center_address: string
  center_selection_method: CenterSelectionMethod
}) {
  return parseResponse<AnalysisTask>(
    await fetch(`${API_BASE_URL}/api/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    }),
  )
}

export async function getAnalysisTask(taskId: string) {
  return parseResponse<AnalysisTask>(await fetch(`${API_BASE_URL}/api/analyze/${taskId}`))
}

export async function fetchReportHistory(limit = 20, offset = 0) {
  return parseResponse<ReportHistoryResponse>(
    await fetch(`${API_BASE_URL}/api/reports/history?limit=${limit}&offset=${offset}`),
  )
}

export async function getHistoricalReport(reportId: string) {
  return parseResponse<Report>(await fetch(`${API_BASE_URL}/api/reports/${encodeURIComponent(reportId)}`))
}

export async function rerunHistoricalReport(reportId: string) {
  return parseResponse<AnalysisTask>(
    await fetch(`${API_BASE_URL}/api/reports/${encodeURIComponent(reportId)}/rerun`, { method: 'POST' }),
  )
}

export async function compareHistoricalReports(reportIds: [string, string]) {
  return parseResponse<ReportComparison>(
    await fetch(`${API_BASE_URL}/api/reports/compare`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report_ids: reportIds }),
    }),
  )
}

export async function simulateFacility(reportId: string, params: {
  category: string
  lng: number
  lat: number
  selection_method: SimulationSelectionMethod
  candidate_id?: string
}) {
  return parseResponse<SimulationResult>(
    await fetch(`${API_BASE_URL}/api/reports/${encodeURIComponent(reportId)}/simulations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    }),
  )
}

export async function waitForAnalysis(task: AnalysisTask, onProgress: (value: number) => void) {
  let current = task
  // 后端采用后台任务模型，统一在数据访问模块轮询，页面层只接收进度和最终报告。
  while (current.status !== 'completed' && current.status !== 'failed') {
    await new Promise((resolve) => setTimeout(resolve, 180))
    current = await getAnalysisTask(task.id)
    onProgress(current.progress)
  }
  if (current.status === 'failed') throw new Error(current.error || '百度地图分析失败')
  return current.result as Report
}
