<template>
  <section class="map-stage" aria-label="生活圈分析地图">
    <p class="sr-only">地图是主要工作区域。键盘用户可在分析参数面板中通过地址候选或经纬度完成选点。</p>
    <div class="map-toolbar">
      <div class="layer-status" aria-label="地图核心图例">
        <span class="legend-item"><span class="legend-origin" aria-hidden="true"></span>起点</span>
        <span class="legend-item"><span class="legend-isochrone" aria-hidden="true"></span>{{ minutes }}分钟等时圈</span>
        <span class="legend-item risk-legend"><span class="status-symbol critical" aria-hidden="true">!</span>重点盲区</span>
        <span class="legend-item risk-legend"><span class="status-symbol sparse" aria-hidden="true">△</span>设施稀疏区</span>
      </div>
      <div class="map-toolbar-actions">
        <button class="mobile-legend-toggle" type="button" aria-controls="mobile-map-legend" :aria-expanded="showMobileLegend" @click="showMobileLegend = !showMobileLegend">图例</button>
        <button class="icon-btn" type="button" aria-label="重新运行当前分析" :disabled="loading" @click="emit('refresh')"><Refresh /></button>
      </div>
    </div>
    <div class="facility-legend" aria-label="设施类别图例"><span v-for="category in Object.keys(FACILITY_LABELS)" :key="category" class="facility-legend-item"><b :style="{ background: categoryColor(category) }" aria-hidden="true">{{ categoryShort(category) }}</b>{{ FACILITY_LABELS[category] }}</span><span v-if="report?.recommendations.length" class="facility-legend-item candidate-legend"><b aria-hidden="true">候</b>规划候选点</span><span v-if="simulation" class="facility-legend-item simulation-legend"><b aria-hidden="true">拟</b>假设设施/模拟区域</span></div>
    <div v-if="showMobileLegend" id="mobile-map-legend" class="mobile-map-legend" role="region" aria-label="地图完整图例">
      <button type="button" aria-label="关闭地图图例" @click="showMobileLegend = false">×</button>
      <strong>地图图例</strong>
      <span><b class="status-symbol critical" aria-hidden="true">!</b>重点服务盲区：红色网纹与感叹号</span>
      <span><b class="status-symbol sparse" aria-hidden="true">△</b>设施稀疏区：黄色斜纹与三角形</span>
      <span v-for="category in Object.keys(FACILITY_LABELS)" :key="`mobile-${category}`"><b class="category-symbol" :style="{ background: categoryColor(category) }" aria-hidden="true">{{ categoryShort(category) }}</b>{{ FACILITY_LABELS[category] }}</span>
      <span v-if="report?.recommendations.length"><b class="category-symbol candidate-legend" aria-hidden="true">候</b>规划候选点</span>
      <span v-if="simulation"><b class="category-symbol simulation-legend" aria-hidden="true">拟</b>假设设施和模拟区域</span>
    </div>
    <div ref="mapContainer" class="map-container" :class="{ hidden: !realMapReady, picking: simulationPicking }" role="region" aria-label="百度地图生活圈分析区域"></div><canvas ref="mapCanvas" class="map-canvas" :class="{ hidden: realMapReady, picking: simulationPicking }" role="img" aria-label="生活圈分析地图画布" @click="handleCanvasClick"></canvas>
    <div class="map-scale"><span>0</span><span class="scale-line"></span><span>500m</span></div>
    <div v-if="loading" class="map-loading" role="status" aria-live="polite" aria-atomic="true"><div class="loader-ring" aria-hidden="true"></div><strong>正在生成生活圈体检</strong><span>正在计算真实步行可达性… {{ progress }}%</span></div>
    <div class="map-caption"><span class="caption-kicker">分析中心</span><strong>{{ analysisCenter.address }}</strong><span>{{ analysisCenter.lng.toFixed(6) }}, {{ analysisCenter.lat.toFixed(6) }}</span></div>
    <div v-if="keyboardServiceAreas.length" class="service-area-keyboard-list" role="group" aria-label="可查看判定证据的服务区域">
      <span class="sr-only">使用 Tab 移动到区域按钮，按回车或空格定位并放大对应网格，同时查看判定依据。</span>
      <button
        v-for="area in keyboardServiceAreas"
        :key="area.properties.grid_id"
        type="button"
        :aria-pressed="selectedServiceArea?.properties.grid_id === area.properties.grid_id"
        :aria-label="`${area.properties.category_label}${area.properties.label} ${area.properties.grid_id}，定位并放大网格，查看判定依据`"
        @click="selectServiceArea(area)"
      >{{ area.properties.category_label }} · {{ area.properties.grid_id }} · {{ area.properties.label }}</button>
    </div>
    <article v-if="selectedServiceArea" ref="evidenceRef" class="service-area-evidence" tabindex="-1" aria-label="区域判定依据" aria-live="polite">
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
import { computed, nextTick, ref, toRef, watch } from 'vue'
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
const showMobileLegend = ref(false)
const evidenceRef = ref<HTMLElement | null>(null)
const { mapCanvas, mapContainer, realMapReady, mapLoadComplete, selectedServiceArea, visibleServiceAreas, selectServiceArea, handleCanvasClick, closeServiceAreaEvidence } = useMapRenderer({
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
const keyboardServiceAreas = computed(() => visibleServiceAreas())

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
watch(selectedServiceArea, async (value) => {
  emit('service-area-select', value?.properties.grid_id || null)
  if (value) {
    await nextTick()
    evidenceRef.value?.focus({ preventScroll: true })
  }
})
</script>
