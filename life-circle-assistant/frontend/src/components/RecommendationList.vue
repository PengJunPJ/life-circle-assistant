<template>
  <div v-if="recommendations.length" class="recommendation-list">
    <article
      v-for="item in recommendations"
      :id="`recommendation-card-${item.id}`"
      :key="item.id"
      :class="['recommendation-card', { selected: item.id === selectedId }]"
    >
      <div class="recommendation-heading">
        <span :class="['priority', item.priority_level]">{{ item.priority }}优先级</span>
        <div><strong>{{ item.title }}</strong><small>{{ item.category_label }} · {{ item.target_region_ids.length }} 个重点盲区</small></div>
        <button type="button" :aria-label="`在地图定位${item.title}`" @click="emit('locate', item.id)">地图定位</button>
      </div>
      <p>{{ item.body }}</p>
      <details :open="expandedIds.includes(item.id)" @toggle="rememberExpanded(item.id, $event)">
        <summary>依据与候选点 <span>{{ item.candidate_locations.length }} 个候选点</span></summary>
        <dl class="recommendation-evidence">
        <div><dt>问题依据</dt><dd>{{ item.problem_basis }}</dd></div>
        <div><dt>最近设施</dt><dd>{{ nearestFacilityText(item) }}</dd></div>
        <div><dt>目标改善</dt><dd>{{ item.target_improvement.description }}</dd></div>
      </dl>
      <div class="candidate-list">
        <div
          v-for="candidate in item.candidate_locations"
          :key="candidate.id"
          class="candidate-item"
        >
          <button type="button" class="candidate-locate" @click="emit('locate', item.id)">
            <span>候选点</span>
            <strong>{{ candidate.region_id }}</strong>
            <small>{{ candidate.lng.toFixed(5) }}, {{ candidate.lat.toFixed(5) }}</small>
            <em>{{ candidate.reason }}</em>
          </button>
          <button type="button" class="candidate-simulate" :disabled="simulationDisabled" @click="emit('simulate', item.category, candidate)">模拟此点</button>
        </div>
        </div>
      </details>
    </article>
  </div>
  <div v-else class="recommendation-empty" role="status">
    <strong>{{ summary.status === 'calculation_incomplete' ? '数据不足，暂不能生成建议' : '当前无需补充设施' }}</strong>
    <span>{{ summary.message }}</span>
  </div>
</template>

<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import type { PlanningRecommendation, RecommendationCandidate, RecommendationSummary } from '../types/recommendations'

const props = defineProps<{
  recommendations: PlanningRecommendation[]
  summary: RecommendationSummary
  selectedId: string | null
  simulationDisabled?: boolean
  active?: boolean
}>()
const expandedIds = ref<string[]>([])
function rememberExpanded(id: string, event: Event) {
  const open = (event.target as HTMLDetailsElement).open
  expandedIds.value = open ? [...new Set([...expandedIds.value, id])] : expandedIds.value.filter(value => value !== id)
}
const emit = defineEmits<{
  locate: [recommendationId: string]
  simulate: [category: string, candidate: RecommendationCandidate]
}>()

function nearestFacilityText(item: PlanningRecommendation) {
  const nearest = item.nearest_facility
  if (nearest.status === 'not_found') return nearest.message
  return `${nearest.name}，步行约 ${nearest.walk_minutes} 分钟、${nearest.walk_distance_m} 米（依据 ${nearest.source_region_id}）`
}

