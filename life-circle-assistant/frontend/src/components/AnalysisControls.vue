<template>
  <aside class="control-panel" aria-label="分析参数">
    <div class="mobile-panel-heading">
      <div><div class="eyebrow">空间分析工作台</div><strong>设置分析参数</strong></div>
      <button class="mobile-panel-close" type="button" aria-label="关闭分析参数面板并返回地图" @click="emit('close-mobile')">×</button>
    </div>
    <button class="desktop-panel-heading" type="button" aria-label="收起或展开分析参数面板" @click="toggleCollapseIfDesktop"><span class="eyebrow">空间分析工作台</span><ArrowLeft class="panel-collapse-icon" /></button>
    <h1>15分钟生活圈<br /><em>智能体检</em></h1>
    <p class="intro">用真实步行可达性，识别社区服务覆盖与规划机会。</p>
    <div class="map-readiness" :class="{ ready: mapStatus?.real_api_configured && realMapReady && mapProbeResult?.verified, snapshot: !mapStatusLoading && mapStatus && !mapStatus.real_api_configured }" data-guide="source-status" role="status" aria-live="polite">
      <div class="map-readiness-heading">
        <span class="readiness-mark" aria-hidden="true">{{ mapStatus?.real_api_configured && realMapReady && mapProbeResult?.verified ? '✓' : mapStatusLoading || mapProbeLoading ? '···' : '!' }}</span>
        <span><strong>{{ readinessTitle }}</strong><small>{{ readinessMessage }}</small></span>
        <button type="button" :disabled="mapStatusLoading || mapProbeLoading" @click="mapStatus?.real_api_configured ? emit('probe-map-api') : emit('refresh-map-status')">{{ mapProbeLoading ? '探测中…' : mapStatus?.real_api_configured ? '验证 Web API' : '刷新状态' }}</button>
      </div>
      <div class="readiness-checks">
        <span :class="{ ok: mapStatus?.real_api_configured && mapProbeResult?.verified }"><i aria-hidden="true"></i>Web API{{ webServiceLabel }}</span>
        <span :class="{ ok: realMapReady }"><i aria-hidden="true"></i>百度底图{{ realMapReady ? '已加载' : '未加载' }}</span>
      </div>
    </div>
    <NaturalLanguageAnalysis :center="center" :disabled="loading || resolving || searching" :real-api-configured="Boolean(mapStatus?.real_api_configured)" @confirm="emit('confirm-intent', $event)" @update:active="intentActive = $event" />
    <div class="panel-section" data-guide="analysis-center">
      <label>分析中心点</label>
      <div class="search-box">
        <Search />
        <input :value="addressQuery" aria-label="地址搜索" placeholder="输入地址后搜索候选" @input="emit('update:addressQuery', ($event.target as HTMLInputElement).value)" @keydown.enter="emit('search-address')" />
        <button class="search-submit" :disabled="searching" aria-label="搜索地址候选" @click="emit('search-address')">{{ searching ? '…' : '搜索' }}</button>
      </div>
      <div v-if="candidates.length" class="candidate-list" aria-label="地址候选列表" aria-live="polite">
        <button v-for="candidate in candidates" :key="`${candidate.lng}-${candidate.lat}-${candidate.address}`" type="button" @click="emit('select-candidate', candidate)">
          <Location /><span><strong>{{ candidate.address }}</strong><small>{{ candidate.lng.toFixed(6) }}, {{ candidate.lat.toFixed(6) }}</small></span>
        </button>
      </div>
      <div class="coordinate-system-row">
        <span>输入坐标系</span>
        <select :value="coordinateSystem" aria-label="输入坐标系" @change="emit('update:coordinateSystem', ($event.target as HTMLSelectElement).value as CoordinateSystem)">
          <option value="bd09">BD-09（百度）</option>
          <option value="gcj02">GCJ-02（高德/腾讯）</option>
          <option value="wgs84">WGS84（GPS）</option>
        </select>
      </div>
      <div class="coordinate-entry">
        <input :value="coordinateLng" inputmode="decimal" :aria-label="`${coordinateSystemLabel} 经度`" placeholder="经度" @input="emit('update:coordinateLng', ($event.target as HTMLInputElement).value)" />
        <input :value="coordinateLat" inputmode="decimal" :aria-label="`${coordinateSystemLabel} 纬度`" placeholder="纬度" @input="emit('update:coordinateLat', ($event.target as HTMLInputElement).value)" />
        <button type="button" :disabled="resolving" :aria-label="`使用输入的 ${coordinateSystemLabel} 坐标`" @click="emit('apply-coordinates')">{{ resolving ? '处理中…' : '确认' }}</button>
      </div>
      <p v-if="coordinateConversionNote" class="coordinate-conversion-note" role="status">{{ coordinateConversionNote }}</p>
      <p v-if="locationError" class="location-error" role="alert">{{ locationError }}</p>
      <div class="selected-center" :class="{ unsupported: center.supportStatus === 'unsupported' }" role="status" aria-live="polite">
        <span class="pin-small">●</span>
        <span><strong>{{ center.address }}</strong><small>BD-09 · {{ center.lng.toFixed(6) }}, {{ center.lat.toFixed(6) }}</small></span>
        <span class="selected">{{ resolving ? '确认中' : '已选' }}</span>
      </div>
      <p class="map-pick-hint">也可直接点击地图选点；离线快照仅支持红山街道海韵东路离线样例中心周边。</p>
    </div>
    <div class="panel-section" data-guide="analysis-parameters">
      <label>分析参数</label>
      <div class="mode-switch" aria-label="分析精度模式"><button type="button" :class="{ active: mode === 'demo' }" :aria-pressed="mode === 'demo'" @click="emit('update:mode', 'demo')">快速分析</button><button type="button" :class="{ active: mode === 'analysis' }" :aria-pressed="mode === 'analysis'" @click="emit('update:mode', 'analysis')">正式分析</button></div>
      <p class="mode-note">正式地图模式下两种精度都会请求百度；正式分析会增加等时圈采样次数。</p>
      <div class="range-row"><span id="walking-time-label">步行时间</span><strong>{{ minutes }} 分钟</strong></div>
      <div class="walking-time-switch" role="radiogroup" aria-labelledby="walking-time-label">
        <label v-for="option in walkingTimeOptions" :key="option" class="walking-time-option">
          <input type="radio" name="walking-time" :value="option" :checked="minutes === option" @change="emit('update:minutes', option)" />
          <span class="walking-time-face"><strong>{{ option }}</strong><small>分钟</small></span>
        </label>
      </div>
    </div>
    <div class="panel-section layer-panel">
      <div class="layer-section-title">
        <div><label>{{ report ? '地图设施展示' : '本次体检设施' }}</label><small>{{ report ? `本报告已体检 ${displayCategories.length} 类；勾选只改变地图显示` : '仅分析勾选的设施类别' }}</small></div>
        <span class="layer-count" role="status" aria-live="polite" aria-atomic="true">{{ displayedCount }}/{{ displayCategories.length }} 类</span>
      </div>
      <div class="facility-selection-actions" role="group" aria-label="设施类别快捷选择">
        <button type="button" :disabled="loading || displayCategories.every(category => visibleCategories.includes(category))" @click="emit('update:visibleCategories', [...displayCategories])">{{ report ? '全选展示' : '全选' }}</button>
        <button type="button" :disabled="loading || !displayedCount" @click="emit('update:visibleCategories', [])">{{ report ? '全部隐藏' : '全部取消' }}</button>
      </div>
      <div class="facility-list layer-facility-list">
        <button v-for="category in ALL_CATEGORIES" :key="category" type="button" :style="{ '--facility-color': categoryColor(category) }" :class="['facility-toggle', { selected: isDisplayed(category), unanalyzed: !displayCategories.includes(category) }]" :disabled="loading || !displayCategories.includes(category)" :aria-pressed="isDisplayed(category)" :aria-label="`${FACILITY_LABELS[category]}${displayCategories.includes(category) ? '' : '，未体检，补充体检后可展示'}`" @click="emit('toggle-category', category)">
          <span class="facility-icon" :style="{ background: categoryColor(category) }" aria-hidden="true">{{ FACILITY_ICONS[category] }}</span>
          <span class="facility-copy"><span class="facility-name">{{ FACILITY_LABELS[category] }}</span><small v-if="!displayCategories.includes(category)" class="facility-unavailable">未体检</small></span>
          <span class="check" aria-hidden="true">{{ isDisplayed(category) ? '✓' : '' }}</span>
        </button>
      </div>
      <div v-if="report && unanalyzedCategories.length" class="supplement-analysis">
        <fieldset :disabled="loading || resolving || searching">
          <legend>补充体检</legend>
          <p>选择未体检类别，生成包含原有类别的新报告。</p>
          <div class="supplement-category-list">
            <label v-for="category in unanalyzedCategories" :key="category">
              <input v-model="supplementCategories" type="checkbox" :value="category" />{{ FACILITY_LABELS[category] }}
            </label>
          </div>
        </fieldset>
        <p class="supplement-note">沿用本报告的地点、{{ report.parameters.minutes }} 分钟及分析精度，合并类别重新测算。</p>
        <button class="supplement-submit" type="button" :disabled="loading || resolving || searching || !supplementCategories.length" @click="emit('supplement-analysis', [...supplementCategories])">{{ loading ? '正在体检…' : `补充体检${supplementCategories.length ? `（${supplementCategories.length}类）` : ''}` }}</button>
        <p v-if="analysisError" class="location-error" role="alert">{{ analysisError }}；原报告已保留，可重试。</p>
      </div>
      <div class="coverage-list" aria-label="服务区域状态图层">
        <div class="coverage-item" :class="{ active: showNormal }">
          <span class="coverage-swatch normal" aria-hidden="true"></span>
          <span class="coverage-copy"><strong>正常覆盖区</strong><small>步行可达范围内</small></span>
          <el-switch aria-label="显示正常覆盖区" :model-value="showNormal" @update:model-value="emit('update:showNormal', $event)" />
        </div>
        <div class="coverage-item" :class="{ active: showSparse }">
          <span class="coverage-swatch sparse" aria-hidden="true"></span>
          <span class="coverage-copy"><strong>设施稀疏区</strong><small>周边同类设施偏少</small></span>
          <el-switch aria-label="显示设施稀疏区" :model-value="showSparse" @update:model-value="emit('update:showSparse', $event)" />
        </div>
        <div class="coverage-item" :class="{ active: showCritical }">
          <span class="coverage-swatch critical" aria-hidden="true"></span>
          <span class="coverage-copy"><strong>重点服务盲区</strong><small>步行时间超过阈值</small></span>
          <el-switch aria-label="显示重点服务盲区" :model-value="showCritical" @update:model-value="emit('update:showCritical', $event)" />
        </div>
      </div>
    </div>
    <button v-if="!intentActive" class="primary-action" data-guide="run-analysis" type="button" aria-describedby="analysis-source-note" :disabled="loading || resolving || Boolean(locationError) || center.supportStatus !== 'supported' || (!report && !visibleCategories.length)" @click="emit('run')"><Refresh :class="{ spin: loading }" />{{ loading ? '正在分析…' : report ? '重新体检已分析类别' : mapStatus?.real_api_configured ? '开始真实分析' : '开始快照体检' }}<span aria-hidden="true">↗</span></button>
    <div id="analysis-source-note" class="api-note"><span class="api-indicator" :class="{ real: mapStatus?.real_api_configured || source === 'baidu' || source === 'real_api' }" aria-hidden="true"></span><span>当前：{{ mapStatus?.real_api_configured ? '已配置真实模式（分析时调用百度 API）' : source === 'baidu' || source === 'real_api' ? '百度地图真实测算结果' : '本地百度数据快照' }}</span></div>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import NaturalLanguageAnalysis from './NaturalLanguageAnalysis.vue'
