<template>
  <main class="app-shell">
    <AppHeader
      :has-report="Boolean(report)"
      :theme="theme"
      :map-status-loading="mapStatusLoading"
      :map-status-available="Boolean(mapStatus)"
      :real-api-configured="Boolean(mapStatus?.real_api_configured)"
      :real-api-verified="Boolean(mapProbeResult?.verified)"
      :active-workbench="activeWorkbench"
      @update:theme="applyTheme"
      @open-guide="openFirstUseGuide"
      @toggle-workbench="toggleWorkbench"
    />
    <p class="sr-only" role="status" aria-live="polite" aria-atomic="true">{{ accessibilityStatus }}</p>
    <p v-if="analysisError" class="sr-only" role="alert">分析失败：{{ analysisError }}</p>
    <section ref="workspaceRef" class="workspace has-conversation" :style="{ '--conversation-height': `${conversationHeight}px` }" :class="{ 'left-collapsed': collapsedControls, 'right-collapsed': collapsedReport, 'report-active': activeWorkbench === 'report' }">
      <AnalysisControls
        id="analysis-controls-panel"
        :class="{ 'mobile-open': activeMobilePanel === 'controls', collapsed: collapsedControls }"
        :mobile-open="activeMobilePanel === 'controls'"
        :center="center"
        :address-query="addressQuery"
        :candidates="candidates"
        :coordinate-lng="coordinateLng"
        :coordinate-lat="coordinateLat"
        :coordinate-system="coordinateSystem"
        :coordinate-conversion-note="coordinateConversionNote"
        :location-error="locationError"
        :location-pending="locationPending"
        :center-picking="centerPicking"
        :searching="searching"
        :resolving="resolving"
        :mode="mode"
        :minutes="minutes"
        :minutes-valid="minutesValid"
        :report="report"
        :analysis-error="analysisError"
        :analysis-categories="analysisCategories"
        :supplement-count="supplementCategories.length"
        :loading="loading"
        :assistant-busy="conversationBusy"
        :map-status="mapStatus"
        :map-status-loading="mapStatusLoading"
        :map-probe-result="mapProbeResult"
        :map-probe-loading="mapProbeLoading"
        :real-map-ready="realMapReady"
        @update:address-query="updateAddressQuery"
        @update:coordinate-lng="coordinateLng = $event"
        @update:coordinate-lat="coordinateLat = $event"
        @update:coordinate-system="coordinateSystem = $event; coordinateConversionNote = ''"
        @update:mode="mode = $event"
        @update:minutes="minutes = $event; minutesValid = true"
        @update:analysis-categories="setAnalysisCategories"
        @update:input-blocked="inputBlocked = $event"
        @update:intent-busy="intentBusy = $event"
        @search-address="searchCandidates"
        @select-candidate="selectCandidate"
        @apply-coordinates="applyCoordinateInput"
        @pick-center="beginCenterPick"
        @run="startAnalysis"
        @fill-intent="fillIntentParameters"
        @refresh-map-status="refreshMapStatus"
        @probe-map-api="probeConfiguredMapApi"
        @close-mobile="closeMobilePanel('controls')"
      />
      <MapStage
        :report="report"
        :analysis-center="center"
        :minutes="report?.parameters.minutes ?? minutes"
        :visible-categories="visibleCategories"
        :show-normal="showNormal"
        :show-sparse="showSparse"
        :show-critical="showCritical"
        :status-layers="statusLayers"
        :sampling-layers="samplingLayers"
        :combination="combinationResult"
        :loading="loading"
        :interaction-blocked="conversationBusy"
        :progress="progress"
        :progress-label="progressLabel"
        :focus-recommendation-id="selectedRecommendationId"
        :focus-grid-id="planningGridId"
        :simulation="simulationResult"
        :simulation-picking="simulationPicking"
        :center-picking="centerPicking"
        @map-ready="handleMapReady"
        @select-center="handleCenterPick"
        @select-simulation-location="selectSimulationMapLocation"
        @update:visible-categories="setVisibleCategories"
        @update:show-normal="showNormal = $event"
        @update:show-sparse="showSparse = $event"
        @update:show-critical="showCritical = $event"
        @update:status-layers="applyStatusLayers"
        @prepare-supplement="prepareSupplement"
        @cancel-center-pick="cancelCenterPick"
        @service-area-select="!conversationBusy && handleServiceAreaSelect($event)"
      />
      <ReportPanel
        id="analysis-report-panel"
        :class="{ 'mobile-open': activeMobilePanel === 'report', collapsed: collapsedReport }"
        :mobile-open="activeMobilePanel === 'report'"
        :report="report"
        :selected-recommendation-id="selectedRecommendationId"
        :history-items="historyItems"
        :history-total="historyTotal"
        :history-loading="historyLoading || conversationBusy"
        :history-loading-more="historyLoadingMore"
        :history-has-more="historyHasMore"
        :history-query="historyQuery"
        :history-error="historyError"
        :opening-report-id="openingReportId"
        :rerunning-report-id="rerunningReportId"
        :selected-report-ids="selectedReportIds"
        :comparison-loading="comparisonLoading"
        :comparison-error="comparisonError"
        :simulation-category="simulationCategory"
        :simulation-location="simulationLocation"
        :simulation-result="simulationResult"
        :simulation-loading="simulationLoading || conversationBusy"
        :simulation-picking="simulationPicking"
        :simulation-error="simulationError"
        :planning-grid-id="planningGridId"
        :governance-revision="governanceRevision"
        :guide-page="guideOpen ? guideStep?.reportPage : null"
        @locate-recommendation="selectedRecommendationId = $event"
        @refresh-history="loadHistory"
        @open-history="handleOpenHistory"
        @rerun-history="handleRerunHistory"
        @toggle-comparison="toggleComparisonReport"
        @compare-history="compareSelection"
        @search-history="searchHistory"
        @load-more-history="loadMoreHistory"
        @simulate-candidate="simulateRecommendationCandidate"
        @update:simulation-category="selectSimulationCategory"
        @pick-simulation-location="beginSimulationPick"
        @run-simulation="runSimulation"
        @clear-simulation="clearSimulation"
        @assistant-simulation="applyAssistantSimulation"
        @new-report="applySelectedReport"
        @sampling="showSamplingLayers"
        @combination="combinationResult = $event"
        @close-mobile="closeMobilePanel('report')"
      />
      <ConversationWorkspace
        :context="conversationContext"
        :turns="conversationTurns"
        :ready="conversationReady"
        :busy="conversationBusy"
        :restoring="conversationRestoring"
        :error="conversationError"
        :can-retry="Boolean(conversationRetryRequest)"
        :pending="conversationPending"
        :task="currentTask"
        :analyzing="loading"
        :progress="progress"
        :progress-label="progressLabel || ''"
        :cancelling="cancelling"
        @send="sendConversation"
        @confirm="confirmConversation"
        @retry="retryConversation"
        @reconnect="initializeConversation"
        @cancel-task="cancelCurrentTask"
        @retry-task="retryCurrentTask"
        @open-report="handleOpenHistory"
        @simulation="applyAssistantSimulation"
        @sampling="showSamplingLayers"
        @combination="combinationResult = $event"
        @resize="conversationHeight = $event"
      />
      <button
        v-if="activeMobilePanel"
        class="mobile-panel-backdrop"
        aria-label="关闭当前面板并返回地图"
        @click="closeMobilePanel(activeMobilePanel)"
      ></button>
      <nav class="mobile-workspace-actions" aria-label="移动端工作台">
        <button
          ref="controlsTrigger"
          type="button"
          aria-controls="analysis-controls-panel"
          :aria-expanded="activeMobilePanel === 'controls'"
          @click="toggleMobilePanel('controls')"
        ><span aria-hidden="true">☰</span><strong>分析参数</strong></button>
        <button
          ref="reportTrigger"
          type="button"
          aria-controls="analysis-report-panel"
          :aria-expanded="activeMobilePanel === 'report'"
          @click="toggleMobilePanel('report')"
        ><span aria-hidden="true">▤</span><strong>体检报告</strong><em v-if="report" aria-label="报告已生成">已完成</em></button>
      </nav>
    </section>
    <ReportComparisonPanel
      v-if="comparison"
      :comparison="comparison"
      @close="closeComparison"
      @open-report="handleOpenComparisonReport"
    />
    <FirstUseGuide
      :open="guideOpen"
      :has-report="Boolean(report)"
      :map-status="mapStatus"
      :map-status-loading="mapStatusLoading"
      :map-probe-result="mapProbeResult"
      :real-map-ready="realMapReady"
      @step-change="handleGuideStepChange"
      @close="closeFirstUseGuide"
    />
  </main>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { downloadReportExport, fetchMapStatus, getAnalysisTask, getHistoricalReport, probeMapApi as requestMapApiProbe } from './services/analysisApi'
