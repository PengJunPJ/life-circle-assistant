<template>
  <section class="simulation-panel" aria-labelledby="simulation-title">
    <div class="simulation-heading">
      <div><strong id="simulation-title">新增设施改善模拟</strong><small>原报告与来源设施保持不变</small></div>
      <button v-if="location || result" type="button" class="simulation-clear" @click="emit('clear')">清除模拟</button>
    </div>
    <label class="simulation-field">
      <span>假设设施类别</span>
      <select :value="category" @change="emit('update:category', ($event.target as HTMLSelectElement).value)">
        <option v-for="item in report.parameters.categories" :key="item" :value="item">{{ FACILITY_LABELS[item] || item }}</option>
      </select>
    </label>
    <div class="simulation-location">
      <div>
        <span>假设位置</span>
        <strong v-if="location">{{ location.lng.toFixed(6) }}, {{ location.lat.toFixed(6) }}</strong>
        <strong v-else>尚未选择</strong>
        <small v-if="location">{{ location.selectionMethod === 'recommendation' ? '来自规划建议候选点' : '来自地图选点' }}</small>
        <small v-else>可从建议中直接模拟，或在地图指定位置</small>
      </div>
      <button type="button" :class="{ active: picking }" @click="emit('pick-map')">{{ picking ? '请点击地图' : '地图选点' }}</button>
    </div>
    <p v-if="error" class="simulation-error" role="alert">{{ error }}</p>
    <button type="button" class="simulation-run" :disabled="!location || loading" @click="emit('run')">
      {{ loading ? '正在计算改善效果…' : '运行改善模拟' }}
    </button>

    <div v-if="result" class="simulation-result" aria-live="polite">
      <div class="simulation-result-title">
        <strong>{{ result.category_label }}模拟结果</strong>
        <span>假设设施以蓝色标记，模拟区域以蓝色边界显示</span>
      </div>
      <div class="simulation-comparison" role="table" aria-label="模拟前后指标对比">
        <div class="comparison-head" role="row"><span role="columnheader">指标</span><span role="columnheader">模拟前</span><span role="columnheader">模拟后</span><span role="columnheader">变化</span></div>
        <div v-for="metric in metrics" :key="metric.key" class="comparison-row" role="row">
          <span role="cell">{{ metric.label }}</span>
          <b role="cell">{{ metric.before }}</b>
          <b role="cell">{{ metric.after }}</b>
          <em role="cell" :class="metric.tone">{{ metric.delta }}</em>
        </div>
      </div>
      <small class="simulation-disclosure">{{ result.data_quality.disclosure }}</small>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { FACILITY_LABELS } from '../constants/facilities'
import type { Report } from '../types/report'
import type { SimulationLocation, SimulationResult } from '../types/simulation'

const props = defineProps<{
  report: Report
  category: string
  location: SimulationLocation | null
  result: SimulationResult | null
  loading: boolean
  picking: boolean
  error: string
}>()
const emit = defineEmits<{
  'update:category': [category: string]
  'pick-map': []
  run: []
  clear: []
}>()

const metrics = computed(() => {
  if (!props.result) return []
  const { before, after, delta } = props.result
  return [
    metric('category_score', '类别评分', before.category_score, after.category_score, delta.category_score, '分'),
    metric('overall_score', '综合分', before.overall_score, after.overall_score, delta.overall_score, '分'),
    metric('coverage_area_sqm', '覆盖面积', before.coverage_area_sqm, after.coverage_area_sqm, delta.coverage_area_sqm, '㎡'),
    metric('critical_zone_count', '重点盲区', before.critical_zone_count, after.critical_zone_count, delta.critical_zone_count, '个', true),
  ]
})

function metric(key: string, label: string, before: number | null, after: number | null, delta: number | null, unit: string, lowerIsBetter = false) {
  const signed = delta === null ? '—' : `${delta > 0 ? '+' : ''}${delta.toLocaleString()}${unit}`
  const improved = delta !== null && (lowerIsBetter ? delta < 0 : delta > 0)
  const worsened = delta !== null && (lowerIsBetter ? delta > 0 : delta < 0)
  return {
    key,
    label,
    before: before === null ? '—' : `${before.toLocaleString()}${unit}`,
    after: after === null ? '—' : `${after.toLocaleString()}${unit}`,
    delta: signed,
    tone: improved ? 'improved' : worsened ? 'worsened' : '',
  }
}
</script>

