import type { AnalysisMode, AnalysisMinutes, ServiceAreaKind } from './report'

export type ComparisonValue = {
  left: number | null
  right: number | null
  delta: number | null
  comparable: boolean
  reason: string | null
}

export type ComparisonReportReference = {
  report_id: string
  task_id: string | null
  completed_at: string
  completeness: 'complete' | 'partial'
  center: { address: string; lng: number; lat: number }
  minutes: AnalysisMinutes
  mode: AnalysisMode
  categories: string[]
  report_url: string
}

export type ParameterDifference = {
  field: 'center' | 'completed_at' | 'minutes' | 'mode' | 'categories'
  label: string
  left: unknown
  right: unknown
  changed: boolean
}

export type CategoryComparison = {
  category: string
  label: string
  present: { left: boolean; right: boolean }
  comparable: boolean
  reason: string
  score: ComparisonValue
  facility_count: ComparisonValue
  service_area_counts: Record<ServiceAreaKind, ComparisonValue>
}

export type ReportComparison = {
  report_ids: [string, string]
  reports: [ComparisonReportReference, ComparisonReportReference]
  parameter_differences: ParameterDifference[]
  category_scope: {
    same_category_set: boolean
    common: string[]
    only_left: string[]
    only_right: string[]
    comparable: string[]
    incomparable: { category: string; label: string; reason: string }[]
  }
  summary: {
    overall_score: ComparisonValue
    reachable_area_sqm: ComparisonValue
    facility_count: ComparisonValue
    service_area_counts: Record<ServiceAreaKind, ComparisonValue>
  }
  categories: CategoryComparison[]
}
