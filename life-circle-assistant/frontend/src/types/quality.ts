export type DataSourceKind = 'real_api' | 'cache' | 'local_snapshot' | 'interpolation' | 'degraded_estimate'

export type QualitySource = {
  kind: DataSourceKind
  provider: string
  label: string
  usage: string
  is_latest_real_measurement: boolean
}

export type QualityEvent = {
  code: string
  severity: 'info' | 'warning' | 'error'
  scope: string
  category: string | null
  object_ref: string | null
  source: DataSourceKind
  method: string
  message: string
}

export type PartialFailure = {
  scope: string
  code: string
  category?: string
  object_ref?: string
  message: string
}

export type DataQuality = {
  overall_status: 'good' | 'limited' | 'partial'
  summary: string
  sources: QualitySource[]
  events: QualityEvent[]
  partial_failures: PartialFailure[]
}
