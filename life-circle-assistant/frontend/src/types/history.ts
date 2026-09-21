import type { AnalysisMode, AnalysisMinutes } from './report'

export type HistoryReportItem = {
  report_id: string
  task_id: string
  schema_version: string
  created_at: string
  completed_at: string
  center: { address: string; lng: number; lat: number }
  minutes: AnalysisMinutes
  mode: AnalysisMode
  categories: string[]
}

export type ReportHistoryResponse = {
  items: HistoryReportItem[]
  total: number
  limit: number
  offset: number
}