import type { AnalysisTask, MapProbeResult, MapStatus } from './types/report'
import type { GuideStep } from './types/guide'
import type { AnalysisIntent } from './types/analysisIntent'
import { ALL_CATEGORIES } from './constants/facilities'
import { useAnalysis } from './composables/useAnalysis'
import { useReportHistory } from './composables/useReportHistory'
import { useAnalysisCenter } from './composables/useAnalysisCenter'
import { useReportComparison } from './composables/useReportComparison'
import { useSimulation } from './composables/useSimulation'
import { useConversation } from './composables/useConversation'
import type { ConversationTurn, WorkspaceState } from './types/workspace'
import { DEFAULT_STATUS_LAYERS, type Combination, type SamplingLayers, type StatusLayers } from './types/completion'
import { recommendationForServiceArea } from './utils/recommendationLinks'
import AppHeader from './components/AppHeader.vue'
import AnalysisControls from './components/AnalysisControls.vue'
import MapStage from './components/MapStage.vue'
import FirstUseGuide from './components/FirstUseGuide.vue'
import ConversationWorkspace from './components/ConversationWorkspace.vue'
// 报告、图表、历史和导出只在工作台完成分析后使用，拆成异步块避免阻塞地图首屏。
const ReportPanel = defineAsyncComponent(() => import('./components/ReportPanel.vue'))
const ReportComparisonPanel = defineAsyncComponent(() => import('./components/ReportComparisonPanel.vue'))

