export type ScoreComponentKey = 'quantity' | 'walking_time' | 'spatial_distribution'
export type CategoryScoreStatus = 'valid' | 'poor_coverage' | 'calculation_incomplete' | 'data_unavailable'
export type OverallScoreStatus = 'complete' | 'partial' | 'unavailable'

export type ScoreComponent = {
  key: ScoreComponentKey
  label: string
  weight: number
  weight_percent: number
  score: number | null
  weighted_score: number | null
  observed_value: number | null
  observed_unit: string
  reason: string
}

export type CategoryScore = {
  category: string
  label: string
  count: number
  nearest_walk_minutes: number | null
  score: number | null
  color: string
  status: CategoryScoreStatus
  status_label: string
  status_explanation: string
  valid_for_overall: boolean
  configured_weight: number
  applied_weight: number
  components: ScoreComponent[]
}

export type CategoryWeight = {
  category: string
  label: string
  configured_weight: number
  applied_weight: number
  included: boolean
  reason: string
}

export type OverallScoring = {
  score: number | null
  status: OverallScoreStatus
  selected_category_count: number
  valid_category_count: number
  component_weights: Record<ScoreComponentKey, { weight: number; weight_percent: number }>
  category_weights: CategoryWeight[]
  explanation: string
}