import type { ConfirmedAnalysisIntent } from '../types/analysisIntent'
import { ArrowLeft, Location, Refresh, Search } from '@element-plus/icons-vue'
import { ALL_CATEGORIES, FACILITY_ICONS, FACILITY_LABELS, categoryColor } from '../constants/facilities'
import type { AnalysisCenter, CoordinateSystem, LocationCandidate } from '../types/location'
import type { AnalysisMode, AnalysisMinutes, MapProbeResult, MapStatus, Report } from '../types/report'

const intentActive = ref(false)
const supplementCategories = ref<string[]>([])
const walkingTimeOptions: AnalysisMinutes[] = [10, 15, 20]
const props = defineProps<{
  center: AnalysisCenter
  addressQuery: string
  candidates: LocationCandidate[]
  coordinateLng: string
  coordinateLat: string
  coordinateSystem: CoordinateSystem
  coordinateConversionNote: string
  locationError: string
  searching: boolean
  resolving: boolean
  mode: AnalysisMode
  minutes: AnalysisMinutes
  report: Report | null
  analysisError: string
  visibleCategories: string[]
  showNormal: boolean
  showSparse: boolean
  showCritical: boolean
  loading: boolean
  source?: string
  mapStatus: MapStatus | null
  mapStatusLoading: boolean
  mapProbeResult: MapProbeResult | null
  mapProbeLoading: boolean
  realMapReady: boolean
  mobileOpen: boolean
}>()
const displayCategories = computed(() => props.report
  ? ALL_CATEGORIES.filter(category => props.report?.parameters.categories.includes(category))
  : ALL_CATEGORIES)