const FIRST_USE_GUIDE_KEY = 'life-circle:first-use-guide:v1'
const selectedRecommendationId = ref<string | null>(null)
const planningGridId = ref<string | null>(null)
const statusLayers = ref<StatusLayers>({ ...DEFAULT_STATUS_LAYERS })
const samplingLayers = ref<SamplingLayers | null>(null)
const combinationResult = ref<Combination | null>(null)
const governanceRevision = ref(0)
type ActiveWorkbench = 'controls' | 'report' | null
const activeWorkbench = ref<ActiveWorkbench>('controls')
const collapsedControls = computed({
  get: () => activeWorkbench.value !== 'controls',
  set: (collapsed: boolean) => { if (collapsed) { if (activeWorkbench.value === 'controls') activeWorkbench.value = null } else activeWorkbench.value = 'controls' },
})
const collapsedReport = computed({
  get: () => activeWorkbench.value !== 'report',
  set: (collapsed: boolean) => { if (collapsed) { if (activeWorkbench.value === 'report') activeWorkbench.value = null } else activeWorkbench.value = 'report' },
})
const activeMobilePanel = ref<'controls' | 'report' | null>(null)
const conversationHeight = ref(130)
const THEME_KEY = 'life-circle:theme:v1'
const theme = ref<'dark' | 'light'>(window.localStorage.getItem(THEME_KEY) === 'light' ? 'light' : 'dark')
const THEME_DURATION = 420
const THEME_FEATHER = 160
let themeBooted = false
function commitTheme(value: 'dark' | 'light') {
  theme.value = value
  document.documentElement.setAttribute('data-theme', value)
  window.localStorage.setItem(THEME_KEY, value)
  window.dispatchEvent(new CustomEvent('life-circle:theme'))
}
function applyTheme(value: 'dark' | 'light', event?: MouseEvent) {
  // 首次挂载直接落色，不做过渡
  if (!themeBooted) {
    themeBooted = true
    commitTheme(value)
    return
  }
  if (value === theme.value) return

  const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  const supportsVT = typeof document.startViewTransition === 'function'
  // 用户偏好减少动效 或 浏览器不支持 VT：直接切换 + crossfade 兜底
  if (reduceMotion || !supportsVT || !event) {
    document.documentElement.classList.add('theme-transitioning')
    commitTheme(value)
    window.setTimeout(() => document.documentElement.classList.remove('theme-transitioning'), 320)
    return
  }

  // View Transitions：以点击位置为圆心的羽化软边扩散
  const root = document.documentElement
  const x = event.clientX
  const y = event.clientY
  const endRadius = Math.hypot(
    Math.max(x, window.innerWidth - x),
    Math.max(y, window.innerHeight - y),
  )
  root.style.setProperty('--vt-x', `${x}px`)
  root.style.setProperty('--vt-y', `${y}px`)
  const transition = document.startViewTransition(() => {
    commitTheme(value)
  })
  transition.ready
    .then(() => {
      root.animate(
        { '--vt-r': [`0px`, `${endRadius + THEME_FEATHER}px`] },
        {
          duration: THEME_DURATION,
          easing: 'cubic-bezier(.33,1,.68,1)', // ease-out：前快后慢，收尾减速
          pseudoElement: '::view-transition-new(root)',
          fill: 'forwards',
        },
      )
    })
    .catch(() => { /* 动画被中断时忽略 */ })
}
applyTheme(theme.value)
const mapStatus = ref<MapStatus | null>(null)
const mapStatusLoading = ref(true)
const mapProbeResult = ref<MapProbeResult | null>(null)
const mapProbeLoading = ref(false)
const realMapReady = ref(false)
const guideOpen = ref(false)
const guideStep = ref<GuideStep | null>(null)
let guidePreviousPanels: { workbench: ActiveWorkbench; mobile: typeof activeMobilePanel.value } | null = null
const controlsTrigger = ref<HTMLButtonElement | null>(null)
const reportTrigger = ref<HTMLButtonElement | null>(null)
const workspaceRef = ref<HTMLElement | null>(null)
const centerPicking = ref(false)
const minutesValid = ref(true)
const inputBlocked = ref(false)
const intentBusy = ref(false)
const {
  center,
  addressQuery,
  candidates,
  coordinateLng,
  coordinateLat,
  coordinateSystem,
  coordinateConversionNote,
  searching,
  resolving,
  error: locationError,
  locationPending,
  updateAddressQuery,
  requireLocation,
  searchCandidates,
  selectCandidate,
  restoreCenter,
  selectMapPoint,
  applyCoordinateInput,
} = useAnalysisCenter()
const {
  mode,
  minutes,
  analysisCategories,
  supplementCategories,
  visibleCategories,
  showNormal,
  showSparse,
  showCritical,
  loading,
  progress,
  progressLabel,
  report,
  error: analysisError,
  runAnalysis,
  setVisibleCategories,
  setAnalysisCategories,
  applyReport,
  currentTask = ref<AnalysisTask | null>(null),
  cancelling = ref(false),
  followTask,
  cancelCurrentTask,
  retryCurrentTask,
} = useAnalysis(center)
const {
  category: simulationCategory,
  location: simulationLocation,
  result: simulationResult,
  loading: simulationLoading,
  picking: simulationPicking,
  error: simulationError,
  selectCategory: selectSimulationCategory,
  beginMapPick: beginSimulationMapPick,
  selectMapLocation: selectSimulationMapLocation,
  simulateCandidate: simulateRecommendationCandidate,
  run: runSimulation,
  clear: clearSimulation,
  applyAssistantSimulation,
} = useSimulation(report)
watch(() => report.value?.report_id, () => { planningGridId.value = null; samplingLayers.value = null; combinationResult.value = null })
watch([showNormal, showSparse, showCritical], ([normal, sparse, critical]) => { statusLayers.value = { ...statusLayers.value, normal, sparse, critical } })
function applyStatusLayers(layers: Partial<StatusLayers>) {
  statusLayers.value = { ...statusLayers.value, ...layers }
  if (layers.normal !== undefined) showNormal.value = layers.normal
  if (layers.sparse !== undefined) showSparse.value = layers.sparse
  if (layers.critical !== undefined) showCritical.value = layers.critical
}
function showSamplingLayers(layers: SamplingLayers) { samplingLayers.value = layers; applyStatusLayers({ sampling: true }) }
const {
  items: historyItems,
  total: historyTotal,
  loading: historyLoading,
  loadingMore: historyLoadingMore,
  hasMore: historyHasMore,
  query: historyQuery,
  error: historyError,
  openingReportId,
  rerunningReportId,
  loadHistory,
  loadMoreHistory,
  searchHistory,
  openHistory,
  rerunHistory,
} = useReportHistory()
const {
  selectedReportIds,
  comparison,
  loading: comparisonLoading,
  error: comparisonError,
  toggleReport: toggleComparisonReport,
  compareSelection,
  closeComparison,
} = useReportComparison()

