<template>
  <section class="map-stage" aria-label="生活圈分析地图">
    <p class="sr-only">地图是主要工作区域。键盘用户可在分析参数面板中通过地址候选或经纬度完成选点。</p>
    <div class="map-toolbar">
      <div class="layer-status" aria-label="地图核心图例">
        <span class="legend-item"><span class="legend-origin" aria-hidden="true"></span>起点</span>
        <span class="legend-item"><span class="legend-isochrone" aria-hidden="true"></span>{{ minutes }}分钟等时圈</span>
        <span v-if="showCritical" class="legend-item risk-legend"><span class="status-symbol critical" aria-hidden="true">!</span>重点盲区</span>
        <span v-if="showSparse" class="legend-item risk-legend"><span class="status-symbol sparse" aria-hidden="true">△</span>设施稀疏区</span>
      </div>
      <div class="map-toolbar-actions">
        <span v-if="routePreview" class="route-chip" role="status">步行路线 · {{ routePreview.poi.name }} · {{ Math.round(routePreview.route.duration_s / 60) }} 分钟</span>
        <button v-if="routePreview" class="icon-btn" type="button" title="清除步行路线" aria-label="清除步行路线" @click="setRoutePreview(null)"><Close /></button>
        <button class="mobile-legend-toggle" type="button" aria-controls="mobile-map-legend" :aria-expanded="showMobileLegend" @click="showMobileLegend = !showMobileLegend">图例</button>
        <MapLayerControls :report="report" :visible-categories="visibleCategories" :loading="loading || interactionBlocked" :show-normal="showNormal" :show-sparse="showSparse" :show-critical="showCritical" :status-layers="statusLayers" @update:status-layers="emit('update:statusLayers', $event)" @update:visible-categories="emit('update:visibleCategories', $event)" @update:show-normal="emit('update:showNormal', $event)" @update:show-sparse="emit('update:showSparse', $event)" @update:show-critical="emit('update:showCritical', $event)" @prepare-supplement="emit('prepare-supplement')" />
      </div>
    </div>
    <p v-if="statusLayers?.sampling && samplingLayers" class="map-evidence-legend" role="status">青绿点：真实观测 · 青绿外沿：仅中心可达 · 蓝色：估计 · 灰色：未决 · 未进入正式评分</p>
    <p v-if="combination" class="map-evidence-legend combination-legend" role="status">组合假设情景 · {{ combination.hypothetical_facilities.length }}处新增设施</p>
    <div v-if="legendCategories.length || hasVisibleCandidates || simulation" class="facility-legend" aria-label="设施类别图例">
      <span v-for="category in legendCategories" :key="category" class="facility-legend-item"><b :style="{ background: categoryColor(category) }" aria-hidden="true">{{ categoryShort(category) }}</b>{{ FACILITY_LABELS[category] }}</span>
      <span v-if="hasVisibleCandidates" class="facility-legend-item candidate-legend"><b aria-hidden="true">候</b>规划候选点</span>
      <span v-if="simulation" class="facility-legend-item simulation-legend"><b aria-hidden="true">拟</b>假设设施/模拟区域</span>
    </div>
    <div v-if="showMobileLegend" id="mobile-map-legend" class="mobile-map-legend" role="region" aria-label="地图完整图例">
      <button type="button" aria-label="关闭地图图例" @click="showMobileLegend = false">×</button>
      <strong>地图图例</strong>
      <span><b class="status-symbol critical" aria-hidden="true">!</b>重点服务盲区：红色网纹与感叹号</span>
      <span><b class="status-symbol sparse" aria-hidden="true">△</b>设施稀疏区：黄色斜纹与三角形</span>
      <span v-for="category in legendCategories" :key="`mobile-${category}`"><b class="category-symbol" :style="{ background: categoryColor(category) }" aria-hidden="true">{{ categoryShort(category) }}</b>{{ FACILITY_LABELS[category] }}</span>
      <span v-if="!legendCategories.length">未选择设施类别</span>
      <span v-if="hasVisibleCandidates"><b class="category-symbol candidate-legend" aria-hidden="true">候</b>规划候选点</span>
      <span v-if="simulation"><b class="category-symbol simulation-legend" aria-hidden="true">拟</b>假设设施和模拟区域</span>
    </div>
    <div v-if="centerPicking" class="center-pick-banner" role="status"><Location /><span>点击地图确认体检位置</span><button type="button" @click="emit('cancel-center-pick')">取消</button></div>
    <div ref="mapContainer" class="map-container" :class="{ hidden: !realMapReady, picking: simulationPicking || centerPicking }" role="region" aria-label="百度地图生活圈分析区域"></div><canvas ref="mapCanvas" class="map-canvas" :class="{ hidden: realMapReady, picking: simulationPicking || centerPicking }" role="img" aria-label="生活圈分析地图画布" @click="handleCanvasClick" @mousemove="handleCanvasMouseMove" @mouseleave="handleCanvasMouseLeave"></canvas>
    <MapHoverCard
      :target="hoverTarget"
      :minutes="minutes"
      :route-available="routeAvailable"
      :route-loading="routeLoading"
      :route-active="routePreview?.poi.id === hoverTarget?.poi.id"
      @show-route="handleShowRoute"
      @hide-route="setRoutePreview(null)"
      @retain="retainHover"
      @release="clearHover"
    />
    <div class="map-scale"><span>0</span><span class="scale-line"></span><span>500m</span></div>
    <div v-if="loading" class="map-loading" role="status" aria-live="polite" aria-atomic="true"><div class="loader-ring" aria-hidden="true"></div><strong>正在生成生活圈体检</strong><span>{{ progressLabel || '正在计算真实步行可达性' }}… {{ progress }}% · 已耗时 {{ elapsedLabel }}</span></div>
    <div class="map-caption"><span class="caption-kicker">分析中心</span><strong>{{ analysisCenter.address }}</strong><span>{{ analysisCenter.lng.toFixed(6) }}, {{ analysisCenter.lat.toFixed(6) }}</span></div>
    <div class="service-area-dock">
      <MapServiceAreaBrowser ref="areaBrowserRef" :areas="keyboardServiceAreas" :names="serviceAreaNames" :selected-id="selectedServiceArea?.properties.grid_id || null" @select="selectServiceArea" @update:open="areaBrowserOpen = $event" />
      <article v-if="selectedServiceArea" v-show="!areaBrowserOpen" ref="evidenceRef" class="service-area-evidence" tabindex="-1" aria-label="区域判定依据" aria-live="polite" @keydown.esc.stop.prevent="dismissServiceArea">
        <button class="evidence-close" aria-label="关闭区域判定依据" @click="dismissServiceArea">×</button>
        <div class="evidence-kicker">{{ serviceAreaNames.get(selectedServiceArea.properties.grid_id) || selectedServiceArea.properties.category_label }} · {{ selectedServiceArea.properties.label }}</div>
        <strong>{{ selectedServiceArea.properties.nearest_facility_name || '候选范围内无同类设施' }}</strong>
        <div class="evidence-metrics">
          <span>步行时间 <b>{{ formatMetric(selectedServiceArea.properties.nearest_walk_minutes, '分钟') }}</b></span>
          <span>步行距离 <b>{{ formatMetric(selectedServiceArea.properties.nearest_walk_distance_m, '米') }}</b></span>
        </div>
        <p>{{ selectedServiceArea.properties.basis }}</p>
        <small>数据来源：{{ sourceLabel(selectedServiceArea.properties.source) }} · 置信度：{{ confidenceLabel(selectedServiceArea.properties.confidence) }}</small>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, toRef, watch } from 'vue'
