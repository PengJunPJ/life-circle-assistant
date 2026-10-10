import type { DataQuality } from './quality'
import type { CategoryScore, OverallScoring } from './scoring'
import type { CenterSelectionMethod } from './location'
import type { PlanningRecommendation, RecommendationSummary } from './recommendations'

export type AnalysisMode = 'demo' | 'analysis'
export type AnalysisMinutes = 10 | 15 | 20

export type Category = CategoryScore

export type Poi = {
  id: string
  name: string
  canonical_name?: string
  semantic_type?: string
  semantic_type_label?: string
  category: string
  lng: number
  lat: number
  walk_minutes: number | null
  walk_distance_m?: number | null
  source?: string
  calculation_method?: string
  normalization?: {
    rules_version: string
    method: string
    confidence: 'high' | 'medium' | 'low'
    aliases: string[]
    merged_facility_ids: string[]
    source_record_count: number
  }
}

export type ServiceAreaKind = 'normal' | 'sparse' | 'critical' | 'unknown'

export type ServiceAreaProperties = {
  grid_id: string
  coordinate_system: 'BD-09'
  kind: ServiceAreaKind
  region_type: ServiceAreaKind
  label: string
  category: string
  category_label: string
  color: string
  threshold_minutes: number
  nearby_radius_m: number
  nearby_facility_count: number
  lacks_nearby_facility: boolean
  candidate_prefilter_radius_m: number
  candidate_facility_count: number
  nearest_facility_id: string | null
  nearest_facility_name: string | null
  nearest_walk_minutes: number | null
  nearest_walk_distance_m: number | null
  walk_threshold_exceeded: boolean | null
  critical_conditions_met: boolean
  classification_status: 'valid' | 'calculation_incomplete'
  source: string
  calculation_method: string
  basis: string
  confidence: 'high' | 'medium' | 'low'
  failed_route_count: number
}

export type GeoJsonFeature<TProperties extends Record<string, any> = Record<string, any>> = {
  type: 'Feature'
  properties: TProperties
  geometry: { type: string; coordinates: number[][][] }
}

export type ServiceAreaFeature = GeoJsonFeature<ServiceAreaProperties>

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
  multisource_validation?: {
    status: 'disabled' | 'complete' | 'failed'
    provider: 'amap' | string
    affects_primary_analysis: false
    message?: string
    error_code?: string
    query_count?: number
    returned_count?: number
    truncated_query_count?: number
    matched_count?: number
    review_count?: number
    conflict_count?: number
    unmatched_count?: number
  }
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
    stages: { code: string; label: string; progress: number; at: string; duration_ms: number }[]
    stage_durations_ms: Record<string, number>
    api_calls: number
    cache: { hits: number; misses: number; hit_rate: number }
    metrics: Record<string, number>
  }
  isochrone: GeoJsonFeature
  pois: Poi[]
  facility_normalization?: {
    rules_version: string
    same_site_distance_m: number
    input_count: number
    output_count: number
    merged_count: number
    merged_group_count: number
    by_category: Record<string, {
      input_count: number
      output_count: number
      merged_count: number
      semantic_types: Record<string, number>
    }>
  }
  zones: { type: 'FeatureCollection'; features: ServiceAreaFeature[] }
  service_areas: { type: 'FeatureCollection'; features: ServiceAreaFeature[] }
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
  recommendation_summary: RecommendationSummary
  recommendations: PlanningRecommendation[]
  center: {
    lng: number
    lat: number
    address: string
    selection_method?: CenterSelectionMethod
    source?: string
    support_status?: 'supported' | 'unsupported'
  }
  parameters: {
    lng: number
    lat: number
    minutes: AnalysisMinutes
    mode: AnalysisMode
    categories: string[]
    center_address?: string
    center_selection_method?: CenterSelectionMethod
  }
}

export type AiEvidenceRef = {
  type: string
  id: string
  label: string
  detail: string
}

export type AiInterpretationIntent =
  | 'summary'
  | 'area_explanation'
  | 'ask'
  | 'priority'
  | 'simulation'
  | 'brief'

export type AiInterpretation = {
  intent: AiInterpretationIntent
  summary: string
  recommendations: { title: string; text: string; priority: string; evidence_refs: AiEvidenceRef[] }[]
  evidence_refs: AiEvidenceRef[]
  model: string
  mode: 'rule_template' | 'rule_template_degraded' | 'llm_structured'
  prompt_version: string
  generated_at: string
  data_quality_notice: string
  boundary_notice: string
  uncertainties?: string[]
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
  request?: Report['parameters']
  rerun_of_report_id?: string | null
  created_at?: string
  completed_at?: string | null
}

export type MapConfig = { mode: string; provider_mode: 'real' | 'snapshot' | 'fixture'; browser_ak: string }

export type MapStatus = {
  mode: 'real' | 'mock'
  provider_mode: 'real' | 'snapshot' | 'fixture'
  provider: string
  source: string
  real_api_configured: boolean
  real_api_probe_endpoint: string | null
  mock_available: boolean
  snapshot_available: boolean
  message: string
}

export type MapProbeResult = {
  configured: boolean
  verified: boolean
  checked_at: string | null
  message: string
}