function getWorkspaceState(): WorkspaceState {
  const boundReport = reportMatchesParameters.value ? report.value : null
  const task = currentTask.value
  const taskRequest = task?.request
  const boundTask = Boolean(taskRequest && minutesValid.value && !locationPending.value && center.value.supportStatus === 'supported'
    && taskRequest.lng === center.value.lng && taskRequest.lat === center.value.lat
    && taskRequest.minutes === minutes.value && taskRequest.mode === mode.value
    && taskRequest.categories.length === analysisCategories.value.length
    && taskRequest.categories.every(category => analysisCategories.value.includes(category)))
  return {
    center: !locationPending.value && center.value.supportStatus === 'supported' ? {
      lng: center.value.lng, lat: center.value.lat, address: center.value.address, selection_method: center.value.selectionMethod,
    } : null,
    minutes: minutes.value,
    minutes_confirmed: minutesValid.value,
    mode: mode.value,
    categories: [...analysisCategories.value],
    report_id: boundReport?.report_id || null,
    grid_id: boundReport ? planningGridId.value : null,
    visible_categories: visibleCategories.value.filter(category => analysisCategories.value.includes(category)),
    analysis_task_id: boundTask && task ? task.id : null,
    status_layers: { ...statusLayers.value, normal: showNormal.value, sparse: showSparse.value, critical: showCritical.value },
    address_candidates: candidates.value.map(item => ({ lng: item.lng, lat: item.lat, address: item.address })),
    history_report_ids: historyItems.value.map(item => item.report_id),
  }
}

