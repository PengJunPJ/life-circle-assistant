<template>
  <main class="app-shell">
    <AppHeader
      :has-report="Boolean(report)"
      :theme="theme"
      :map-status-loading="mapStatusLoading"
      :map-status-available="Boolean(mapStatus)"
      :real-api-ready="Boolean(mapStatus?.real_api_available)"
      @update:theme="applyTheme"
      @open-guide="openFirstUseGuide"
    />
    <p class="sr-only" role="status" aria-live="polite" aria-atomic="true">{{ accessibilityStatus }}</p>
    <p v-if="analysisError" class="sr-only" role="alert">分析失败：{{ analysisError }}</p>
    <section ref="workspaceRef" class="workspace" :class="{ 'left-collapsed': collapsedControls, 'right-collapsed': collapsedReport }">
      <AnalysisControls
        id="analysis-controls-panel"
        :class="{ 'mobile-open': activeMobilePanel === 'controls', collapsed: collapsedControls }"
        :mobile-open="activeMobilePanel === 'controls'"
        :center="center"
        :address-query="addressQuery"
        :candidates="candidates"
        :coordinate-lng="coordinateLng"
        :coordinate-lat="coordinateLat"
        :location-error="locationError"
        :searching="searching"
        :resolving="resolving"
        :mode="mode"
        :minutes="minutes"
        :visible-categories="visibleCategories"
        :show-normal="showNormal"
        :show-sparse="showSparse"
        :show-critical="showCritical"
        :loading="loading"
        :source="report?.source || center.source"
        :map-status="mapStatus"
        :map-status-loading="mapStatusLoading"
        :real-map-ready="realMapReady"
        @update:address-query="addressQuery = $event"
        @update:coordinate-lng="coordinateLng = $event"
        @update:coordinate-lat="coordinateLat = $event"
        @update:mode="mode = $event"
        @update:minutes="minutes = $event"
        @update:show-normal="showNormal = $event"
        @update:show-sparse="showSparse = $event"
        @update:show-critical="showCritical = $event"
        @search-address="searchCandidates"
        @select-candidate="selectCandidate"
        @apply-coordinates="applyCoordinateInput"
        @toggle-category="toggleCategory"
        @run="startAnalysis"
        @refresh-map-status="loadMapStatus"
        @toggle-collapse="collapsedControls = !collapsedControls"
        @close-mobile="closeMobilePanel('controls')"
      />
      <MapStage
        :report="report"
        :analysis-center="center"
        :minutes="minutes"
        :visible-categories="visibleCategories"
        :show-normal="showNormal"
        :show-sparse="showSparse"
        :show-critical="showCritical"
        :loading="loading"
        :progress="progress"
        :progress-label="progressLabel"
        :all-expanded="!collapsedControls && !collapsedReport"
        :all-collapsed="collapsedControls && collapsedReport"
        :focus-recommendation-id="selectedRecommendationId"
        :simulation="simulationResult"
        :simulation-picking="simulationPicking"
        @map-ready="handleMapReady"
        @select-center="selectMapPoint"
        @select-simulation-location="selectSimulationMapLocation"
        @refresh="startAnalysis"
        @service-area-select="handleServiceAreaSelect"
        @expand-all="expandAllPanels"
        @collapse-all="collapseAllPanels"
      />
      <ReportPanel
        id="analysis-report-panel"
        :class="{ 'mobile-open': activeMobilePanel === 'report', collapsed: collapsedReport }"
        :mobile-open="activeMobilePanel === 'report'"
        :report="report"
        :selected-recommendation-id="selectedRecommendationId"
        :history-items="historyItems"
        :history-total="historyTotal"
        :history-loading="historyLoading"
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
        :simulation-loading="simulationLoading"
        :simulation-picking="simulationPicking"
        :simulation-error="simulationError"
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
        @pick-simulation-location="beginSimulationMapPick"
        @run-simulation="runSimulation"
        @clear-simulation="clearSimulation"
        @toggle-collapse="collapsedReport = !collapsedReport"
        @close-mobile="closeMobilePanel('report')"
      />
      <button
        class="panel-rail left"
        :class="{ show: collapsedControls }"
        type="button"
        aria-label="展开分析参数面板"
        @click="collapsedControls = false"
      ><span class="rail-dot" aria-hidden="true"></span><b>分析参数</b></button>
      <button
        class="panel-rail right"
        :class="{ show: collapsedReport }"
        type="button"
        aria-label="展开体检报告面板"
        @click="collapsedReport = false"
      ><span class="rail-dot" aria-hidden="true"></span><b>体检报告</b></button>
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
      :map-status="mapStatus"
      :map-status-loading="mapStatusLoading"
      :real-map-ready="realMapReady"
      @step-change="handleGuideStepChange"
      @close="closeFirstUseGuide"
    />
  </main>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { fetchMapStatus } from './services/analysisApi'
