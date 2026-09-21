export type RecommendationPriority = 'high' | 'medium'

export type RecommendationSummary = {
  status: 'needs_action' | 'no_shortage' | 'calculation_incomplete'
  message: string
  recommendation_count: number
  target_region_count: number
}

export type RecommendationNearestFacility = {
  status: 'available' | 'not_found'
  id: string | null
  name: string | null
  walk_minutes: number | null
  walk_distance_m: number | null
  source_region_id: string | null
  message: string
}

export type RecommendationCandidate = {
  id: string
  category: string
  coordinate_system: 'BD-09'
  lng: number
  lat: number
  region_id: string
  related_region_ids: string[]
  reason: string
  selection_method: string
}

export type PlanningRecommendation = {
  id: string
  category: string
  category_label: string
  priority: '高' | '中'
  priority_level: RecommendationPriority
  priority_rank: number
  title: string
  body: string
  problem_basis: string
  nearest_facility: RecommendationNearestFacility
  target_region_ids: string[]
  target_improvement: {
    region_count: number
    estimated_area_sqm: number
    estimated_critical_regions_reduced: number
    description: string
    method: string
  }
  candidate_locations: RecommendationCandidate[]
}