async function restoreWorkspaceState(state: WorkspaceState) {
  if (state.report_id && state.report_id !== report.value?.report_id) applySelectedReport(await getHistoricalReport(state.report_id))
  if (!state.report_id) report.value = null
  if (state.center) restoreCenter({ ...state.center, source: report.value?.source || 'workspace', selectionMethod: state.center.selection_method })
  else requireLocation()
  minutes.value = state.minutes
  minutesValid.value = state.minutes_confirmed !== false
  mode.value = state.mode
  setAnalysisCategories(state.categories)
  setVisibleCategories(state.visible_categories)
  applyStatusLayers({ ...DEFAULT_STATUS_LAYERS, ...state.status_layers })
  if (state.address_candidates) candidates.value = state.address_candidates.map(item => ({ ...item, source: 'workspace', provider: 'workspace' }))
  await nextTick()
  focusConversationGrid(state.grid_id)
  if (state.analysis_task_id && !loading.value) { const task = await getAnalysisTask(state.analysis_task_id); currentTask.value = task; if (['queued', 'running', 'completed'].includes(task.status)) void followTask(task) }
}

async function applyConversationTurn(turn: ConversationTurn) {
  for (const action of turn.actions) {
    if (action.type === 'apply_parameters') await fillIntentParameters(turn.intent || { draft: action.draft, parser: 'rules', model: null, missing_fields: [], message: '' }, !turn.actions.some(item => item.type === 'show_address_candidates'))
    else if (action.type === 'show_report' || action.type === 'open_report') { applySelectedReport(await getHistoricalReport(action.report_id)); await nextTick() }
    else if (action.type === 'focus_grid') focusConversationGrid(action.grid_id)
    else if (action.type === 'set_layers') setVisibleCategories(action.categories)
    else if (action.type === 'set_status_layers') applyStatusLayers(action.layers)
    else if (action.type === 'show_address_candidates') { requireLocation(); candidates.value = action.items.map(item => ({ ...item, source: 'workspace', provider: 'workspace' })) }
    else if (action.type === 'select_address_candidate') { restoreCenter({ ...action.candidate, source: 'workspace', selectionMethod: action.candidate.selection_method || 'address' }); candidates.value = [] }
    else if (action.type === 'task_cancelled') currentTask.value = turn.task || await getAnalysisTask(action.task_id)
    else if (action.type === 'show_history') { historyItems.value = action.items; historyTotal.value = action.items.length }
    else if (action.type === 'download_report') await downloadReportExport(action.report_id, action.format)
    else if (action.type === 'analysis_started' && !loading.value) void followTask(turn.task || await getAnalysisTask(action.task_id))
  }
  if (turn.optimization?.combination) combinationResult.value = turn.optimization.combination
  if (turn.sampling_experiment?.layers) showSamplingLayers(turn.sampling_experiment.layers)
  if (turn.governance_state || turn.semantic_review || turn.observation) governanceRevision.value += 1
}

