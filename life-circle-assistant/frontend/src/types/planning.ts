import type { AiInterpretation } from './report'
import type { SimulationResult } from './simulation'

export type PlanningToolCall = {
  id: string
  name: string
  label: string
  arguments: Record<string, unknown>
  status: 'completed' | 'failed'
  duration_ms: number
  error?: string
  result?: {
    summary: string
    source: string
    total?: number
    items?: Record<string, unknown>[]
    simulation?: Pick<SimulationResult, 'id' | 'category' | 'category_label' | 'delta' | 'data_quality'>
    comparison?: PlanningComparison
  }
}

export type PlanningComparisonOption = {
  id: string
  title: string
  category: string
  location_label?: string
  status: 'completed' | 'failed' | 'pending'
  eligible: boolean
  excluded_reason?: string | null
  error?: string
  rank?: number | null
  objective_improvement?: number
  delta?: SimulationResult['delta']
  simulation?: Record<string, unknown>
  location?: { lng: number; lat: number }
}

export type PlanningComparison = {
  id: string
  report_id: string
  goal: 'reduce_critical_zones' | 'increase_coverage' | 'improve_overall_score'
  goal_label: string
  summary: string
  preferred_option_ids: string[]
  disclosure: string
  options: PlanningComparisonOption[]
}

export type PlanningResponse = AiInterpretation & {
  id: string
  report_id: string
  question: string
  tool_calls: PlanningToolCall[]
  simulations: SimulationResult[]
  comparisons: PlanningComparison[]
}

export type PlanningParameters = {
  message: string
  previous_turn_id?: string
  selected_location?: { lng: number; lat: number }
  grid_id?: string
  comparison_goal?: PlanningComparison['goal']
}
