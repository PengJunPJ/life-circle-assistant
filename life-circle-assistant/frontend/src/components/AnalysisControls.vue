<template>
  <aside class="control-panel" aria-label="智能体检工作台">
    <header class="controls-heading">
      <h1>智能体检工作台</h1>
      <button class="mobile-panel-close" type="button" aria-label="关闭分析参数面板并返回地图" @click="emit('close-mobile')">×</button>
    </header>
    <div class="controls-scroll">
      <details class="compact-data-status" data-guide="source-status">
        <summary><span class="api-indicator" :class="{ real: mapStatus?.real_api_configured && mapProbeResult?.verified }" aria-hidden="true"></span><span>{{ readinessSummary }}</span><small>详情</small></summary>
        <div class="data-status-details">
          <strong>{{ readinessTitle }}</strong><p>{{ readinessMessage }}</p>
          <div class="readiness-checks"><span :class="{ ok: mapProbeResult?.verified }">Web API · {{ webServiceLabel }}</span><span :class="{ ok: realMapReady }">底图 · {{ realMapReady ? '已加载' : '未加载' }}</span></div>
          <button type="button" :disabled="mapStatusLoading || mapProbeLoading" @click="mapStatus?.real_api_configured ? emit('probe-map-api') : emit('refresh-map-status')">{{ mapProbeLoading ? '探测中…' : mapStatus?.real_api_configured ? '验证 Web API' : '刷新状态' }}</button>
        </div>
      </details>
      <p v-if="!mapStatusLoading && !mapStatus" class="control-warning" role="alert">无法读取数据状态，请检查后端服务。</p>
      <p v-else-if="mapStatus && !mapStatus.real_api_configured" class="control-warning">本地快照仅支持沙涌长盛花园样例周边，数据非实时。</p>
      <p v-else-if="mapProbeResult && !mapProbeResult.verified" class="control-warning" role="alert">地图接口探测失败，请展开详情检查。</p>
      <div class="entry-tabs" role="tablist" aria-label="体检参数填写方式" @keydown="handleTabKeydown">
        <button id="manual-entry-tab" type="button" role="tab" :aria-selected="entry === 'manual'" :tabindex="entry === 'manual' ? 0 : -1" aria-controls="manual-entry-panel" :disabled="busy" @click="entry = 'manual'">自主设置</button>
        <button id="natural-entry-tab" type="button" role="tab" :aria-selected="entry === 'natural'" :tabindex="entry === 'natural' ? 0 : -1" aria-controls="natural-entry-panel" :disabled="busy" @click="entry = 'natural'">一句话填写</button>
      </div>
      <div v-show="entry === 'manual'" id="manual-entry-panel" class="entry-panel" role="tabpanel" aria-labelledby="manual-entry-tab" data-guide="analysis-center">
        <label for="shared-address">搜索地址</label>
        <div class="address-entry-row">
          <div class="search-box"><Search /><input id="shared-address" :value="addressQuery" :disabled="busy" placeholder="输入社区或地址" @input="emit('update:addressQuery', ($event.target as HTMLInputElement).value)" @keydown.enter.prevent="!busy && emit('search-address')" /><button class="search-submit" type="button" :disabled="busy" aria-label="搜索地址候选" @click="emit('search-address')">{{ searching ? '…' : '搜索' }}</button></div>
          <button class="map-pick-action" type="button" :disabled="busy" @click="emit('pick-center')"><Location />地图选点</button>
        </div>
      </div>
      <div v-show="entry === 'natural'" id="natural-entry-panel" class="entry-panel" role="tabpanel" aria-labelledby="natural-entry-tab">
        <NaturalLanguageAnalysis :previous="intentPrevious" :disabled="loading || resolving || searching" @fill="emit('fill-intent', $event)" @update:blocked="intentBlocked = $event" @update:busy="intentBusy = $event" />
      </div>
      <section class="shared-location" aria-label="公共位置确认">
        <div v-if="candidates.length" class="candidate-list" aria-label="地址候选列表" aria-live="polite"><p>请选择体检位置</p><button v-for="candidate in candidates" :key="`${candidate.lng}-${candidate.lat}-${candidate.address}`" type="button" :disabled="busy" @click="emit('select-candidate', candidate)"><Location /><span><strong>{{ candidate.address }}</strong><small>{{ candidate.lng.toFixed(6) }}, {{ candidate.lat.toFixed(6) }}</small></span></button></div>
        <p v-if="locationError" class="location-error" role="alert">{{ locationError }}</p>
        <div class="selected-center" :class="{ unsupported: locationPending || center.supportStatus !== 'supported' }" role="status"><span class="pin-small" aria-hidden="true">●</span><span><small>{{ locationPending ? '位置待确认' : '已选位置' }}</small><strong :title="center.address">{{ center.address }}</strong></span><span class="selected">{{ searching || resolving ? '确认中' : locationPending ? '待确认' : '已确认' }}</span></div>
        <p v-if="locationPending && !locationError && !candidates.length" class="form-help">{{ entry === 'manual' ? '请搜索并确认地址，或确认高级设置中的坐标。' : '请在下方选择候选，或切换自主设置确认位置。' }}</p>
      </section>
      <section class="panel-section common-parameters" data-guide="analysis-parameters">
        <div class="range-row"><span id="walking-time-label">步行时间</span><strong>{{ minutesValid ? `${minutes} 分钟` : '请选择' }}</strong></div>
        <div class="walking-time-switch" role="radiogroup" aria-labelledby="walking-time-label"><label v-for="option in walkingTimeOptions" :key="option" class="walking-time-option"><input type="radio" name="walking-time" :value="option" :disabled="busy" :checked="minutesValid && minutes === option" @change="emit('update:minutes', option)" /><span class="walking-time-face"><strong>{{ option }}</strong><small>分钟</small></span></label></div>
        <p v-if="!minutesValid" class="location-error" role="alert">支持 10、15、20 分钟，请选择步行时间。</p>
      </section>
      <section class="panel-section layer-panel analysis-facilities">
        <div class="layer-section-title"><div><label>体检设施</label><small>决定下一次体检范围</small></div><span class="layer-count" role="status">{{ analysisCategories.length }}/7 类</span></div>
        <div class="facility-selection-actions" role="group" aria-label="体检设施快捷选择"><button type="button" :disabled="busy || analysisCategories.length === ALL_CATEGORIES.length" @click="emit('update:analysisCategories', [...ALL_CATEGORIES])">全选</button><button type="button" :disabled="busy || !analysisCategories.length" @click="emit('update:analysisCategories', [])">全部取消</button></div>
        <div class="facility-list layer-facility-list"><button v-for="category in ALL_CATEGORIES" :key="category" type="button" :style="{ '--facility-color': categoryColor(category) }" :class="['facility-toggle', { selected: analysisCategories.includes(category) }]" :disabled="busy" :aria-pressed="analysisCategories.includes(category)" :aria-label="`${FACILITY_LABELS[category]}${report && !report.parameters.categories.includes(category) ? '，当前报告未体检' : ''}`" @click="toggleAnalysisCategory(category)"><span class="facility-icon" :style="{ background: categoryColor(category) }" aria-hidden="true">{{ FACILITY_ICONS[category] }}</span><span class="facility-copy"><span class="facility-name">{{ FACILITY_LABELS[category] }}</span><small v-if="report && !report.parameters.categories.includes(category)" class="facility-unavailable">未体检</small></span><span class="check" aria-hidden="true">{{ analysisCategories.includes(category) ? '✓' : '' }}</span></button></div>
        <p v-if="!analysisCategories.length" class="location-error" role="alert">请至少选择一类设施。</p><p v-else-if="supplementCount" class="form-help">沿用本报告的地点、时间和精度，补充 {{ supplementCount }} 类设施。</p><p v-else-if="report" class="form-help">当前报告保持原有范围；新设置在开始体检后生效。</p>
      </section>
      <details class="advanced-settings">
        <summary>高级设置<span>{{ mode === 'analysis' ? '正式分析' : '快速分析' }}</span></summary>
        <fieldset :disabled="busy"><legend class="sr-only">分析精度和坐标</legend>
          <label>分析精度</label><div class="mode-switch" aria-label="分析精度模式"><button type="button" :class="{ active: mode === 'demo' }" :aria-pressed="mode === 'demo'" @click="emit('update:mode', 'demo')">快速分析</button><button type="button" :class="{ active: mode === 'analysis' }" :aria-pressed="mode === 'analysis'" @click="emit('update:mode', 'analysis')">正式分析</button></div><p class="mode-note">正式分析使用更多步行采样，耗时较长。</p>
          <div class="coordinate-system-row"><span>输入坐标系</span><select :value="coordinateSystem" aria-label="输入坐标系" @change="emit('update:coordinateSystem', ($event.target as HTMLSelectElement).value as CoordinateSystem)"><option value="bd09">BD-09（百度）</option><option value="gcj02">GCJ-02（高德/腾讯）</option><option value="wgs84">WGS84（GPS）</option></select></div>
          <div class="coordinate-entry"><input :value="coordinateLng" inputmode="decimal" :aria-label="`${coordinateSystemLabel} 经度`" placeholder="经度" @input="emit('update:coordinateLng', ($event.target as HTMLInputElement).value)" /><input :value="coordinateLat" inputmode="decimal" :aria-label="`${coordinateSystemLabel} 纬度`" placeholder="纬度" @input="emit('update:coordinateLat', ($event.target as HTMLInputElement).value)" /><button type="button" :aria-label="`使用输入的 ${coordinateSystemLabel} 坐标`" @click="emit('apply-coordinates')">确认</button></div>
          <p v-if="coordinateConversionNote" class="coordinate-conversion-note" role="status">{{ coordinateConversionNote }}</p><p class="form-help">当前 BD-09：{{ center.lng.toFixed(6) }}, {{ center.lat.toFixed(6) }}</p>
        </fieldset>
      </details>
    </div>
    <footer class="analysis-footer">
      <p v-if="analysisError" class="location-error" role="alert">{{ analysisError }}{{ report ? '；原报告已保留，可重试。' : '' }}</p>
      <strong class="footer-location" :title="center.address">{{ center.address }}</strong><p class="footer-summary" role="status">{{ centerPicking ? '地图选点中' : locationPending || center.supportStatus !== 'supported' ? '位置待确认' : '位置已确认' }} · {{ minutesValid ? `${minutes}分钟` : '时间待确认' }} · {{ analysisCategories.length }}类设施</p>
      <button class="primary-action" data-guide="run-analysis" type="button" :disabled="!canRun" @click="emit('run')"><Refresh :class="{ spin: loading }" />{{ loading ? '正在体检…' : supplementCount ? `补充体检（${supplementCount}类）` : '开始体检' }}</button>
    </footer>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Location, Refresh, Search } from '@element-plus/icons-vue'
