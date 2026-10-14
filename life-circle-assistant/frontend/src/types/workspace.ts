import type { AnalysisIntent, IntentDraft } from './analysisIntent'
import type { CoverageOptimization, SamplingExperiment, SemanticReview } from './aiExtensions'
import type { HistoryReportItem } from './history'
import type { CenterSelectionMethod } from './location'
import type { PlanningResponse } from './planning'
import type { AiEvidenceRef, AiInterpretation, AnalysisMinutes, AnalysisMode, AnalysisTask } from './report'
import type { AudienceReport, Governance, ResidentObservation, StatusLayers } from './completion'
import type { ReportExportFormat } from './exports'

export type WorkspaceAddressCandidate = { lng: number; lat: number; address: string; name?: string; selection_method?: CenterSelectionMethod }

export type WorkspaceState = {
  center: { lng: number; lat: number; address: string; selection_method: CenterSelectionMethod } | null
  minutes: AnalysisMinutes
  minutes_confirmed?: boolean
  mode: AnalysisMode
  categories: string[]
  report_id: string | null
  grid_id: string | null
  visible_categories: string[]
  analysis_task_id?: string | null
  status_layers?: StatusLayers
  address_candidates?: WorkspaceAddressCandidate[]
  history_report_ids?: string[]
  clarification?: Record<string, unknown> | null
  task_plan?: Record<string, unknown>[]
}

export type Workspace = {
  id: string
  revision: number
  state: WorkspaceState
  created_at: string
  updated_at: string
}

export type WorkspaceAction =
  | { type: 'apply_parameters'; draft: IntentDraft }
  | { type: 'show_report'; report_id: string }
  | { type: 'open_report'; report_id: string }
  | { type: 'focus_grid'; grid_id: string }
  | { type: 'set_layers'; categories: string[] }
  | { type: 'set_status_layers'; layers: Partial<StatusLayers> }
  | { type: 'show_address_candidates'; items: WorkspaceAddressCandidate[] }
  | { type: 'select_address_candidate'; candidate: WorkspaceAddressCandidate }
  | { type: 'task_cancelled'; task_id: string }
  | { type: 'analysis_started'; task_id: string }
  | { type: 'show_history'; items: HistoryReportItem[] }
  | { type: 'download_report'; report_id: string; format: ReportExportFormat }

export type ConversationTurn = {
  id: string
  workspace_id: string
  request_id: string
  revision: number
  status: 'completed' | 'awaiting_confirmation' | 'failed'
  message: string
  answer: string
  actions: WorkspaceAction[]
  evidence_refs?: AiEvidenceRef[]
  planning?: PlanningResponse
  interpretation?: AiInterpretation
  intent?: AnalysisIntent
  semantic_review?: SemanticReview
  sampling_experiment?: SamplingExperiment
  optimization?: CoverageOptimization
  governance_state?: Partial<Governance> & { catalog_version: number; requires_recompute?: boolean; audit_event?: Governance['audit'][number] }
  recomputation?: { report_id: string; source_report_id?: string; catalog_version: number; affects_original_report: false }
  observation?: ResidentObservation
  role_report?: AudienceReport
  pending?: { token: string; label: string; budget: { max_route_pairs: number; max_model_calls: number }; command: Record<string, unknown> }
  task?: AnalysisTask
  created_at: string
}
