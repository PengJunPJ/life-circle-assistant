import type { Combination, PlanningOptimization, SamplingLayers } from './completion'

type ProposalReviewState = { status?: 'pending_human_review' | 'accepted' | 'rejected' | 'corrected'; reviewer?: string; reason?: string }
export type SemanticReview = {
  report_id: string
  mode: 'rules' | 'rules_degraded' | 'llm_review'
  record_count: number
  candidate_count: number
  candidates_truncated: boolean
  records: { id: string; name?: string; address?: string }[]
  category_proposals: ({ record_id: string; original_category: string | null; candidate_categories: string[]; proposed_category: string | null; confidence: number | null } & ProposalReviewState)[]
  entity_proposals: ({ left_id: string; right_id: string; relation: string; distance_m: number; confidence: number | null } & ProposalReviewState)[]
  diagnostics: string[]
  apply_policy: 'human_review_only'
  affects_original_report: false
  disclosure: string
}

export type SamplingExperiment = {
  report_id: string
  status: 'experimental' | 'insufficient_recorded_samples' | 'insufficient_evaluation_budget'
  sample_count?: number
  training_ids?: string[]
  validation_ids?: string[]
  evaluation?: { evaluated_count: number; unknown_measurements: number; false_reachable_count: number; false_unreachable_count: number; unresolved_count: number; mae_minutes: number | null }
  baseline?: { method: string; mae_minutes: number | null; false_reachable_count: number; false_unreachable_count: number }
  enabled_for_official_analysis: false
  external_route_pairs_used: number
  disclosure: string
  layers?: SamplingLayers
}

export type CoverageOptimization = {
  report_id: string
  status: 'OPTIMAL' | 'FEASIBLE'
  selected_candidate_ids: string[]
  selected_count: number
  candidate_count: number
  covered_grid_count: number
  unknown_route_pairs: number
  coverage_evidence_status: 'partial_lower_bound' | 'complete_for_selected_grid_pairs'
  candidate_evidence: { candidate_id: string; category: string; covered_grid_ids: string[]; unknown_grid_ids: string[]; sources: string[] }[]
  total_cost: number | null
  affects_original_report: false
  disclosure: string
  combination?: Combination
  pareto_solutions?: PlanningOptimization['pareto_solutions']
}