import type { MapStatus } from './types/report'
import { useAnalysis } from './composables/useAnalysis'
import { useReportHistory } from './composables/useReportHistory'
import { useAnalysisCenter } from './composables/useAnalysisCenter'
import { useReportComparison } from './composables/useReportComparison'
import { useSimulation } from './composables/useSimulation'
import { recommendationForServiceArea } from './utils/recommendationLinks'
import AppHeader from './components/AppHeader.vue'
import AnalysisControls from './components/AnalysisControls.vue'
import MapStage from './components/MapStage.vue'
import FirstUseGuide from './components/FirstUseGuide.vue'
// 报告、图表、历史和导出只在工作台完成分析后使用，拆成异步块避免阻塞地图首屏。
const ReportPanel = defineAsyncComponent(() => import('./components/ReportPanel.vue'))
const ReportComparisonPanel = defineAsyncComponent(() => import('./components/ReportComparisonPanel.vue'))

const FIRST_USE_GUIDE_KEY = 'life-circle:first-use-guide:v1'
const selectedRecommendationId = ref<string | null>(null)
const activeMobilePanel = ref<'controls' | 'report' | null>(null)
const collapsedControls = ref(false)
const collapsedReport = ref(false)
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
const realMapReady = ref(false)
const guideOpen = ref(false)
const controlsTrigger = ref<HTMLButtonElement | null>(null)
const reportTrigger = ref<HTMLButtonElement | null>(null)
const workspaceRef = ref<HTMLElement | null>(null)
const {
  center,
  addressQuery,
  candidates,
  coordinateLng,
  coordinateLat,
  searching,
  resolving,
  error: locationError,
  searchCandidates,
  selectCandidate,
  restoreCenter,
  selectMapPoint,
  applyCoordinateInput,
} = useAnalysisCenter()
const {
  mode,
  minutes,
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
  toggleCategory,
  applyReport,
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
} = useSimulation(report)
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

function keepWorkspaceAtOrigin() {
  if (!workspaceRef.value) return
  workspaceRef.value.scrollTop = 0
  workspaceRef.value.scrollLeft = 0
}

function expandAllPanels() {
  collapsedControls.value = false
  collapsedReport.value = false
}

function collapseAllPanels() {
  collapsedControls.value = true
  collapsedReport.value = true
}

function handleWorkspaceKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && activeMobilePanel.value) {
    const panel = activeMobilePanel.value
    event.preventDefault()
    closeMobilePanel(panel)
  }
}

async function startAnalysis() {
  selectedRecommendationId.value = null
  await runAnalysis()
  if (report.value) await loadHistory()
}

async function handleOpenHistory(reportId: string) {
  const selected = await openHistory(reportId)
  if (selected) applySelectedReport(selected)
}

async function handleRerunHistory(reportId: string) {
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
  } catch {
    mapStatus.value = null
  } finally {
    mapStatusLoading.value = false
  }
}

function openFirstUseGuide() {
  guideOpen.value = true
  handleGuideStepChange(0)
}

function handleGuideStepChange(index: number) {
  activeMobilePanel.value = index === 4 ? 'report' : 'controls'
  nextTick(keepWorkspaceAtOrigin)
}

function closeFirstUseGuide(completed: boolean) {
  guideOpen.value = false
  window.localStorage.setItem(FIRST_USE_GUIDE_KEY, completed ? 'completed' : 'dismissed')
  activeMobilePanel.value = 'controls'
}

function applySelectedReport(selected: NonNullable<typeof report.value>) {
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
  if (!serviceAreaId || !report.value) {
    selectedRecommendationId.value = null
    return
  }
  const recommendation = recommendationForServiceArea(report.value.recommendations, serviceAreaId)
  selectedRecommendationId.value = recommendation?.id || null
}

onMounted(() => {
  loadHistory()
  loadMapStatus()
  if (!window.localStorage.getItem(FIRST_USE_GUIDE_KEY)) {
    window.setTimeout(openFirstUseGuide, 350)
  }
  window.addEventListener('keydown', handleWorkspaceKeydown)
})
onBeforeUnmount(() => window.removeEventListener('keydown', handleWorkspaceKeydown))
</script>
