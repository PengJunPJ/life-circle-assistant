import type { AnalysisCenter } from './location'
import type { AnalysisMinutes, AnalysisMode } from './report'

export type IntentDraft = {
  address: string
  use_current_center: boolean
  minutes: AnalysisMinutes | null
  mode: AnalysisMode
  categories: string[]
  defaulted_fields: ('minutes' | 'mode' | 'categories')[]
}

export type AnalysisIntent = {
  draft: IntentDraft
  parser: 'llm' | 'rules' | 'rules_degraded'
  model: string | null
  missing_fields: ('location' | 'minutes' | 'categories')[]
  message: string
}

export type ConfirmedAnalysisIntent = {
  center: AnalysisCenter
  minutes: AnalysisMinutes
  mode: AnalysisMode
  categories: string[]
}
