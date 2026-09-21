<template>
  <aside class="control-panel" aria-label="分析参数">
    <div class="mobile-panel-heading">
      <div><div class="eyebrow">空间分析工作台</div><strong>设置分析参数</strong></div>
      <button class="mobile-panel-close" type="button" aria-label="关闭分析参数面板并返回地图" @click="emit('close-mobile')">×</button>
    </div>
    <div class="desktop-panel-heading eyebrow">空间分析工作台</div>
    <h1>15分钟生活圈<br /><em>智能体检</em></h1>
    <p class="intro">用真实步行可达性，识别社区服务覆盖与规划机会。</p>
    <div class="map-readiness" :class="{ ready: mapStatus?.real_api_available && realMapReady, snapshot: !mapStatusLoading && mapStatus && !mapStatus.real_api_available }" data-guide="source-status" role="status" aria-live="polite">
      <div class="map-readiness-heading">
        <span class="readiness-mark" aria-hidden="true">{{ mapStatus?.real_api_available && realMapReady ? '✓' : mapStatusLoading ? '···' : '!' }}</span>
        <span><strong>{{ readinessTitle }}</strong><small>{{ readinessMessage }}</small></span>
        <button type="button" :disabled="mapStatusLoading" @click="emit('refresh-map-status')">重新检测</button>
      </div>
      <div class="readiness-checks">
        <span :class="{ ok: mapStatus?.real_api_available }"><i aria-hidden="true"></i>Web 服务{{ webServiceLabel }}</span>
        <span :class="{ ok: realMapReady }"><i aria-hidden="true"></i>百度底图{{ realMapReady ? '已加载' : '未加载' }}</span>
      </div>
    </div>
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
      <div class="coordinate-entry">
        <input :value="coordinateLng" inputmode="decimal" aria-label="BD-09 经度" placeholder="经度" @input="emit('update:coordinateLng', ($event.target as HTMLInputElement).value)" />
        <input :value="coordinateLat" inputmode="decimal" aria-label="BD-09 纬度" placeholder="纬度" @input="emit('update:coordinateLat', ($event.target as HTMLInputElement).value)" />
        <button type="button" :disabled="resolving" aria-label="使用输入的 BD-09 坐标" @click="emit('apply-coordinates')">确认</button>
      </div>
      <p v-if="locationError" class="location-error" role="alert">{{ locationError }}</p>
      <div class="selected-center" :class="{ unsupported: center.supportStatus === 'unsupported' }" role="status" aria-live="polite">
        <span class="pin-small">●</span>
        <span><strong>{{ center.address }}</strong><small>BD-09 · {{ center.lng.toFixed(6) }}, {{ center.lat.toFixed(6) }}</small></span>
        <span class="selected">{{ resolving ? '确认中' : '已选' }}</span>
      </div>
      <p class="map-pick-hint">也可直接点击地图选点；离线快照仅支持萝岗样例范围。</p>
    </div>
    <div class="panel-section" data-guide="analysis-parameters">
      <label>分析参数</label>
      <div class="mode-switch" aria-label="分析精度模式"><button type="button" :class="{ active: mode === 'demo' }" :aria-pressed="mode === 'demo'" @click="emit('update:mode', 'demo')">快速分析</button><button type="button" :class="{ active: mode === 'analysis' }" :aria-pressed="mode === 'analysis'" @click="emit('update:mode', 'analysis')">正式分析</button></div>
      <p class="mode-note">正式地图模式下两种精度都会请求百度；正式分析会增加等时圈采样次数。</p>
      <div class="range-row"><span>步行时间</span><strong>{{ minutes }} 分钟</strong></div>
      <el-segmented :model-value="minutes" :options="[10, 15, 20]" size="small" @update:model-value="emit('update:minutes', $event as AnalysisMinutes)" />
    </div>
    <div class="panel-section">
      <label>设施与服务区域图层</label>
      <div class="facility-list"><button v-for="category in Object.keys(FACILITY_LABELS)" :key="category" type="button" :class="['facility-toggle', { selected: visibleCategories.includes(category) }]" :aria-pressed="visibleCategories.includes(category)" @click="emit('toggle-category', category)"><span class="facility-icon" :style="{ background: categoryColor(category) }" aria-hidden="true">{{ FACILITY_ICONS[category] }}</span><span>{{ FACILITY_LABELS[category] }}</span><span class="check" aria-hidden="true">{{ visibleCategories.includes(category) ? '✓' : '' }}</span></button></div>
      <div class="switch-line"><span>显示正常覆盖区</span><el-switch aria-label="显示正常覆盖区" :model-value="showNormal" @update:model-value="emit('update:showNormal', $event)" /></div>
      <div class="switch-line"><span>显示设施稀疏区</span><el-switch aria-label="显示设施稀疏区" :model-value="showSparse" @update:model-value="emit('update:showSparse', $event)" /></div>
      <div class="switch-line"><span>显示重点服务盲区</span><el-switch aria-label="显示重点服务盲区" :model-value="showCritical" @update:model-value="emit('update:showCritical', $event)" /></div>
    </div>
    <button class="primary-action" data-guide="run-analysis" type="button" aria-describedby="analysis-source-note" :disabled="loading || resolving || Boolean(locationError) || center.supportStatus !== 'supported'" @click="emit('run')"><Refresh :class="{ spin: loading }" />{{ loading ? '正在分析…' : mapStatus?.real_api_available ? '开始真实分析' : '开始快照体检' }}<span aria-hidden="true">↗</span></button>
    <div id="analysis-source-note" class="api-note"><span class="api-indicator" :class="{ real: mapStatus?.real_api_available || source === 'baidu' || source === 'real_api' }" aria-hidden="true"></span><span>当前：{{ mapStatus?.real_api_available || source === 'baidu' || source === 'real_api' ? '百度地图真实数据' : '本地百度数据快照' }}</span></div>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Location, Refresh, Search } from '@element-plus/icons-vue'
