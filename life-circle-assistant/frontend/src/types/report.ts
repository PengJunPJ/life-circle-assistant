import type { DataQuality } from './quality'
import type { CategoryScore, OverallScoring } from './scoring'

export type AnalysisMode = 'demo' | 'analysis'
export type AnalysisMinutes = 10 | 15 | 20

export type Category = CategoryScore

export type Poi = {
  id: string
  name: string
  category: string
  lng: number
  lat: number
  walk_minutes: number | null
  walk_distance_m?: number | null
  source?: string
  calculation_method?: string
}

export type GeoJsonFeature = {
  type: 'Feature'
  properties: Record<string, any>
  geometry: { type: string; coordinates: number[][][] }
}

export type Report = {
  schema_version: '2.0' | string
  id: string
  report_id: string
  task_id: string
  status: 'completed'
  completeness: 'complete' | 'partial'
  created_at: string
  completed_at: string
  source: string
  quality: { mode: string; confidence: number; message: string }
  data_quality: DataQuality
  calculation_mode: {
    requested_mode: AnalysisMode
    provider_mode: 'real' | 'snapshot' | 'fixture'
    coordinate_system: 'BD-09'
    walking_method: string
  }
  execution: {
    current_stage: string
    current_stage_label: string
    total_duration_ms: number
    stages: { code: string; label: string; progress: number; at: string }[]
    metrics: Record<string, number>
  }
  isochrone: GeoJsonFeature
  pois: Poi[]
  zones: { type: 'FeatureCollection'; features: GeoJsonFeature[] }
  summary: {
    score: number | null
    score_status: OverallScoring['status']
    score_explanation: string
    area_sqm: number
    poi_count: number
    critical_zone_count: number
    sparse_zone_count: number
  }
  categories: Category[]
  category_scores: CategoryScore[]
  scoring: OverallScoring
  recommendations: { priority: string; title: string; body: string; category: string }[]
  center: { lng: number; lat: number; address: string }
  parameters: {
    lng: number
    lat: number
    minutes: AnalysisMinutes
    mode: AnalysisMode
    categories: string[]
  }
}

export type AnalysisTask = {
  id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  progress: number
  stage: string
  stage_label: string
  report_id?: string
  result?: Report
  error?: string
}

export type MapConfig = { mode: string; browser_ak: string }