function focusConversationGrid(gridId: string | null) {
  const area = report.value?.service_areas.features.find(item => item.properties.grid_id === gridId)
  if (area) {
    setVisibleCategories([...visibleCategories.value, area.properties.category])
    if (area.properties.kind === 'normal') showNormal.value = true
    else if (area.properties.kind === 'sparse') showSparse.value = true
    else if (area.properties.kind === 'critical') showCritical.value = true
  }
  handleServiceAreaSelect(area ? gridId : null)
}

const reportMatchesParameters = computed(() => {
  const selected = report.value
  return Boolean(selected && minutesValid.value && !locationPending.value && center.value.supportStatus === 'supported'
    && selected.center.lng === center.value.lng && selected.center.lat === center.value.lat
    && selected.parameters.minutes === minutes.value && selected.parameters.mode === mode.value
    && selected.parameters.categories.length === analysisCategories.value.length
    && selected.parameters.categories.every(category => analysisCategories.value.includes(category)))
})
const {
  turns: conversationTurns,
  ready: conversationReady,
  busy: conversationBusy,
  restoring: conversationRestoring,
  error: conversationError,
  retryRequest: conversationRetryRequest,
  pending: conversationPending,
  initialize: initializeConversation,
  scheduleSync: scheduleConversationSync,
  send: sendConversation,
  confirm: confirmConversation,
  retry: retryConversation,
  dispose: disposeConversation,
} = useConversation({ getState: getWorkspaceState, applyState: restoreWorkspaceState, applyTurn: applyConversationTurn })
const conversationContext = computed(() => `${locationPending.value ? '位置待确认' : center.value.address} · ${minutesValid.value ? `${minutes.value}分钟` : '时间待确认'} · ${analysisCategories.value.length}类${planningGridId.value && reportMatchesParameters.value ? ` · ${planningGridId.value}` : ''}${reportMatchesParameters.value ? ' · 当前报告' : report.value ? ' · 参数已变更，待重新体检' : ''}`)
watch(getWorkspaceState, scheduleConversationSync, { deep: true })
watch(() => report.value?.report_id, id => { if (id) void loadHistory() })

const accessibilityStatus = computed(() => {
  if (locationError.value) return `分析中心点需要处理：${locationError.value}`
  if (analysisError.value) return `分析失败：${analysisError.value}`
  if (loading.value) return `分析进行中，当前进度 ${progress.value}%`
  if (report.value) {
    return report.value.completeness === 'partial'
      ? '分析已完成，但部分数据不可用。请打开体检报告查看数据质量说明。'
      : '分析已完成。可以打开体检报告查看评分、服务区域和规划建议。'
  }
  return '尚未生成分析报告。'
})