import { FACILITY_ICONS, FACILITY_LABELS, categoryColor } from '../constants/facilities'
import type { AnalysisCenter, LocationCandidate } from '../types/location'
import type { AnalysisMode, AnalysisMinutes, MapStatus } from '../types/report'

const props = defineProps<{
  center: AnalysisCenter
  addressQuery: string
  candidates: LocationCandidate[]
  coordinateLng: string
  coordinateLat: string
  locationError: string
  searching: boolean
  resolving: boolean
  mode: AnalysisMode
  minutes: AnalysisMinutes
  visibleCategories: string[]
  showNormal: boolean
  showSparse: boolean
  showCritical: boolean
  loading: boolean
  source?: string
  mapStatus: MapStatus | null
  mapStatusLoading: boolean
  realMapReady: boolean
  mobileOpen: boolean
}>()
const readinessTitle = computed(() => {
  if (props.mapStatusLoading) return '正在检测地图服务'
  if (!props.mapStatus) return '无法读取地图服务状态'
  if (props.mapStatus?.real_api_available && props.realMapReady) return '正式百度地图已就绪'
  if (props.mapStatus?.real_api_available) return '真实 Web 服务已启用'
  return '当前为本地快照模式'
})
const readinessMessage = computed(() => {
  if (props.mapStatusLoading) return '正在读取后端和浏览器底图状态。'
  if (!props.mapStatus) return '请确认后端已启动，然后重新检测。'
  if (props.mapStatus?.real_api_available && props.realMapReady) return '可以开始正式地图测试。'
  if (props.mapStatus?.real_api_available) return '底图未加载，请检查浏览器 AK 域名白名单。'
  return props.mapStatus?.message || '快照数据仅适合演示，不代表最新地图。'
})
const webServiceLabel = computed(() => {
  if (props.mapStatusLoading) return '检测中'
  if (!props.mapStatus) return '状态未知'
  return props.mapStatus.real_api_available ? '已连接' : '未启用'
})
const emit = defineEmits<{
  'update:addressQuery': [value: string]
  'update:coordinateLng': [value: string]
  'update:coordinateLat': [value: string]
  'update:mode': [value: AnalysisMode]
  'update:minutes': [value: AnalysisMinutes]
  'update:showNormal': [value: boolean]
  'update:showSparse': [value: boolean]
  'update:showCritical': [value: boolean]
  'search-address': []
  'select-candidate': [value: LocationCandidate]
  'apply-coordinates': []
  'toggle-category': [value: string]
  run: []
  'refresh-map-status': []
  'close-mobile': []
}>()
</script>
