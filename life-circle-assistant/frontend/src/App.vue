<template>
  <main class="app-shell">
    <AppHeader :has-report="Boolean(report)" />
    <section class="workspace">
      <AnalysisControls
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
        @map-ready="handleMapReady"
        @select-center="selectMapPoint"
        @refresh="startAnalysis"
      />
      <ReportPanel
        :report="report"
        :history-items="historyItems"
        :history-total="historyTotal"
        :history-loading="historyLoading"
        :history-error="historyError"
        :opening-report-id="openingReportId"
        :rerunning-report-id="rerunningReportId"
        @export="exportReport(report)"
        @refresh-history="loadHistory"
        @open-history="handleOpenHistory"
        @rerun-history="handleRerunHistory"
      />
    </section>
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useAnalysis } from './composables/useAnalysis'
import { useReportHistory } from './composables/useReportHistory'
import { useAnalysisCenter } from './composables/useAnalysisCenter'
import { exportReport } from './utils/report'
import AppHeader from './components/AppHeader.vue'
import AnalysisControls from './components/AnalysisControls.vue'
import MapStage from './components/MapStage.vue'
import ReportPanel from './components/ReportPanel.vue'

const analysisStarted = ref(false)
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
  runAnalysis,
  toggleCategory,
  applyReport,
} = useAnalysis(center)
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

async function startAnalysis() {
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

// 地图组件先确定真实底图是否可用，再启动首次分析，避免真实地图初始化与任务请求竞态。
function handleMapReady(_value: boolean) {
  if (!analysisStarted.value) {
    analysisStarted.value = true
    startAnalysis()
  }
}

function applySelectedReport(selected: NonNullable<typeof report.value>) {
  restoreCenter({
    lng: selected.center.lng,
    lat: selected.center.lat,
    address: selected.center.address,
    source: selected.center.source || selected.source,
    selectionMethod: selected.center.selection_method || selected.parameters.center_selection_method || 'default',
  })
  applyReport(selected)
}

onMounted(loadHistory)
</script>
