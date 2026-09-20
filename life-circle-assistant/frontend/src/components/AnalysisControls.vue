<template>
  <aside class="control-panel">
    <div class="eyebrow">空间分析工作台</div>
    <h1>15分钟生活圈<br /><em>智能体检</em></h1>
    <p class="intro">用真实步行可达性，识别社区服务覆盖与规划机会。</p>
    <div class="panel-section">
      <label>分析中心点</label>
      <div class="search-box"><Search /><input :value="address" aria-label="分析中心点" @input="emit('update:address', ($event.target as HTMLInputElement).value)" /><Location class="location-icon" /></div>
      <div class="suggestion"><span class="pin-small">●</span><span>广州市 · 黄埔区 · 萝岗街道</span><span class="selected">已选</span></div>
    </div>
    <div class="panel-section">
      <label>分析参数</label>
      <div class="mode-switch"><button :class="{ active: mode === 'demo' }" @click="emit('update:mode', 'demo')">演示模式</button><button :class="{ active: mode === 'analysis' }" @click="emit('update:mode', 'analysis')">分析模式</button></div>
      <div class="range-row"><span>步行时间</span><strong>{{ minutes }} 分钟</strong></div>
      <el-segmented :model-value="minutes" :options="[10, 15, 20]" size="small" @update:model-value="emit('update:minutes', $event as AnalysisMinutes)" />
    </div>
    <div class="panel-section">
      <label>设施图层</label>
      <div class="facility-list"><button v-for="category in Object.keys(FACILITY_LABELS)" :key="category" :class="['facility-toggle', { selected: visibleCategories.includes(category) }]" @click="emit('toggle-category', category)"><span class="facility-icon" :style="{ background: categoryColor(category) }">{{ FACILITY_ICONS[category] }}</span><span>{{ FACILITY_LABELS[category] }}</span><span class="check">{{ visibleCategories.includes(category) ? '✓' : '' }}</span></button></div>
      <div class="switch-line"><span>显示设施稀疏区</span><el-switch :model-value="showSparse" @update:model-value="emit('update:showSparse', $event)" /></div>
    </div>
    <button class="primary-action" :disabled="loading" @click="emit('run')"><Refresh :class="{ spin: loading }" />{{ loading ? '正在分析…' : '开始体检' }}<span>↗</span></button>
    <div class="api-note"><span class="api-indicator" :class="{ real: source === 'baidu' }"></span><span>当前：{{ source === 'baidu' ? '百度地图真实数据' : '本地百度数据快照' }}</span></div>
  </aside>
</template>

<script setup lang="ts">
import { Location, Refresh, Search } from '@element-plus/icons-vue'
import { FACILITY_ICONS, FACILITY_LABELS, categoryColor } from '../constants/facilities'
import type { AnalysisMode, AnalysisMinutes } from '../types/report'

defineProps<{ address: string; mode: AnalysisMode; minutes: AnalysisMinutes; visibleCategories: string[]; showSparse: boolean; loading: boolean; source?: string }>()
const emit = defineEmits<{
  'update:address': [value: string]
  'update:mode': [value: AnalysisMode]
  'update:minutes': [value: AnalysisMinutes]
  'update:showSparse': [value: boolean]
  'toggle-category': [value: string]
  run: []
}>()
</script>