watch(() => [props.selectedId, props.active] as const, async ([id, active]) => {
  if (!id || active === false) return
  if (!expandedIds.value.includes(id)) expandedIds.value.push(id)
  await nextTick()
  document.getElementById(`recommendation-card-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
}, { immediate: true })
watch(() => props.recommendations, () => { expandedIds.value = expandedIds.value.filter(id => props.recommendations.some(item => item.id === id)) })
</script>

<style scoped>
.recommendation-list { display: grid; gap: 10px; margin-top: 10px; }
.recommendation-card { padding: 12px 0; border: 0; border-bottom: 1px solid var(--report-line, #e0e8e3); border-radius: 0; background: transparent; transition: background .2s; }
.recommendation-card.selected { border-color: #2f8f80; box-shadow: 0 0 0 2px rgba(47,143,128,.12); }
.recommendation-heading { display: grid; grid-template-columns: auto minmax(0, 1fr); align-items: start; gap: 7px; }
.recommendation-heading strong, .recommendation-heading small { display: block; }
.recommendation-heading strong { color: #2f4d49; font-size: 13px; line-height: 1.5; overflow-wrap: anywhere; }
.recommendation-heading small { margin-top: 3px; color: #667d75; font-size: 11px; }
.recommendation-heading button { grid-column: 2; justify-self: start; min-height: 28px; padding: 4px 8px; border: 1px solid #c9ddd4; border-radius: 4px; background: transparent; color: #39786c; font-size: 12px; }
.recommendation-card > p { margin: 9px 0; color: #61766e; font-size: 12px; line-height: 1.65; }
.recommendation-card details > summary { display: flex; justify-content: space-between; gap: 8px; cursor: pointer; padding: 7px 0; color: var(--report-accent, #39786c); font-size: 12px; }
.recommendation-card details > summary::after { content: '+'; }
.recommendation-card details[open] > summary::after { content: '−'; }
.recommendation-card details > summary span { margin-left: auto; color: var(--report-muted, #667d75); font-size: 11px; }
.priority { height: auto; padding: 4px 5px; border-radius: 3px; color: #fff; font-size: 10px; white-space: nowrap; }
.priority.high { background: #c65b45; }
.priority.medium { background: #c6963e; }
.recommendation-evidence { display: grid; gap: 7px; margin: 0; }
.recommendation-evidence div { padding-top: 7px; border-top: 1px solid #edf1ee; }
.recommendation-evidence dt { color: #4d786f; font-size: 12px; font-weight: 700; }
.recommendation-evidence dd { margin: 4px 0 0; color: #667d75; font-size: 12px; line-height: 1.65; }
.candidate-list { display: grid; gap: 6px; margin-top: 9px; }
.candidate-item { display: grid; grid-template-columns: minmax(0, 1fr) auto; border: 1px dashed #b9d3c8; border-radius: 4px; background: #f5faf7; overflow: hidden; }
.candidate-locate { display: grid; grid-template-columns: auto 1fr; gap: 2px 6px; padding: 7px 8px; background: transparent; text-align: left; }
.candidate-locate span { grid-row: span 2; align-self: center; padding: 3px 4px; color: #347465; font-size: 11px; }
.candidate-locate strong { color: #31564f; font-size: 11px; overflow-wrap: anywhere; }
.candidate-locate small { color: #667d75; font-size: 10px; overflow-wrap: anywhere; }
.candidate-locate em { grid-column: 1 / -1; margin-top: 4px; color: #667d75; font-size: 11px; font-style: normal; line-height: 1.6; }
.candidate-simulate { padding: 0 7px; border-left: 1px solid #cfe0d8; background: #e9f4ef; color: #2e7567; font-size: 11px; font-weight: 700; white-space: nowrap; }
.candidate-simulate:hover, .candidate-simulate:focus-visible { background: #dceee6; outline: 0; }
.recommendation-empty { display: flex; flex-direction: column; gap: 5px; margin-top: 10px; padding: 13px; border: 1px solid #d6e6de; border-radius: 5px; background: #f1f8f4; }
.recommendation-empty strong { color: #377364; font-size: 13px; }
.recommendation-empty span { color: #667d75; font-size: 12px; line-height: 1.6; }
html[data-theme="dark"] .recommendation-card { border-color: rgba(126,214,199,.16); background: transparent; }
html[data-theme="dark"] .recommendation-card.selected { border-color: #2ee6c5; box-shadow: 0 0 0 2px rgba(46,230,197,.18); }
html[data-theme="dark"] .recommendation-heading strong { color: #eaf6f3; }
html[data-theme="dark"] .recommendation-heading small { color: #6f8b90; }
html[data-theme="dark"] .recommendation-heading button { border-color: rgba(126,214,199,.24); background: rgba(46,230,197,.08); color: #7ff0da; }
html[data-theme="dark"] .recommendation-card > p { color: #9db8b8; }
html[data-theme="dark"] .priority.medium { color: #14202b; }
html[data-theme="dark"] .recommendation-evidence div { border-top-color: rgba(126,214,199,.1); }
html[data-theme="dark"] .recommendation-evidence dt { color: #7ff0da; }
html[data-theme="dark"] .recommendation-evidence dd { color: #9db8b8; }
html[data-theme="dark"] .candidate-item { border-color: rgba(126,214,199,.28); background: rgba(9,18,27,.5); }
html[data-theme="dark"] .candidate-locate span { background: rgba(46,230,197,.16); color: #7ff0da; }
html[data-theme="dark"] .candidate-locate strong { color: #cfe7e1; }
html[data-theme="dark"] .candidate-locate small { color: #6f8b90; }
html[data-theme="dark"] .candidate-locate em { color: #9db8b8; }
html[data-theme="dark"] .candidate-simulate { border-left-color: rgba(126,214,199,.16); background: rgba(46,230,197,.08); color: #7ff0da; }
html[data-theme="dark"] .candidate-simulate:hover, html[data-theme="dark"] .candidate-simulate:focus-visible { background: rgba(46,230,197,.16); }
html[data-theme="dark"] .recommendation-empty { border-color: rgba(126,214,199,.2); background: rgba(46,230,197,.06); }
html[data-theme="dark"] .recommendation-empty strong { color: #7ff0da; }
html[data-theme="dark"] .recommendation-empty span { color: #9db8b8; }
</style>
