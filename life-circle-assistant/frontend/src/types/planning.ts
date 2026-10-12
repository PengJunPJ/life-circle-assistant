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
  }
}

export type PlanningResponse = AiInterpretation & {
  id: string
  report_id: string
  question: string
  tool_calls: PlanningToolCall[]
  simulations: SimulationResult[]
}

export type PlanningParameters = {
  message: string
  previous_turn_id?: string
  selected_location?: { lng: number; lat: number }
  grid_id?: string
}