async function toggleMobilePanel(panel: 'controls' | 'report') {
  if (activeMobilePanel.value === panel) {
    closeMobilePanel(panel)
    return
  }
  activeMobilePanel.value = panel
  await nextTick()
  document.querySelector<HTMLElement>(`#analysis-${panel === 'controls' ? 'controls' : 'report'}-panel .mobile-panel-close`)?.focus({ preventScroll: true })
  keepWorkspaceAtOrigin()
  window.requestAnimationFrame(keepWorkspaceAtOrigin)
}

function closeMobilePanel(panel: 'controls' | 'report') {
  activeMobilePanel.value = null
  nextTick(() => {
    const trigger = panel === 'controls' ? controlsTrigger.value : reportTrigger.value
    trigger?.focus({ preventScroll: true })
    keepWorkspaceAtOrigin()
  })
}

function toggleWorkbench(panel: 'controls' | 'report') {
  activeWorkbench.value = activeWorkbench.value === panel ? null : panel
}

function keepWorkspaceAtOrigin() {
  if (!workspaceRef.value) return
  workspaceRef.value.scrollTop = 0
  workspaceRef.value.scrollLeft = 0
}

function handleWorkspaceKeydown(event: KeyboardEvent) {
  if (guideOpen.value) return
  if (event.key === 'Escape' && centerPicking.value) {
    event.preventDefault()
    cancelCenterPick()
    return
  }
  if (event.key === 'Escape' && activeMobilePanel.value) {
    const panel = activeMobilePanel.value
    event.preventDefault()
    closeMobilePanel(panel)
  }
}

async function fillIntentParameters(intent: AnalysisIntent, resolveAddress = true) {
  if (loading.value || resolving.value || searching.value) return
  minutesValid.value = intent.draft.minutes !== null
  if (intent.draft.minutes) minutes.value = intent.draft.minutes
  mode.value = intent.draft.mode
  setAnalysisCategories(intent.draft.categories)
  if (intent.draft.use_current_center) {
    if (center.value.supportStatus === 'supported') restoreCenter(center.value)
    else requireLocation()
    return
  }
  if (!intent.draft.address.trim()) { requireLocation(); return }
  updateAddressQuery(intent.draft.address)
  if (resolveAddress) await searchCandidates()
  else requireLocation()
}

async function startAnalysis() {
  if (conversationBusy.value || loading.value || resolving.value || searching.value || centerPicking.value || inputBlocked.value || locationPending.value || !minutesValid.value || locationError.value || center.value.supportStatus !== 'supported') return
  selectedRecommendationId.value = null
  const completed = await runAnalysis()
  if (completed && report.value) {
    restoreCenter({ lng: report.value.center.lng, lat: report.value.center.lat, address: report.value.center.address, source: report.value.source, selectionMethod: report.value.center.selection_method || report.value.parameters.center_selection_method || 'default' })
    await loadHistory()
  }
}

function prepareSupplement() {
  if (conversationBusy.value || !report.value || loading.value || resolving.value || searching.value || intentBusy.value) return
  const original = report.value
  restoreCenter({ ...center.value, ...original.center, source: original.source, selectionMethod: original.center.selection_method || original.parameters.center_selection_method || 'default' })
  minutes.value = original.parameters.minutes
  minutesValid.value = true
  mode.value = original.parameters.mode
  setAnalysisCategories([...ALL_CATEGORIES])
  collapsedControls.value = false
  if (window.matchMedia('(max-width: 820px)').matches) activeMobilePanel.value = 'controls'
}

function beginCenterPick() {
  if (conversationBusy.value || loading.value || resolving.value || searching.value || intentBusy.value) return
  clearSimulation()
  centerPicking.value = true
  if (activeMobilePanel.value) closeMobilePanel(activeMobilePanel.value)
}

function beginSimulationPick() {
  centerPicking.value = false
  beginSimulationMapPick()
}

function cancelCenterPick() {
  centerPicking.value = false
  if (window.matchMedia('(max-width: 820px)').matches) activeMobilePanel.value = 'controls'
}

async function handleCenterPick(lng: number, lat: number) {
  if (conversationBusy.value || loading.value || resolving.value || searching.value || intentBusy.value) return
  const picking = centerPicking.value
  await selectMapPoint(lng, lat)
  centerPicking.value = false
  if (picking && window.matchMedia('(max-width: 820px)').matches) activeMobilePanel.value = 'controls'
}