const unanalyzedCategories = computed(() => ALL_CATEGORIES.filter(category => !displayCategories.value.includes(category)))
const isDisplayed = (category: string) => displayCategories.value.includes(category) && props.visibleCategories.includes(category)
const displayedCount = computed(() => displayCategories.value.filter(isDisplayed).length)
watch(() => props.report?.report_id, () => { supplementCategories.value = [] })
const readinessTitle = computed(() => {
  if (props.mapStatusLoading) return '正在检测地图服务'
  if (!props.mapStatus) return '无法读取地图服务状态'
  if (!props.mapStatus.real_api_configured) return '当前为本地快照模式'
  if (props.mapProbeLoading) return '正在探测百度地理编码接口'
  if (props.mapProbeResult?.verified && props.realMapReady) return 'Web API 探测成功，浏览器底图已加载'
  if (props.mapProbeResult?.verified) return '百度 Web API 地理编码探测成功'
  if (props.mapProbeResult && !props.mapProbeResult.verified) return '百度 Web API 探测失败'
  if (props.realMapReady) return '浏览器底图已加载，Web API 尚未探测'
  return '真实百度 Web 服务已配置，尚未探测'
})
const coordinateSystemLabel = computed(() => props.coordinateSystem === 'wgs84' ? 'WGS84' : props.coordinateSystem === 'gcj02' ? 'GCJ-02' : 'BD-09')
const readinessMessage = computed(() => {
  if (props.mapStatusLoading) return '正在读取后端配置和浏览器底图状态。'
  if (!props.mapStatus) return '请确认后端已启动，然后重新检测。'
  if (!props.mapStatus.real_api_configured) return props.mapStatus.message || '快照数据仅适合演示，不代表最新地图。'
  if (props.mapProbeLoading) return '正在调用一次百度地理编码接口；遇到超时或限流时可能重试并额外消耗配额。'
  if (props.mapProbeResult) return props.mapProbeResult.message
  if (!props.realMapReady) return 'Web 服务仅表示已配置；浏览器底图未加载，请检查浏览器 AK 域名白名单。点击“验证 Web API”会产生真实地理编码调用。'
  return '浏览器底图已加载，但不代表 Web 服务接口已验证。点击“验证 Web API”会调用一次地理编码接口。'
})
const webServiceLabel = computed(() => {
  if (props.mapStatusLoading) return '检测中'
  if (!props.mapStatus) return '状态未知'
  if (!props.mapStatus.real_api_configured) return '未启用'
  if (props.mapProbeLoading) return '探测中'
  if (props.mapProbeResult?.verified) return '探测成功'
  if (props.mapProbeResult && !props.mapProbeResult.verified) return '探测失败'
  return '已配置，未探测'
})
const emit = defineEmits<{
  'update:addressQuery': [value: string]
  'update:coordinateLng': [value: string]
  'update:coordinateLat': [value: string]
  'update:coordinateSystem': [value: CoordinateSystem]
  'update:mode': [value: AnalysisMode]
  'update:minutes': [value: AnalysisMinutes]
  'update:visibleCategories': [value: string[]]
  'update:showNormal': [value: boolean]
  'update:showSparse': [value: boolean]
  'update:showCritical': [value: boolean]
  'search-address': []
  'select-candidate': [value: LocationCandidate]
  'apply-coordinates': []
  'toggle-category': [value: string]
  run: []
  'supplement-analysis': [categories: string[]]
  'confirm-intent': [intent: ConfirmedAnalysisIntent]
  'refresh-map-status': []
  'probe-map-api': []
  'close-mobile': []
  'toggle-collapse': []
}>()

// 标题栏整体作为折叠开关仅在桌面生效；移动端抽屉由独立关闭按钮控制。
function toggleCollapseIfDesktop() {
  if (window.matchMedia('(max-width: 820px)').matches) return
  emit('toggle-collapse')
}
</script>