import { Close, Location } from '@element-plus/icons-vue'
import ElMessage from 'element-plus/es/components/message/index'
import { ALL_CATEGORIES, FACILITY_LABELS, categoryColor, categoryShort } from '../constants/facilities'
import { useMapRenderer } from '../composables/useMapRenderer'
import { fetchWalkingRoute } from '../services/analysisApi'
import MapHoverCard from './MapHoverCard.vue'
import MapLayerControls from './MapLayerControls.vue'
import MapServiceAreaBrowser from './MapServiceAreaBrowser.vue'
import type { Poi } from '../types/report'
import type { AnalysisCenter } from '../types/location'
import type { Report } from '../types/report'
import type { SimulationResult } from '../types/simulation'
import type { Combination, SamplingLayers, StatusLayers } from '../types/completion'

const props = defineProps<{ report: Report | null; analysisCenter: AnalysisCenter; minutes: 10 | 15 | 20; visibleCategories: string[]; showNormal: boolean; showSparse: boolean; showCritical: boolean; statusLayers?: StatusLayers; samplingLayers?: SamplingLayers | null; combination?: Combination | null; loading: boolean; interactionBlocked?: boolean; progress: number; progressLabel?: string; focusRecommendationId: string | null; focusGridId?: string | null; simulation: SimulationResult | null; simulationPicking: boolean; centerPicking?: boolean }>()
const emit = defineEmits<{ 'map-ready': [value: boolean]; 'select-center': [lng: number, lat: number]; 'select-simulation-location': [lng: number, lat: number]; 'service-area-select': [serviceAreaId: string | null]; 'update:visibleCategories': [categories: string[]]; 'update:showNormal': [value: boolean]; 'update:showSparse': [value: boolean]; 'update:showCritical': [value: boolean]; 'update:statusLayers': [layers: Partial<StatusLayers>]; 'prepare-supplement': []; 'cancel-center-pick': [] }>()
const report = toRef(props, 'report')
const analysisCenter = toRef(props, 'analysisCenter')
const minutes = toRef(props, 'minutes')
const visibleCategories = computed(() => props.report
  ? props.visibleCategories.filter(category => props.report?.parameters?.categories.includes(category))
  : props.visibleCategories)
