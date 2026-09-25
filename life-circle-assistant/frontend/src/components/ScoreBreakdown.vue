<template>
  <div class="score-breakdown">
    <details v-for="category in scores" :key="category.category" class="score-category">
      <summary>
        <span class="score-category-name">
          <i :style="{ background: category.color }"></i>
          {{ category.label }}
        </span>
        <span :class="['score-status', category.status]">{{ category.status_label }}</span>
        <strong>{{ category.score === null ? '不计分' : `${category.score} 分` }}</strong>
      </summary>
      <div class="score-category-body">
        <p>{{ category.status_explanation }}</p>
        <div class="component-list">
          <div v-for="component in category.components" :key="component.key" class="score-component">
            <div class="component-heading">
              <strong>{{ component.label }}</strong>
              <span>权重 {{ component.weight_percent }}%</span>
              <b>{{ component.score === null ? '—' : `${component.score} 分` }}</b>
            </div>
            <div class="component-meter" aria-hidden="true">
              <span :style="{ width: `${component.score ?? 0}%`, background: category.color }"></span>
            </div>
            <p>{{ component.reason }}</p>
          </div>
        </div>
        <div class="category-weight">
          <span>类别配置权重 {{ percent(category.configured_weight) }}</span>
          <strong v-if="category.valid_for_overall">综合分实际权重 {{ percent(category.applied_weight) }}</strong>
          <strong v-else>未纳入综合分</strong>
        </div>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import type { CategoryScore } from '../types/scoring'

defineProps<{ scores: CategoryScore[] }>()

function percent(value: number) {
  return `${Math.round(value * 100)}%`
}
</script>

<style scoped>
.score-breakdown { display: grid; gap: 7px; margin-top: 10px; }
.score-category { border: 1px solid #dce6e0; border-radius: 5px; background: #fbfcfa; }
.score-category summary { min-height: 38px; display: grid; grid-template-columns: minmax(80px, 1fr) auto auto; align-items: center; gap: 7px; padding: 8px 9px; cursor: pointer; list-style-position: inside; color: #45635d; font-size: 10px; }
.score-category summary::marker { color: #78908a; }
.score-category-name { display: inline-flex; align-items: center; gap: 6px; font-weight: 700; }
.score-category-name i { width: 8px; height: 8px; flex: 0 0 auto; border-radius: 50%; }
.score-category summary > strong { color: #294d46; font-size: 10px; white-space: nowrap; }
.score-status { padding: 2px 5px; border-radius: 8px; background: #e5f1eb; color: #397662; font-size: 8px; white-space: nowrap; }
.score-status.poor_coverage { background: #f4dfd9; color: #a14e3b; }
.score-status.calculation_incomplete, .score-status.data_unavailable { background: #f5ead3; color: #946b29; }
.score-category-body { padding: 0 10px 10px; border-top: 1px solid #e5ebe7; }
.score-category-body > p { margin: 8px 0; color: #71827e; font-size: 9px; line-height: 1.55; }
.component-list { display: grid; gap: 8px; }
.score-component { padding: 7px; border-radius: 4px; background: #f3f7f4; }
.component-heading { display: flex; align-items: center; gap: 6px; font-size: 9px; }
.component-heading strong { color: #3f5d56; }
.component-heading span { color: #899793; }
.component-heading b { margin-left: auto; color: #526d66; }
.component-meter { height: 3px; margin-top: 6px; overflow: hidden; border-radius: 2px; background: #dfe8e3; }
.component-meter span { display: block; height: 100%; border-radius: inherit; }
.score-component p { margin: 6px 0 0; color: #788985; font-size: 9px; line-height: 1.5; }
.category-weight { display: flex; justify-content: space-between; gap: 8px; margin-top: 9px; color: #85938f; font-size: 8px; }
.category-weight strong { color: #56756d; }
html[data-theme="dark"] .score-category { border-color: rgba(126,214,199,.16); background: rgba(16,32,46,.6); }
html[data-theme="dark"] .score-category summary { color: #cfe7e1; }
html[data-theme="dark"] .score-category summary::marker { color: #6f8b90; }
html[data-theme="dark"] .score-category summary > strong { color: #eaf6f3; }
html[data-theme="dark"] .score-status { background: rgba(52,224,180,.16); color: #7ff0da; }
html[data-theme="dark"] .score-status.poor_coverage { background: rgba(255,107,87,.16); color: #ff9d8d; }
html[data-theme="dark"] .score-status.calculation_incomplete, html[data-theme="dark"] .score-status.data_unavailable { background: rgba(255,181,71,.16); color: #ffcf8a; }
html[data-theme="dark"] .score-category-body { border-top-color: rgba(126,214,199,.1); }
html[data-theme="dark"] .score-category-body > p { color: #9db8b8; }
html[data-theme="dark"] .score-component { background: rgba(9,18,27,.6); }
html[data-theme="dark"] .component-heading strong { color: #cfe7e1; }
html[data-theme="dark"] .component-heading span { color: #6f8b90; }
html[data-theme="dark"] .component-heading b { color: #9db8b8; }
html[data-theme="dark"] .component-meter { background: rgba(126,214,199,.16); }
html[data-theme="dark"] .score-component p { color: #9db8b8; }
html[data-theme="dark"] .category-weight { color: #6f8b90; }
html[data-theme="dark"] .category-weight strong { color: #9db8b8; }
</style>
