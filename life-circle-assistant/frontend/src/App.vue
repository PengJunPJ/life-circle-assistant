<template>
  <main class="app-shell">
    <AppHeader :has-report="Boolean(report)" />
    <p class="sr-only" role="status" aria-live="polite" aria-atomic="true">{{ accessibilityStatus }}</p>
    <p v-if="analysisError" class="sr-only" role="alert">分析失败：{{ analysisError }}</p>
    <section ref="workspaceRef" class="workspace">
      <AnalysisControls
        id="analysis-controls-panel"
        :class="{ 'mobile-open': activeMobilePanel === 'controls' }"
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
        :focus-recommendation-id="selectedRecommendationId"
        :simulation="simulationResult"
        :simulation-picking="simulationPicking"
        @map-ready="handleMapReady"
        @select-center="selectMapPoint"
        @select-simulation-location="selectSimulationMapLocation"
        @refresh="startAnalysis"
        @service-area-select="handleServiceAreaSelect"
      />
      <ReportPanel
        id="analysis-report-panel"
        :class="{ 'mobile-open': activeMobilePanel === 'report' }"
        :mobile-open="activeMobilePanel === 'report'"
        :report="report"
        :selected-recommendation-id="selectedRecommendationId"
        :history-items="historyItems"
        :history-total="historyTotal"
        :history-loading="historyLoading"
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
        @simulate-candidate="simulateRecommendationCandidate"
        @update:simulation-category="selectSimulationCategory"
        @pick-simulation-location="beginSimulationMapPick"
        @run-simulation="runSimulation"
        @clear-simulation="clearSimulation"
        @close-mobile="closeMobilePanel('report')"
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
  </main>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useAnalysis } from './composables/useAnalysis'
import { useReportHistory } from './composables/useReportHistory'
import { useAnalysisCenter } from './composables/useAnalysisCenter'
import { useReportComparison } from './composables/useReportComparison'
import { useSimulation } from './composables/useSimulation'
import { recommendationForServiceArea } from './utils/recommendationLinks'
import AppHeader from './components/AppHeader.vue'
import AnalysisControls from './components/AnalysisControls.vue'
import MapStage from './components/MapStage.vue'
// 报告、图表、历史和导出只在工作台完成分析后使用，拆成异步块避免阻塞地图首屏。
const ReportPanel = defineAsyncComponent(() => import('./components/ReportPanel.vue'))
const ReportComparisonPanel = defineAsyncComponent(() => import('./components/ReportComparisonPanel.vue'))

const analysisStarted = ref(false)
const selectedRecommendationId = ref<string | null>(null)
const activeMobilePanel = ref<'controls' | 'report' | null>(null)
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
  error: historyError,
  openingReportId,
  rerunningReportId,
  loadHistory,
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

// 地图组件先确定真实底图是否可用，再启动首次分析，避免真实地图初始化与任务请求竞态。
function handleMapReady(_value: boolean) {
  if (!analysisStarted.value) {
    analysisStarted.value = true
    startAnalysis()
  }
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
  window.addEventListener('keydown', handleWorkspaceKeydown)
})
onBeforeUnmount(() => window.removeEventListener('keydown', handleWorkspaceKeydown))
</script>