async function handleOpenHistory(reportId: string) {
  if (conversationBusy.value || loading.value) return
  const selected = await openHistory(reportId)
  if (selected) applySelectedReport(selected)
}

async function handleRerunHistory(reportId: string) {
  if (conversationBusy.value || loading.value) return
  loading.value = true
  progress.value = 12
  try {
    const selected = await rerunHistory(reportId, (value) => { progress.value = value })
    if (selected) applySelectedReport(selected)
  } finally {
    loading.value = false
  }
}

async function handleOpenComparisonReport(reportId: string) {
  const selected = await openHistory(reportId)
  if (selected) {
    applySelectedReport(selected)
    closeComparison()
  }
}

// 真实模式只记录底图就绪状态，不自动提交分析，避免首次访问误消耗 API 配额。
function handleMapReady(value: boolean) {
  realMapReady.value = value
}

async function loadMapStatus() {
  mapStatusLoading.value = true
  try {
    mapStatus.value = await fetchMapStatus()
    if (!mapStatus.value.real_api_configured) mapProbeResult.value = null
  } catch {
    mapStatus.value = null
  } finally {
    mapStatusLoading.value = false
  }
}

async function refreshMapStatus() {
  await loadMapStatus()
}

async function probeConfiguredMapApi() {
  if (!mapStatus.value?.real_api_configured || mapProbeLoading.value) return
  mapProbeLoading.value = true
  try {
    mapProbeResult.value = await requestMapApiProbe()
  } catch {
    mapProbeResult.value = {
      configured: true,
      verified: false,
      checked_at: new Date().toISOString(),
      message: '百度地图地理编码接口探测失败，请检查 Web 服务 AK、权限、配额或网络。',
    }
  } finally {
    mapProbeLoading.value = false
  }
}

function openFirstUseGuide() {
  if (guideOpen.value) return
  guidePreviousPanels = { workbench: activeWorkbench.value, mobile: activeMobilePanel.value }
  guideOpen.value = true
  handleGuideStepChange({ id: 'source', surface: 'controls' })
}

function handleGuideStepChange(step: GuideStep) {
  guideStep.value = step
  const panel = step.surface === 'controls' || step.surface === 'report' ? step.surface : null
  activeWorkbench.value = panel
  activeMobilePanel.value = panel
  nextTick(keepWorkspaceAtOrigin)
}

function closeFirstUseGuide(completed: boolean) {
  if (!guideOpen.value) return
  guideOpen.value = false
  guideStep.value = null
  window.localStorage.setItem(FIRST_USE_GUIDE_KEY, completed ? 'completed' : 'dismissed')
  if (guidePreviousPanels) {
    activeWorkbench.value = guidePreviousPanels.workbench
    activeMobilePanel.value = guidePreviousPanels.mobile
    guidePreviousPanels = null
  }
  nextTick(keepWorkspaceAtOrigin)
}

function applySelectedReport(selected: NonNullable<typeof report.value>) {
  minutesValid.value = true
  selectedRecommendationId.value = null
  restoreCenter({
    lng: selected.center.lng,
    lat: selected.center.lat,
    address: selected.center.address,
    source: selected.center.source || selected.source,
    selectionMethod: selected.center.selection_method || selected.parameters.center_selection_method || 'default',
  })
  applyReport(selected)
}

function handleServiceAreaSelect(serviceAreaId: string | null) {
  planningGridId.value = serviceAreaId
  if (!serviceAreaId || !report.value) {
    selectedRecommendationId.value = null
    return
  }
  const recommendation = recommendationForServiceArea(report.value.recommendations, serviceAreaId)
  selectedRecommendationId.value = recommendation?.id || null
}

onMounted(() => {
  void initializeConversation()
  loadHistory()
  loadMapStatus()
  if (!window.localStorage.getItem(FIRST_USE_GUIDE_KEY)) {
    window.setTimeout(openFirstUseGuide, 350)
  }
  window.addEventListener('keydown', handleWorkspaceKeydown)
})
onBeforeUnmount(() => { window.removeEventListener('keydown', handleWorkspaceKeydown); disposeConversation() })
</script>
