<template>
  <section class="map-stage">
    <div class="map-toolbar"><div class="layer-status"><span class="legend-item"><span class="legend-origin"></span>起点</span><span class="legend-item"><span class="legend-isochrone"></span>{{ minutes }}分钟等时圈</span><span class="legend-item"><span class="status-dot red"></span>重点盲区</span><span class="legend-item"><span class="status-dot amber"></span>稀疏区</span></div><button class="icon-btn" title="刷新分析" @click="emit('refresh')"><Refresh /></button></div>
    <div class="facility-legend"><span v-for="category in Object.keys(FACILITY_LABELS)" :key="category" class="facility-legend-item"><b :style="{ background: categoryColor(category) }">{{ categoryShort(category) }}</b>{{ FACILITY_LABELS[category] }}</span><span v-if="report?.recommendations.length" class="facility-legend-item candidate-legend"><b>候</b>规划候选点</span><span v-if="simulation" class="facility-legend-item simulation-legend"><b>拟</b>假设设施/模拟区域</span></div>
    <div ref="mapContainer" class="map-container" :class="{ hidden: !realMapReady, picking: simulationPicking }"></div><canvas ref="mapCanvas" class="map-canvas" :class="{ hidden: realMapReady, picking: simulationPicking }" @click="handleCanvasClick"></canvas>
    <div class="map-scale"><span>0</span><span class="scale-line"></span><span>500m</span></div>
    <div v-if="loading" class="map-loading"><div class="loader-ring"></div><strong>正在生成生活圈体检</strong><span>正在计算真实步行可达性… {{ progress }}%</span></div>
    <div class="map-caption"><span class="caption-kicker">分析中心</span><strong>{{ analysisCenter.address }}</strong><span>{{ analysisCenter.lng.toFixed(6) }}, {{ analysisCenter.lat.toFixed(6) }}</span></div>
    <article v-if="selectedServiceArea" class="service-area-evidence" aria-live="polite">
      <button class="evidence-close" aria-label="关闭区域判定依据" @click="closeServiceAreaEvidence">×</button>
      <div class="evidence-kicker">{{ selectedServiceArea.properties.category_label }} · {{ selectedServiceArea.properties.label }}</div>
      <strong>{{ selectedServiceArea.properties.nearest_facility_name || '候选范围内无同类设施' }}</strong>
      <div class="evidence-metrics">
        <span>步行时间 <b>{{ formatMetric(selectedServiceArea.properties.nearest_walk_minutes, '分钟') }}</b></span>
        <span>步行距离 <b>{{ formatMetric(selectedServiceArea.properties.nearest_walk_distance_m, '米') }}</b></span>
      </div>
      <p>{{ selectedServiceArea.properties.basis }}</p>
      <small>数据来源：{{ sourceLabel(selectedServiceArea.properties.source) }} · 置信度：{{ confidenceLabel(selectedServiceArea.properties.confidence) }}</small>
    </article>
  </section>
</template>

<script setup lang="ts">
import { toRef, watch } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { FACILITY_LABELS, categoryColor, categoryShort } from '../constants/facilities'
import { useMapRenderer } from '../composables/useMapRenderer'
import type { AnalysisCenter } from '../types/location'
import type { Report } from '../types/report'
import type { SimulationResult } from '../types/simulation'

const props = defineProps<{ report: Report | null; analysisCenter: AnalysisCenter; minutes: 10 | 15 | 20; visibleCategories: string[]; showNormal: boolean; showSparse: boolean; showCritical: boolean; loading: boolean; progress: number; focusRecommendationId: string | null; simulation: SimulationResult | null; simulationPicking: boolean }>()
const emit = defineEmits<{ refresh: [] ; 'map-ready': [value: boolean]; 'select-center': [lng: number, lat: number]; 'select-simulation-location': [lng: number, lat: number]; 'service-area-select': [serviceAreaId: string | null] }>()
const report = toRef(props, 'report')
const analysisCenter = toRef(props, 'analysisCenter')
const visibleCategories = toRef(props, 'visibleCategories')
const showNormal = toRef(props, 'showNormal')
const showSparse = toRef(props, 'showSparse')
const showCritical = toRef(props, 'showCritical')
const focusRecommendationId = toRef(props, 'focusRecommendationId')
const simulation = toRef(props, 'simulation')
const simulationPicking = toRef(props, 'simulationPicking')
const { mapCanvas, mapContainer, realMapReady, mapLoadComplete, selectedServiceArea, handleCanvasClick, closeServiceAreaEvidence } = useMapRenderer({
  report,
  analysisCenter,
  visibleCategories,
  showNormal,
  showSparse,
  showCritical,
  focusRecommendationId,
  simulation,
  simulationPicking,
  onSelectCenter: (lng, lat) => emit('select-center', lng, lat),
  onSelectSimulationLocation: (lng, lat) => emit('select-simulation-location', lng, lat),
})

function formatMetric(value: number | null, unit: string) {
  return value === null ? '无有效结果' : `${value}${unit}`
}

function confidenceLabel(value: 'high' | 'medium' | 'low') {
  return { high: '高', medium: '中', low: '低' }[value]
}

function sourceLabel(value: string) {
  const labels: Record<string, string> = {
    real_api: '真实 API', cache: '有效缓存', local_snapshot: '本地快照',
    interpolation: '空间插值', degraded_estimate: '降级估算',
  }
  return labels[value] || value
}

watch(mapLoadComplete, (value) => { if (value) emit('map-ready', realMapReady.value) }, { immediate: true })
watch(selectedServiceArea, (value) => emit('service-area-select', value?.properties.grid_id || null))
</script>