import NaturalLanguageAnalysis from './NaturalLanguageAnalysis.vue'
import { ALL_CATEGORIES, FACILITY_ICONS, FACILITY_LABELS, categoryColor } from '../constants/facilities'
import type { AnalysisIntent, IntentDraft } from '../types/analysisIntent'
import type { AnalysisCenter, CoordinateSystem, LocationCandidate } from '../types/location'
import type { AnalysisMode, AnalysisMinutes, MapProbeResult, MapStatus, Report } from '../types/report'
const props = defineProps<{
  center: AnalysisCenter; addressQuery: string; candidates: LocationCandidate[]
  coordinateLng: string; coordinateLat: string; coordinateSystem: CoordinateSystem; coordinateConversionNote: string
  locationError: string; locationPending: boolean; centerPicking?: boolean; searching: boolean; resolving: boolean
  mode: AnalysisMode; minutes: AnalysisMinutes; minutesValid: boolean; report: Report | null; analysisError: string
  analysisCategories: string[]; supplementCount: number; loading: boolean
  assistantBusy?: boolean
  mapStatus: MapStatus | null; mapStatusLoading: boolean; mapProbeResult: MapProbeResult | null; mapProbeLoading: boolean; realMapReady: boolean; mobileOpen: boolean
}>()
const emit = defineEmits<{
  'update:addressQuery': [value: string]; 'update:coordinateLng': [value: string]; 'update:coordinateLat': [value: string]; 'update:coordinateSystem': [value: CoordinateSystem]
  'update:mode': [value: AnalysisMode]; 'update:minutes': [value: AnalysisMinutes]; 'update:analysisCategories': [value: string[]]
  'update:inputBlocked': [value: boolean]; 'update:intentBusy': [value: boolean]
  'search-address': []; 'select-candidate': [value: LocationCandidate]; 'apply-coordinates': []; 'pick-center': []
  run: []; 'fill-intent': [intent: AnalysisIntent]; 'refresh-map-status': []; 'probe-map-api': []; 'close-mobile': []
}>()
const entry = ref<'manual' | 'natural'>('manual')
const intentBlocked = ref(false)
const intentBusy = ref(false)
const busy = computed(() => props.loading || props.resolving || props.searching || intentBusy.value || props.assistantBusy)
const inputBlocked = computed(() => intentBusy.value || (entry.value === 'natural' && intentBlocked.value))
watch(inputBlocked, value => emit('update:inputBlocked', value), { immediate: true })
watch(intentBusy, value => emit('update:intentBusy', value))
const canRun = computed(() => !busy.value && !inputBlocked.value && !props.centerPicking && !props.locationPending && !props.locationError && props.center.supportStatus === 'supported' && props.minutesValid && props.analysisCategories.length > 0)
const intentPrevious = computed<IntentDraft>(() => ({ address: props.locationPending ? props.addressQuery : props.center.address, use_current_center: !props.locationPending && props.center.supportStatus === 'supported', minutes: props.minutesValid ? props.minutes : null, mode: props.mode, categories: [...props.analysisCategories], defaulted_fields: [] }))
const walkingTimeOptions: AnalysisMinutes[] = [10, 15, 20]
const coordinateSystemLabel = computed(() => props.coordinateSystem === 'wgs84' ? 'WGS84' : props.coordinateSystem === 'gcj02' ? 'GCJ-02' : 'BD-09')
const readinessSummary = computed(() => props.mapStatusLoading ? '数据状态 · 检测中' : !props.mapStatus ? '数据状态 · 异常' : !props.mapStatus.real_api_configured ? '数据状态 · 本地快照' : props.mapProbeResult?.verified ? '数据状态 · 接口已验证' : props.mapProbeResult ? '数据状态 · 探测失败' : '数据状态 · 真实服务已配置')
const readinessTitle = computed(() => {
  if (props.mapStatusLoading) return '正在检测地图服务'
  if (!props.mapStatus) return '无法读取地图服务状态'
  if (!props.mapStatus.real_api_configured) return '当前为本地快照模式'
  if (props.mapProbeLoading) return '正在探测百度地理编码接口'
  if (props.mapProbeResult?.verified && props.realMapReady) return 'Web API 探测成功，浏览器底图已加载'
  if (props.mapProbeResult?.verified) return '百度 Web API 地理编码探测成功'
  if (props.mapProbeResult) return '百度 Web API 探测失败'
  return props.realMapReady ? '浏览器底图已加载，Web API 尚未探测' : '真实百度 Web 服务已配置，尚未探测'
})
const readinessMessage = computed(() => {
  if (props.mapStatusLoading) return '正在读取后端配置和浏览器底图状态。'
  if (!props.mapStatus) return '请确认后端已启动，然后重新检测。'
  if (!props.mapStatus.real_api_configured) return props.mapStatus.message || '快照数据仅适合演示，不代表最新地图。'
  if (props.mapProbeLoading) return '正在调用百度地理编码接口；超时或限流时可能重试并额外消耗配额。'
  if (props.mapProbeResult) return props.mapProbeResult.message
  return `${props.realMapReady ? '底图已加载，但 Web 接口尚未验证。' : '底图尚未加载，请检查浏览器 AK 域名白名单。'}点击“验证 Web API”会消耗地理编码调用配额。`
})
const webServiceLabel = computed(() => props.mapStatusLoading ? '检测中' : !props.mapStatus ? '未知' : !props.mapStatus.real_api_configured ? '未启用' : props.mapProbeLoading ? '探测中' : props.mapProbeResult?.verified ? '探测成功' : props.mapProbeResult ? '探测失败' : '已配置，未探测')
function toggleAnalysisCategory(category: string) { emit('update:analysisCategories', props.analysisCategories.includes(category) ? props.analysisCategories.filter(item => item !== category) : [...props.analysisCategories, category]) }
function handleTabKeydown(event: KeyboardEvent) {
  if (busy.value || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  entry.value = event.key === 'Home' ? 'manual' : event.key === 'End' ? 'natural' : entry.value === 'manual' ? 'natural' : 'manual'
  document.getElementById(`${entry.value}-entry-tab`)?.focus()
}
</script>
