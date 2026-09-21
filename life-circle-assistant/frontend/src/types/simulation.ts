import type { CategoryScore } from './scoring'
import type { ServiceAreaFeature } from './report'

export type SimulationSelectionMethod = 'recommendation' | 'map'

export type SimulationLocation = {
  lng: number
  lat: number
  selectionMethod: SimulationSelectionMethod
  candidateId?: string
}

export type SimulationSnapshot = {
  category_score: number | null
  overall_score: number | null
  coverage_area_sqm: number
  critical_zone_count: number
  sparse_zone_count: number
  category_score_detail: CategoryScore
  service_areas: { type: 'FeatureCollection'; features: ServiceAreaFeature[] }
}

export type SimulationResult = {
  id: string
  report_id: string
  created_at: string
  coordinate_system: 'BD-09'
  selection_method: SimulationSelectionMethod
  candidate_id: string | null
  category: string
  category_label: string
  hypothetical_facility: {
    id: string
    name: string
    category: string
    lng: number
    lat: number
    walk_minutes: number | null
    walk_distance_m: number | null
    source: string
    calculation_method: string
    is_hypothetical: true
  }
  before: SimulationSnapshot
  after: SimulationSnapshot
  delta: {
    category_score: number | null
    overall_score: number | null
    coverage_area_sqm: number
    critical_zone_count: number
    sparse_zone_count: number
  }
  unaffected_category_scores: CategoryScore[]
  data_quality: {
    source: string
    events: Record<string, unknown>[]
    partial_failures: Record<string, unknown>[]
    disclosure: string
  }
}