const legendCategories = computed(() => ALL_CATEGORIES.filter(category => visibleCategories.value.includes(category)))
const hasVisibleCandidates = computed(() => props.report?.recommendations.some(recommendation =>
  visibleCategories.value.includes(recommendation.category) && recommendation.candidate_locations.length > 0,
))
const showNormal = toRef(props, 'showNormal')
const showSparse = toRef(props, 'showSparse')
const showCritical = toRef(props, 'showCritical')
const focusRecommendationId = toRef(props, 'focusRecommendationId')
const simulation = toRef(props, 'simulation')
const simulationPicking = toRef(props, 'simulationPicking')
const centerPicking = computed(() => Boolean(props.centerPicking))
const showMobileLegend = ref(false)
const elapsedSeconds = ref(0)
let elapsedTimer: number | undefined
const elapsedLabel = computed(() => `${Math.floor(elapsedSeconds.value / 60)}:${String(elapsedSeconds.value % 60).padStart(2, '0')}`)
watch(() => props.loading, (value) => {
  if (value) {
    elapsedSeconds.value = 0
    elapsedTimer = window.setInterval(() => { elapsedSeconds.value += 1 }, 1000)
  } else if (elapsedTimer !== undefined) {
    window.clearInterval(elapsedTimer)
    elapsedTimer = undefined
  }
}, { immediate: true })
onBeforeUnmount(() => { if (elapsedTimer !== undefined) window.clearInterval(elapsedTimer) })
const evidenceRef = ref<HTMLElement | null>(null)
const areaBrowserRef = ref<InstanceType<typeof MapServiceAreaBrowser> | null>(null)
const areaBrowserOpen = ref(false)
const serviceAreaNames = computed(() => {
  const counts = new Map<string, number>()
  return new Map((props.report?.service_areas?.features || props.report?.zones?.features || []).map(area => {
    const number = (counts.get(area.properties.category) || 0) + 1
    counts.set(area.properties.category, number)
    return [area.properties.grid_id, `${area.properties.category_label} · 区域 ${number}`]
  }))
})
const { mapCanvas, mapContainer, realMapReady, mapLoadComplete, selectedServiceArea, hoverTarget, routePreview, setRoutePreview, retainHover, clearHover, visibleServiceAreas, selectServiceArea, handleCanvasClick, handleCanvasMouseMove, handleCanvasMouseLeave, closeServiceAreaEvidence } = useMapRenderer({
  report,
  analysisCenter,
  minutes,
  visibleCategories,
  showNormal,
  showSparse,
  showCritical,
  focusRecommendationId,
  focusGridId: computed(() => props.focusGridId || null),
  simulation,
  simulationPicking,
  centerPicking,
  statusLayers: computed(() => props.statusLayers || { normal: props.showNormal, sparse: props.showSparse, critical: props.showCritical, unknown: true, scarcity: false, walking_timeout: false, gap_groups: false, sampling: false }),
  samplingLayers: computed(() => props.samplingLayers || null),
  combination: computed(() => props.combination || null),
  onSelectCenter: (lng, lat) => emit('select-center', lng, lat),
  onSelectSimulationLocation: (lng, lat) => emit('select-simulation-location', lng, lat),
})
const keyboardServiceAreas = computed(() => visibleServiceAreas())

function dismissServiceArea() {
  closeServiceAreaEvidence()
  areaBrowserRef.value?.focusTrigger()
}

const routeLoading = ref(false)
const routeAvailable = computed(() => props.report?.calculation_mode?.provider_mode === 'real')

async function handleShowRoute(poi: Poi) {
  if (routeLoading.value) return
  routeLoading.value = true
  try {
    const route = await fetchWalkingRoute({ lng: props.analysisCenter.lng, lat: props.analysisCenter.lat }, { lng: poi.lng, lat: poi.lat })
    setRoutePreview({ poi, route })
  } catch (error) {
    ElMessage.warning(error instanceof Error ? error.message : '步行路线获取失败')
  } finally {
    routeLoading.value = false
  }
}

function handleEscape(event: KeyboardEvent) {
  if (event.key === 'Escape') setRoutePreview(null)
}
onMounted(() => window.addEventListener('keydown', handleEscape))
onBeforeUnmount(() => window.removeEventListener('keydown', handleEscape))

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
<style scoped>
.map-evidence-legend { position: absolute; z-index: 4; top: 98px; left: 14px; margin: 0; max-width: calc(100% - 28px); padding: 6px 9px; border-radius: 5px; color: #24483f; background: rgba(248,252,250,.94); font-size: 10px; }
.combination-legend { top: 128px; color: #286995; }
html[data-theme="dark"] .map-evidence-legend { color: #cfe7e1; background: rgba(24,40,56,.94); }
</style>
