import { API_BASE_URL } from '../constants/facilities'
import type { AnalysisMode, AnalysisMinutes, AnalysisTask, MapConfig, Report } from '../types/report'

async function parseResponse<T>(response: Response): Promise<T> {
  const payload = await response.json()
  if (!response.ok) throw new Error(payload.detail || payload.error || '请求失败')
  return payload as T
}

export async function fetchMapConfig() {
  return parseResponse<MapConfig>(await fetch(`${API_BASE_URL}/api/map/config`))
}

export async function geocodeAddress(address: string) {
  return parseResponse<{ result?: { location?: { lng: number; lat: number } } }>(
    await fetch(`${API_BASE_URL}/api/geocode?address=${encodeURIComponent(address)}&city=广州`),
  )
}

export async function createAnalysis(params: {
  lng: number
  lat: number
  minutes: AnalysisMinutes
  mode: AnalysisMode
  categories: string[]
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