<style scoped>
.simulation-panel { margin-top: 10px; padding: 12px; border: 1px solid #cfe0d8; border-radius: 6px; background: #f3f8f5; }
.simulation-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
.simulation-heading strong, .simulation-heading small { display: block; }
.simulation-heading strong { color: #31564f; font-size: 11px; }
.simulation-heading small { margin-top: 3px; color: #879792; font-size: 8px; }
.simulation-clear { background: transparent; color: #8b665e; font-size: 9px; }
.simulation-field { display: grid; grid-template-columns: auto 1fr; align-items: center; gap: 8px; margin-top: 11px; color: #61756f; font-size: 9px; }
.simulation-field select { min-width: 0; height: 29px; padding: 0 7px; border: 1px solid #cbdcd3; border-radius: 4px; background: #fff; color: #31564f; font-size: 9px; }
.simulation-location { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 8px; padding: 8px; border-radius: 4px; background: #fff; }
.simulation-location span, .simulation-location strong, .simulation-location small { display: block; }
.simulation-location span { color: #78908a; font-size: 8px; }
.simulation-location strong { margin-top: 2px; color: #31564f; font-size: 9px; }
.simulation-location small { margin-top: 2px; color: #95a39f; font-size: 8px; }
.simulation-location button { flex: 0 0 auto; padding: 5px 7px; border: 1px solid #b9d3c8; border-radius: 3px; background: #edf6f1; color: #367567; font-size: 9px; }
.simulation-location button.active { border-color: #397d70; background: #397d70; color: #fff; }
.simulation-run { width: 100%; height: 31px; margin-top: 8px; border-radius: 4px; background: #315f58; color: #fff; font-size: 10px; font-weight: 700; }
.simulation-run:disabled { cursor: not-allowed; opacity: .5; }
.simulation-error { margin: 7px 0 0; color: #a84f3d; font-size: 9px; line-height: 1.45; }
.simulation-result { margin-top: 11px; padding-top: 10px; border-top: 1px solid #d5e3dc; }
.simulation-result-title strong, .simulation-result-title span { display: block; }
.simulation-result-title strong { color: #294f48; font-size: 10px; }
.simulation-result-title span { margin-top: 3px; color: #81928d; font-size: 8px; }
.simulation-comparison { margin-top: 8px; border-top: 1px solid #d9e5df; border-left: 1px solid #d9e5df; }
.comparison-head, .comparison-row { display: grid; grid-template-columns: 1.2fr repeat(3, 1fr); }
.comparison-head span, .comparison-row > * { padding: 6px 4px; border-right: 1px solid #d9e5df; border-bottom: 1px solid #d9e5df; text-align: right; font-size: 8px; }
.comparison-head span:first-child, .comparison-row > *:first-child { text-align: left; }
.comparison-head { background: #e8f1ec; color: #6d817b; }
.comparison-row { background: #fff; color: #627670; }
.comparison-row b { color: #31564f; font-weight: 700; }
.comparison-row em { color: #7f908b; font-style: normal; }
.comparison-row em.improved { color: #26836d; font-weight: 700; }
.comparison-row em.worsened { color: #b4533f; font-weight: 700; }
.simulation-disclosure { display: block; margin-top: 8px; color: #879792; font-size: 8px; line-height: 1.5; }
html[data-theme="dark"] .simulation-panel { border-color: rgba(126,214,199,.2); background: rgba(9,18,27,.5); }
html[data-theme="dark"] .simulation-heading strong { color: #eaf6f3; }
html[data-theme="dark"] .simulation-heading small { color: #6f8b90; }
html[data-theme="dark"] .simulation-clear { color: #ff9d8d; }
html[data-theme="dark"] .simulation-field { color: #9db8b8; }
html[data-theme="dark"] .simulation-field select { border-color: rgba(126,214,199,.2); background: rgba(16,32,46,.8); color: #cfe7e1; }
html[data-theme="dark"] .simulation-location { background: rgba(16,32,46,.7); }
html[data-theme="dark"] .simulation-location span { color: #6f8b90; }
html[data-theme="dark"] .simulation-location strong { color: #cfe7e1; }
html[data-theme="dark"] .simulation-location small { color: #6f8b90; }
html[data-theme="dark"] .simulation-location button { border-color: rgba(126,214,199,.24); background: rgba(46,230,197,.08); color: #7ff0da; }
html[data-theme="dark"] .simulation-location button.active { border-color: #2ee6c5; background: #2ee6c5; color: #04211c; }
html[data-theme="dark"] .simulation-run { background: linear-gradient(120deg, #2ee6c5, #38bdf8); color: #04211c; }
html[data-theme="dark"] .simulation-error { color: #ff9d8d; }
html[data-theme="dark"] .simulation-result { border-top-color: rgba(126,214,199,.12); }
html[data-theme="dark"] .simulation-result-title strong { color: #eaf6f3; }
html[data-theme="dark"] .simulation-result-title span { color: #6f8b90; }
html[data-theme="dark"] .simulation-comparison { border-top-color: rgba(126,214,199,.12); border-left-color: rgba(126,214,199,.12); }
html[data-theme="dark"] .comparison-head span, html[data-theme="dark"] .comparison-row > * { border-right-color: rgba(126,214,199,.12); border-bottom-color: rgba(126,214,199,.12); }
html[data-theme="dark"] .comparison-head { background: rgba(46,230,197,.08); color: #9db8b8; }
html[data-theme="dark"] .comparison-row { background: rgba(16,32,46,.5); color: #9db8b8; }
html[data-theme="dark"] .comparison-row b { color: #eaf6f3; }
html[data-theme="dark"] .comparison-row em { color: #9db8b8; }
html[data-theme="dark"] .comparison-row em.improved { color: #34e0b4; }
html[data-theme="dark"] .comparison-row em.worsened { color: #ff6b57; }
html[data-theme="dark"] .simulation-disclosure { color: #6f8b90; }
</style>
