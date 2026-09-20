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
      <dl class="recommendation-evidence">
        <div><dt>问题依据</dt><dd>{{ item.problem_basis }}</dd></div>
        <div><dt>最近设施</dt><dd>{{ nearestFacilityText(item) }}</dd></div>
        <div><dt>目标改善</dt><dd>{{ item.target_improvement.description }}</dd></div>
      </dl>
      <div class="candidate-list">
        <button
          v-for="candidate in item.candidate_locations"
          :key="candidate.id"
          type="button"
          @click="emit('locate', item.id)"
        >
          <span>候选点</span>
          <strong>{{ candidate.region_id }}</strong>
          <small>{{ candidate.lng.toFixed(5) }}, {{ candidate.lat.toFixed(5) }}</small>
          <em>{{ candidate.reason }}</em>
        </button>
      </div>
    </article>
  </div>
  <div v-else class="recommendation-empty" role="status">
    <strong>当前无需补充设施</strong>
    <span>{{ summary.message }}</span>
  </div>
</template>

<script setup lang="ts">
import { nextTick, watch } from 'vue'
import type { PlanningRecommendation, RecommendationSummary } from '../types/recommendations'

const props = defineProps<{
  recommendations: PlanningRecommendation[]
  summary: RecommendationSummary
  selectedId: string | null
}>()
const emit = defineEmits<{ locate: [recommendationId: string] }>()

function nearestFacilityText(item: PlanningRecommendation) {
  const nearest = item.nearest_facility
  if (nearest.status === 'not_found') return nearest.message
  return `${nearest.name}，步行约 ${nearest.walk_minutes} 分钟、${nearest.walk_distance_m} 米（依据 ${nearest.source_region_id}）`
}

watch(() => props.selectedId, async (id) => {
  if (!id) return
  await nextTick()
  document.getElementById(`recommendation-card-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
})
</script>

<style scoped>
.recommendation-list { display: grid; gap: 10px; margin-top: 10px; }
.recommendation-card { padding: 11px; border: 1px solid #e0e8e3; border-radius: 6px; background: #fff; transition: border-color .2s, box-shadow .2s; }
.recommendation-card.selected { border-color: #2f8f80; box-shadow: 0 0 0 2px rgba(47,143,128,.12); }
.recommendation-heading { display: grid; grid-template-columns: auto 1fr auto; align-items: start; gap: 8px; }
.recommendation-heading strong, .recommendation-heading small { display: block; }
.recommendation-heading strong { color: #2f4d49; font-size: 11px; }
.recommendation-heading small { margin-top: 3px; color: #8b9995; font-size: 9px; }
.recommendation-heading button { padding: 4px 6px; border: 1px solid #c9ddd4; border-radius: 3px; background: #f3f8f5; color: #39786c; font-size: 9px; }
.recommendation-card > p { margin: 8px 0; color: #71817d; font-size: 10px; line-height: 1.55; }
.priority { height: auto; padding: 3px 5px; border-radius: 2px; color: #fff; font-size: 8px; white-space: nowrap; }
.priority.high { background: #c65b45; }
.priority.medium { background: #c6963e; }
.recommendation-evidence { display: grid; gap: 7px; margin: 0; }
.recommendation-evidence div { padding-top: 7px; border-top: 1px solid #edf1ee; }
.recommendation-evidence dt { color: #4d786f; font-size: 9px; font-weight: 700; }
.recommendation-evidence dd { margin: 3px 0 0; color: #7d8c88; font-size: 9px; line-height: 1.5; }
.candidate-list { display: grid; gap: 6px; margin-top: 9px; }
.candidate-list button { display: grid; grid-template-columns: auto 1fr; gap: 2px 6px; padding: 7px 8px; border: 1px dashed #b9d3c8; border-radius: 4px; background: #f5faf7; text-align: left; }
.candidate-list span { grid-row: span 2; align-self: center; padding: 3px 5px; border-radius: 9px; background: #dceee6; color: #347465; font-size: 8px; }
.candidate-list strong { color: #31564f; font-size: 9px; }
.candidate-list small { color: #80918c; font-size: 8px; }
.candidate-list em { grid-column: 1 / -1; margin-top: 3px; color: #73847f; font-size: 8px; font-style: normal; line-height: 1.4; }
.recommendation-empty { display: flex; flex-direction: column; gap: 5px; margin-top: 10px; padding: 13px; border: 1px solid #d6e6de; border-radius: 5px; background: #f1f8f4; }
.recommendation-empty strong { color: #377364; font-size: 11px; }
.recommendation-empty span { color: #71857f; font-size: 9px; line-height: 1.5; }
</style>
