import type { SemanticReview } from './aiExtensions'
import type { Report, ServiceAreaFeature } from './report'

export type StatusLayerKey = 'normal' | 'sparse' | 'critical' | 'unknown' | 'scarcity' | 'walking_timeout' | 'gap_groups' | 'sampling'
export type StatusLayers = Record<StatusLayerKey, boolean>
export const DEFAULT_STATUS_LAYERS: StatusLayers = { normal: true, sparse: true, critical: true, unknown: true, scarcity: false, walking_timeout: false, gap_groups: false, sampling: false }
export type SpatialFeature = {
  type: 'Feature'
  geometry: { type: 'Point'; coordinates: number[] } | { type: 'Polygon'; coordinates: number[][][] } | { type: 'MultiPolygon'; coordinates: number[][][][] }
  properties: { coordinate_system?: string; category?: string; source?: string; point_id?: string; mean_minutes?: number | null; std_minutes?: number | null; [key: string]: unknown }
}
export type SpatialCollection = { type: 'FeatureCollection'; features: SpatialFeature[] }
export type SamplingLayers = { observed: SpatialCollection; observed_boundary?: SpatialCollection; estimated: SpatialCollection; unresolved: SpatialCollection; time_field: SpatialCollection; native_boundary?: SpatialCollection }
export type SamplingStrategy = 'active' | 'uniform' | 'radial' | 'rule_densification' | 'idw'
export type NativeIsochroneCapability = {
  configured: boolean; available: boolean; account_verified: boolean; credentials_available?: boolean; pricing_verified: boolean
  strategies?: string[]; verified_at?: string | null; error_code?: string | null; disclosure?: string
  status?: 'disabled' | 'available' | 'unavailable'; request_sent?: boolean; message?: string
  geometry?: Exclude<SpatialFeature['geometry'], { type: 'Point' }>; source?: string; method?: string
}
export type ActiveSampling = {
  report_id: string; status: string; external_route_pairs_used: number; layers: SamplingLayers; disclosure: string
  enabled_for_official_analysis: false; evaluation?: { mae_minutes?: number | null; evaluated_count?: number; unresolved_count?: number }
  native_capability?: { status?: string; available?: boolean; reason?: string }
}
export type CatalogRecord = { id: string; name?: string; category?: string; lng?: number; lat?: number; active?: boolean }
export type ResidentObservation = {
  id: string; text: string; status: string; ocr_text?: string; kind?: string; lng?: number; lat?: number; created_at?: string; disclosure?: string
  facility_id?: string; location?: { lng?: number; lat?: number }
  image_url?: string | null; has_image?: boolean
}
export type Governance = {
  catalog_version: number; catalog: { version: number; records: CatalogRecord[]; source_records?: CatalogRecord[] }
  reviews: (SemanticReview & { review_id: string })[]; observations: ResidentObservation[]
  audit: { id?: string; decision?: string; reviewer?: string; reason?: string; created_at?: string; kind?: string }[]
}
export type ReviewDecision = {
  review_id: string; kind: 'category' | 'entity'; record_id?: string; left_id?: string; right_id?: string
  decision: 'accept' | 'reject' | 'correct'; category?: string; relation?: string; reviewer: string; reason: string; expected_version: number
}
export type Audience = 'resident' | 'community' | 'planner'
export type AudienceReport = {
  audience?: Audience; observations: unknown[]; possible_causes: unknown[]; measures: unknown[]; verification_conditions: unknown[]
  norms: { id?: string; title?: string; text?: string; source?: string; [key: string]: unknown }[]; citations: unknown[]; disclosure: string
}
export type TrustedCandidate = {
  id: string; category: string; lng: number; lat: number; source: string; verified: boolean
  cost?: number | null; capacity?: number | null; population?: number | null; land_allowed?: boolean | null
}
export type PlanningDemand = { grid_id: string; population: number; source: string; verified: true }
export type PlanningConstraints = {
  candidate_ids: string[]; max_facilities: number; budget?: number; category_limits: Record<string, { min: number; max: number }>
  required_ids: string[]; forbidden_ids: string[]; minimum_capacity?: number; minimum_population?: number; allowed_land_only?: boolean; method: 'auto'
}
export type CombinationSnapshot = {
  overall_score?: number | null; score?: number | null; coverage_area_sqm?: number; critical_zone_count?: number; sparse_zone_count?: number
  service_areas?: { type: 'FeatureCollection'; features: ServiceAreaFeature[] }; category_scores?: Report['category_scores']
}
export type Combination = {
  id?: string; report_id: string; before: CombinationSnapshot; after: CombinationSnapshot; delta: CombinationSnapshot
  hypothetical_facilities: { id: string; name?: string; category: string; lng: number; lat: number }[]; disclosure?: string
}
export type PlanningOptimization = {
  status: string; selected_candidate_ids: string[]; selected_candidates: TrustedCandidate[]; covered_grid_count?: number; total_cost?: number | null; confirmed_population?: number | null
  combination: Combination; pareto_solutions: { candidate_ids: string[]; covered_grid_count?: number; total_cost?: number | null; selected_count?: number; [key: string]: unknown }[]; disclosure?: string
}
