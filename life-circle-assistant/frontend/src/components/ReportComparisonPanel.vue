<template>
  <Teleport to="body">
    <div class="comparison-backdrop" @click.self="emit('close')">
      <section class="comparison-panel" role="dialog" aria-modal="true" aria-labelledby="comparison-title">
        <header class="comparison-header">
          <div>
            <div class="eyebrow">报告对比</div>
            <h2 id="comparison-title">两份体检报告差异</h2>
          </div>
          <button class="comparison-close" aria-label="关闭报告比较" @click="emit('close')">×</button>
        </header>

        <div class="comparison-report-grid">
          <article v-for="(item, index) in comparison.reports" :key="item.report_id" class="comparison-report-card">
            <span>{{ index === 0 ? '报告 A' : '报告 B' }} · {{ item.completeness === 'partial' ? '部分报告' : '完整报告' }}</span>
            <strong>{{ item.center.address }}</strong>
            <small>{{ formatTime(item.completed_at) }}</small>
            <button @click="emit('open-report', item.report_id)">返回原报告</button>
          </article>
        </div>

        <section class="comparison-section" aria-labelledby="parameter-title">
          <h3 id="parameter-title">参数与时间差异</h3>
          <div class="comparison-parameter-list">
            <div v-for="item in comparison.parameter_differences" :key="item.field" :class="{ changed: item.changed }">
              <span>{{ item.label }}</span>
              <b>{{ formatParameter(item.field, item.left) }}</b>
              <i>{{ item.changed ? '→' : '=' }}</i>
              <b>{{ formatParameter(item.field, item.right) }}</b>
            </div>
          </div>
        </section>

        <section class="comparison-section" aria-labelledby="summary-title">
          <h3 id="summary-title">核心指标变化</h3>
          <div class="comparison-summary-grid">
            <article v-for="metric in summaryMetrics" :key="metric.label" :class="{ incomparable: !metric.value.comparable }">
              <span>{{ metric.label }}</span>
              <strong>{{ formatMetric(metric.value.left, metric.unit) }} → {{ formatMetric(metric.value.right, metric.unit) }}</strong>
              <em v-if="metric.value.comparable">{{ formatDelta(metric.value.delta, metric.unit) }}</em>
              <small v-else>{{ metric.value.reason }}</small>
            </article>
          </div>
        </section>

        <section v-if="!comparison.category_scope.same_category_set || comparison.category_scope.incomparable.length" class="comparison-warning" role="note">
          <strong>不可直接比较的部分</strong>
          <p v-if="comparison.category_scope.only_left.length">仅报告 A：{{ categoryNames(comparison.category_scope.only_left) }}</p>
          <p v-if="comparison.category_scope.only_right.length">仅报告 B：{{ categoryNames(comparison.category_scope.only_right) }}</p>
          <p v-for="item in comparison.category_scope.incomparable" :key="item.category">{{ item.label }}：{{ item.reason }}</p>
        </section>

        <section class="comparison-section" aria-labelledby="category-title">
          <h3 id="category-title">类别分与服务区域</h3>
          <div class="comparison-category-list">
            <article v-for="item in comparison.categories" :key="item.category" class="comparison-category-card">
              <div class="comparison-category-heading">
                <strong>{{ item.label }}</strong>
                <span :class="{ valid: item.comparable }">{{ item.comparable ? '可比较' : '不可比较' }}</span>
              </div>
              <p v-if="!item.comparable">{{ item.reason }}</p>
              <div class="comparison-category-metrics">
                <div><span>类别分</span><b>{{ metricPair(item.score) }}</b><em>{{ item.score.comparable ? formatDelta(item.score.delta) : '—' }}</em></div>
                <div><span>设施数</span><b>{{ metricPair(item.facility_count) }}</b><em>{{ item.facility_count.comparable ? formatDelta(item.facility_count.delta, ' 个') : '—' }}</em></div>
                <div><span>正常区</span><b>{{ metricPair(item.service_area_counts.normal) }}</b><em>{{ item.service_area_counts.normal.comparable ? formatDelta(item.service_area_counts.normal.delta, ' 个') : '—' }}</em></div>
                <div><span>稀疏区</span><b>{{ metricPair(item.service_area_counts.sparse) }}</b><em>{{ item.service_area_counts.sparse.comparable ? formatDelta(item.service_area_counts.sparse.delta, ' 个') : '—' }}</em></div>
                <div><span>重点盲区</span><b>{{ metricPair(item.service_area_counts.critical) }}</b><em>{{ item.service_area_counts.critical.comparable ? formatDelta(item.service_area_counts.critical.delta, ' 个') : '—' }}</em></div>
              </div>
            </article>
          </div>
        </section>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { FACILITY_LABELS } from '../constants/facilities'
import type { ComparisonValue, ParameterDifference, ReportComparison } from '../types/comparison'

const props = defineProps<{ comparison: ReportComparison }>()
const emit = defineEmits<{ close: []; 'open-report': [reportId: string] }>()

const summaryMetrics = computed(() => [
  { label: '综合分', value: props.comparison.summary.overall_score, unit: '' },
  { label: '可达面积', value: props.comparison.summary.reachable_area_sqm, unit: ' m²' },
  { label: '民生设施数', value: props.comparison.summary.facility_count, unit: ' 个' },
  { label: '正常覆盖区', value: props.comparison.summary.service_area_counts.normal, unit: ' 个' },
  { label: '设施稀疏区', value: props.comparison.summary.service_area_counts.sparse, unit: ' 个' },
  { label: '重点服务盲区', value: props.comparison.summary.service_area_counts.critical, unit: ' 个' },
])

function formatTime(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  }).format(new Date(value))
}

function formatParameter(field: ParameterDifference['field'], value: unknown) {
  if (field === 'center' && value && typeof value === 'object') {
    const center = value as { address?: string; lng?: number; lat?: number }
    return `${center.address || '未命名'} (${center.lng ?? '—'}, ${center.lat ?? '—'})`
  }
  if (field === 'completed_at' && typeof value === 'string') return formatTime(value)
  if (field === 'minutes') return `${value} 分钟`
  if (field === 'mode') return value === 'analysis' ? '正式分析' : '快速分析'
  if (field === 'categories' && Array.isArray(value)) return categoryNames(value)
  return String(value ?? '—')
}

function categoryNames(categories: string[]) {
  return categories.map((category) => FACILITY_LABELS[category] || category).join('、') || '无'
}

function formatMetric(value: number | null, unit = '') {
  return value === null ? '—' : `${value.toLocaleString()}${unit}`
}

function formatDelta(value: number | null, unit = '') {
  if (value === null) return '不可比较'
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toLocaleString()}${unit}`
}

function metricPair(value: ComparisonValue) {
  return `${formatMetric(value.left)} → ${formatMetric(value.right)}`
}
</script>
