<template>
  <section v-if="comparison" class="option-comparison" aria-label="规划方案比较">
    <div class="comparison-heading"><strong>{{ comparison.goal_label }}</strong><small>{{ comparableCount }}/{{ comparison.options.length }} 个方案可比较</small></div>
    <p class="comparison-summary">{{ comparison.summary }}</p>
    <div class="option-list">
      <article v-for="option in comparison.options" :key="option.id" class="option-row" :class="{ preferred: comparison.preferred_option_ids.includes(option.id), excluded: !option.eligible }">
        <div class="option-title"><strong>{{ option.title }}</strong><span v-if="option.rank">第 {{ option.rank }} 名</span><span v-else-if="option.status === 'pending'">未完成</span><span v-else-if="!option.eligible">不排名</span></div>
        <p v-if="option.location_label" class="option-location">{{ option.location_label }}</p>
        <div v-if="option.delta" class="option-metrics">
          <span>重点盲区 {{ signed(option.delta.critical_zone_count, '个') }}</span>
          <span>分类覆盖 {{ signed(option.delta.coverage_area_sqm, '㎡') }}</span>
          <span>综合指数 {{ signed(option.delta.overall_score, '分') }}</span>
        </div>
        <p v-if="option.excluded_reason || option.error" class="option-boundary">{{ option.excluded_reason || option.error }}</p>
        <button v-if="option.status === 'completed' && option.simulation" type="button" class="option-map" @click="$emit('show-simulation', option.id)">在地图查看</button>
      </article>
    </div>
    <p class="comparison-disclosure">{{ comparison.disclosure }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { PlanningComparison } from '../types/planning'
const props = defineProps<{ comparison: PlanningComparison }>()
defineEmits<{ 'show-simulation': [id: string] }>()
const comparableCount = computed(() => props.comparison.options.filter(option => option.eligible).length)
function signed(value: number | null, unit: string) {
  if (value === null || value === undefined) return '不可用'
  return `${value > 0 ? '+' : ''}${new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 }).format(value)}${unit}`
}
</script>

<style scoped>
.option-comparison { margin: 10px 0; border-top: 1px solid #d6e4dc; }
.comparison-heading, .option-title, .option-metrics { display: flex; align-items: baseline; flex-wrap: wrap; gap: 8px; }
.comparison-heading { justify-content: space-between; padding-top: 9px; color: #346b59; font-size: 10px; }
.comparison-heading small, .option-title span { color: #72837e; font-size: 9px; }
.comparison-summary { margin: 6px 0; color: #36564f; font-size: 10px; line-height: 1.5; }
.option-row { padding: 8px 0; border-top: 1px solid #e5ede8; }
.option-row.preferred { border-left: 2px solid #4a9a82; padding-left: 7px; }
.option-row.excluded { opacity: .78; }
.option-title { justify-content: space-between; color: #3c5b54; font-size: 10px; }
.option-location { margin: 3px 0 0; color: #72837e; font-size: 9px; overflow-wrap: anywhere; }
.option-metrics { margin-top: 5px; color: #526d63; font-size: 9px; row-gap: 3px; }
.option-boundary, .comparison-disclosure { color: #92723d; font-size: 8px; line-height: 1.45; }
.option-map { margin-top: 5px; padding: 4px 7px; border: 1px solid #c9ddd3; border-radius: 4px; background: #f1f8f4; color: #397568; font-size: 9px; }
.comparison-disclosure { margin: 6px 0; color: #7f908b; }
html[data-theme="dark"] .option-comparison { border-color: rgba(126,214,199,.2); }
html[data-theme="dark"] .comparison-heading, html[data-theme="dark"] .option-title { color: #7ff0da; }
html[data-theme="dark"] .comparison-heading small, html[data-theme="dark"] .option-title span { color: #9db8b8; }
html[data-theme="dark"] .option-location { color: #9db8b8; }
html[data-theme="dark"] .comparison-summary { color: #d7ece7; }
html[data-theme="dark"] .option-row { border-color: rgba(126,214,199,.12); }
html[data-theme="dark"] .option-metrics { color: #9db8b8; }
html[data-theme="dark"] .option-map { border-color: rgba(126,214,199,.24); background: rgba(46,230,197,.08); color: #7ff0da; }
html[data-theme="dark"] .comparison-disclosure { color: #9db8b8; }
</style>
