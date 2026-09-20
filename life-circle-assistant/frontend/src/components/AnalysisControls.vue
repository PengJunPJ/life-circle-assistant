<template>
  <aside class="control-panel">
    <div class="eyebrow">空间分析工作台</div>
    <h1>15分钟生活圈<br /><em>智能体检</em></h1>
    <p class="intro">用真实步行可达性，识别社区服务覆盖与规划机会。</p>
    <div class="panel-section">
      <label>分析中心点</label>
      <div class="search-box">
        <Search />
        <input :value="addressQuery" aria-label="地址搜索" placeholder="输入地址后搜索候选" @input="emit('update:addressQuery', ($event.target as HTMLInputElement).value)" @keydown.enter="emit('search-address')" />
        <button class="search-submit" :disabled="searching" aria-label="搜索地址候选" @click="emit('search-address')">{{ searching ? '…' : '搜索' }}</button>
      </div>
      <div v-if="candidates.length" class="candidate-list" aria-label="地址候选列表">
        <button v-for="candidate in candidates" :key="`${candidate.lng}-${candidate.lat}-${candidate.address}`" @click="emit('select-candidate', candidate)">
          <Location /><span><strong>{{ candidate.address }}</strong><small>{{ candidate.lng.toFixed(6) }}, {{ candidate.lat.toFixed(6) }}</small></span>
        </button>
      </div>
      <div class="coordinate-entry">
        <input :value="coordinateLng" inputmode="decimal" aria-label="BD-09 经度" placeholder="经度" @input="emit('update:coordinateLng', ($event.target as HTMLInputElement).value)" />
        <input :value="coordinateLat" inputmode="decimal" aria-label="BD-09 纬度" placeholder="纬度" @input="emit('update:coordinateLat', ($event.target as HTMLInputElement).value)" />
        <button :disabled="resolving" @click="emit('apply-coordinates')">确认</button>
      </div>
      <p v-if="locationError" class="location-error" role="alert">{{ locationError }}</p>
      <div class="selected-center" :class="{ unsupported: center.supportStatus === 'unsupported' }">
        <span class="pin-small">●</span>
        <span><strong>{{ center.address }}</strong><small>BD-09 · {{ center.lng.toFixed(6) }}, {{ center.lat.toFixed(6) }}</small></span>
        <span class="selected">{{ resolving ? '确认中' : '已选' }}</span>
      </div>
      <p class="map-pick-hint">也可直接点击地图选点；离线快照仅支持萝岗样例范围。</p>
    </div>
    <div class="panel-section">
      <label>分析参数</label>
      <div class="mode-switch"><button :class="{ active: mode === 'demo' }" @click="emit('update:mode', 'demo')">演示模式</button><button :class="{ active: mode === 'analysis' }" @click="emit('update:mode', 'analysis')">分析模式</button></div>
      <div class="range-row"><span>步行时间</span><strong>{{ minutes }} 分钟</strong></div>
      <el-segmented :model-value="minutes" :options="[10, 15, 20]" size="small" @update:model-value="emit('update:minutes', $event as AnalysisMinutes)" />
    </div>
    <div class="panel-section">
      <label>设施与服务区域图层</label>
      <div class="facility-list"><button v-for="category in Object.keys(FACILITY_LABELS)" :key="category" :class="['facility-toggle', { selected: visibleCategories.includes(category) }]" @click="emit('toggle-category', category)"><span class="facility-icon" :style="{ background: categoryColor(category) }">{{ FACILITY_ICONS[category] }}</span><span>{{ FACILITY_LABELS[category] }}</span><span class="check">{{ visibleCategories.includes(category) ? '✓' : '' }}</span></button></div>
      <div class="switch-line"><span>显示正常覆盖区</span><el-switch :model-value="showNormal" @update:model-value="emit('update:showNormal', $event)" /></div>
      <div class="switch-line"><span>显示设施稀疏区</span><el-switch :model-value="showSparse" @update:model-value="emit('update:showSparse', $event)" /></div>
      <div class="switch-line"><span>显示重点服务盲区</span><el-switch :model-value="showCritical" @update:model-value="emit('update:showCritical', $event)" /></div>
    </div>
    <button class="primary-action" :disabled="loading || resolving || Boolean(locationError) || center.supportStatus !== 'supported'" @click="emit('run')"><Refresh :class="{ spin: loading }" />{{ loading ? '正在分析…' : '开始体检' }}<span>↗</span></button>
    <div class="api-note"><span class="api-indicator" :class="{ real: source === 'baidu' || source === 'real_api' }"></span><span>当前：{{ source === 'baidu' || source === 'real_api' ? '百度地图真实数据' : '本地百度数据快照' }}</span></div>
  </aside>
</template>

<script setup lang="ts">
import { Location, Refresh, Search } from '@element-plus/icons-vue'
import { FACILITY_ICONS, FACILITY_LABELS, categoryColor } from '../constants/facilities'
import type { AnalysisCenter, LocationCandidate } from '../types/location'
import type { AnalysisMode, AnalysisMinutes } from '../types/report'

defineProps<{
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
}>()
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
}>()
</script>
