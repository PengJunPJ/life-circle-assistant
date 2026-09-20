<template>
  <main class="app-shell">
    <AppHeader :has-report="Boolean(report)" />
    <section class="workspace">
      <AnalysisControls
        :address="address"
        :mode="mode"
        :minutes="minutes"
        :visible-categories="visibleCategories"
        :show-sparse="showSparse"
        :loading="loading"
        :source="report?.source"
        @update:address="address = $event"
        @update:mode="mode = $event"
        @update:minutes="minutes = $event"
        @update:show-sparse="showSparse = $event"
        @toggle-category="toggleCategory"
        @run="runAnalysis"
      />
      <MapStage
        :report="report"
        :minutes="minutes"
        :visible-categories="visibleCategories"
        :show-sparse="showSparse"
        :loading="loading"
        :progress="progress"
        @map-ready="handleMapReady"
        @refresh="runAnalysis"
      />
      <ReportPanel :report="report" @export="exportReport(report)" />
    </section>
  </main>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useAnalysis } from './composables/useAnalysis'
import { exportReport } from './utils/report'
import AppHeader from './components/AppHeader.vue'
import AnalysisControls from './components/AnalysisControls.vue'
import MapStage from './components/MapStage.vue'
import ReportPanel from './components/ReportPanel.vue'

const mapReady = ref(false)
const analysisStarted = ref(false)
const { address, mode, minutes, visibleCategories, showSparse, loading, progress, report, runAnalysis, toggleCategory } = useAnalysis(mapReady)

// 地图组件先确定真实底图是否可用，再启动首次分析，避免真实地图初始化与任务请求竞态。
function handleMapReady(value: boolean) {
  mapReady.value = value
  if (!analysisStarted.value) {
    analysisStarted.value = true
    runAnalysis()
  }
}
</script>
