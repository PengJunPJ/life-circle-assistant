<template>
  <aside class="report-panel" aria-labelledby="report-panel-title">
    <div class="mobile-panel-heading">
      <div><div class="eyebrow">社区体检报告</div><strong>{{ report ? '查看完整报告' : '等待分析结果' }}</strong></div>
      <button class="mobile-panel-close" type="button" aria-label="关闭体检报告面板并返回地图" @click="emit('close-mobile')">×</button>
    </div>
    <div class="report-heading clickable" role="presentation" @click="toggleCollapseIfDesktop"><div><div class="eyebrow">社区体检报告</div><h2 id="report-panel-title">{{ report?.center.address || '分析报告' }}</h2></div><button class="panel-collapse-btn" type="button" aria-label="收起或展开体检报告面板" @click.stop="toggleCollapseIfDesktop"><ArrowRight /></button></div>
    <ReportHistory
      :items="historyItems"
      :total="historyTotal"
      :loading="historyLoading"
      :error="historyError"
      :opening-report-id="openingReportId"
      :rerunning-report-id="rerunningReportId"
      :selected-report-ids="selectedReportIds"
      :comparison-loading="comparisonLoading"
      :comparison-error="comparisonError"
      @refresh="emit('refresh-history')"
      @open="emit('open-history', $event)"
      @rerun="emit('rerun-history', $event)"
      @toggle-comparison="emit('toggle-comparison', $event)"
      @compare="emit('compare-history')"
    />
    <div v-if="report" class="report-content">
      <div class="quality-banner" role="status">
        <CircleCheck />
        <span>{{ report.quality.mode }} · {{ report.completeness === 'partial' ? '部分结果' : '结果已完成' }}</span>
        <button
          title="查看数据说明"
          aria-controls="quality-details"
          :aria-expanded="showQualityDetails"
          @click="showQualityDetails = !showQualityDetails"
        >i</button>
      </div>
      <div v-if="showQualityDetails" id="quality-details">
        <DataQualityDetails :quality="report.data_quality" />
      </div>
      <div class="score-block"><div><span class="score-label">综合生活圈指数</span><div class="score-value" :class="scoreTone">{{ scoreText }}<small v-if="overallScore !== null">/100</small></div><span class="score-trend"><TrendCharts /> {{ report.scoring.explanation }}</span></div><div class="score-ring" :class="{ unavailable: overallScore === null }" :style="scoreRingStyle"><b>{{ scoreText }}</b><span>{{ overallScore === null ? '暂不展示' : '健康度' }}</span></div></div>
      <div class="stat-grid"><div><strong>{{ report.summary.poi_count }}</strong><span>设施点位</span></div><div><strong>{{ report.summary.area_sqm.toLocaleString() }}</strong><span>可达面积 m²</span></div><div class="danger"><strong>{{ report.summary.critical_zone_count }}</strong><span>重点盲区</span></div><div class="amber"><strong>{{ report.summary.sparse_zone_count }}</strong><span>设施稀疏区</span></div></div>
      <section class="report-section execution-section" aria-labelledby="execution-title">
        <div class="section-title"><span id="execution-title">执行指标</span><small>可复现性能观测</small></div>
        <div class="execution-metrics">
          <div><span>总耗时</span><strong>{{ formatDuration(report.execution.total_duration_ms) }}</strong></div>
          <div><span>地图 API 调用</span><strong>{{ report.execution.api_calls }}</strong></div>
          <div><span>缓存命中</span><strong>{{ report.execution.cache.hits }}<small>（{{ formatRate(report.execution.cache.hit_rate) }}）</small></strong></div>
          <div><span>缓存未命中</span><strong>{{ report.execution.cache.misses }}</strong></div>
        </div>
        <div class="stage-duration-list" aria-label="主要阶段耗时">
          <span v-for="stage in stageDurations" :key="stage.code"><b>{{ stage.label }}</b><em>{{ formatDuration(stage.duration_ms) }}</em></span>
        </div>
      </section>
      <div class="report-section"><div class="section-title"><span>设施覆盖评分</span><small>可展开核验计算过程</small></div><div ref="chartRef" class="chart"></div><ScoreBreakdown :scores="report.category_scores" /></div>
      <div class="report-section"><div class="section-title"><span>规划建议</span><small>{{ report.recommendations.length }} 项</small></div><RecommendationList :recommendations="report.recommendations" :summary="report.recommendation_summary" :selected-id="selectedRecommendationId" @locate="emit('locate-recommendation', $event)" @simulate="(category, candidate) => emit('simulate-candidate', category, candidate)" /></div>
      <div class="report-section">
        <SimulationPanel
          :report="report"
          :category="simulationCategory"
          :location="simulationLocation"
          :result="simulationResult"
          :loading="simulationLoading"
          :picking="simulationPicking"
          :error="simulationError"
          @update:category="emit('update:simulation-category', $event)"
          @pick-map="emit('pick-simulation-location')"
          @run="emit('run-simulation')"
          @clear="emit('clear-simulation')"
        />
      </div>
      <AiPlanningAssistant :report="report" />
      <ReportExportMenu :report-id="report.report_id" />
    </div>
    <div v-else class="empty-report"><Warning /><strong>等待体检结果</strong><span>设置分析参数后开始生成报告</span></div>
  </aside>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { ECharts } from '../utils/chartRuntime'
import { ArrowRight, CircleCheck, TrendCharts, Warning } from '@element-plus/icons-vue'
import type { HistoryReportItem } from '../types/history'
import type { RecommendationCandidate } from '../types/recommendations'
import type { Report } from '../types/report'
import type { SimulationLocation, SimulationResult } from '../types/simulation'
import DataQualityDetails from './DataQualityDetails.vue'
import ScoreBreakdown from './ScoreBreakdown.vue'
import ReportHistory from './ReportHistory.vue'
import RecommendationList from './RecommendationList.vue'
import SimulationPanel from './SimulationPanel.vue'
import ReportExportMenu from './ReportExportMenu.vue'
import AiPlanningAssistant from './AiPlanningAssistant.vue'

const props = defineProps<{
  report: Report | null
  selectedRecommendationId: string | null
  historyItems: HistoryReportItem[]
  historyTotal: number
  historyLoading: boolean
  historyError: string
  openingReportId: string
  rerunningReportId: string
  selectedReportIds: string[]
  comparisonLoading: boolean
  comparisonError: string
  simulationCategory: string
  simulationLocation: SimulationLocation | null
  simulationResult: SimulationResult | null
  simulationLoading: boolean
  simulationPicking: boolean
  simulationError: string
  mobileOpen: boolean
}>()
const emit = defineEmits<{
  'refresh-history': []
  'open-history': [reportId: string]
  'rerun-history': [reportId: string]
  'locate-recommendation': [recommendationId: string]
  'toggle-comparison': [reportId: string]
  'compare-history': []
  'simulate-candidate': [category: string, candidate: RecommendationCandidate]
  'update:simulation-category': [category: string]
  'pick-simulation-location': []
  'run-simulation': []
  'clear-simulation': []
  'close-mobile': []
  'toggle-collapse': []
}>()

// 标题栏整体作为折叠开关仅在桌面生效；移动端抽屉由独立关闭按钮控制。
function toggleCollapseIfDesktop() {
  if (window.matchMedia('(max-width: 820px)').matches) return
  emit('toggle-collapse')
}
const chartRef = ref<HTMLDivElement | null>(null)
const showQualityDetails = ref(false)
let chart: ECharts | null = null
type ChartRuntime = typeof import('../utils/chartRuntime')
let echartsImport: Promise<ChartRuntime> | null = null
const overallScore = computed(() => props.report?.summary.score ?? null)
const scoreText = computed(() => overallScore.value === null ? '—' : overallScore.value)
const scoreTone = computed(() => overallScore.value === null ? 'unavailable' : overallScore.value >= 80 ? 'good' : overallScore.value >= 60 ? 'fair' : 'risk')
const scoreRingStyle = computed(() => ({ '--score': `${(overallScore.value ?? 0) * 3.6}deg` }))
const stageLabels: Record<string, string> = {
  request_validation: '请求校验', facility_discovery: '设施发现', walking_calculation: '步行计算',
  region_classification: '区域分类', scoring: '评分生成', report_assembly: '报告组装',
}
const stageDurations = computed(() => Object.entries(props.report?.execution.stage_durations_ms || {})
  .map(([code, duration_ms]) => ({ code, duration_ms, label: stageLabels[code] || code })))

function formatDuration(value: number) {
  return value < 1_000 ? `${value} ms` : `${(value / 1_000).toFixed(2)} s`
}

function formatRate(value: number) {
  return `${Math.round(value * 100)}%`
}

async function drawChart() {
  if (!chartRef.value || !props.report) return
  echartsImport ||= loadChartRuntime()
  const echarts = await echartsImport
  if (!chartRef.value || !props.report) return
  const dark = document.documentElement.getAttribute('data-theme') === 'dark'
  const axis = dark ? '#9db8b8' : '#71838a'
  const axisMinor = dark ? '#6f8b90' : '#9aa7a5'
  const split = dark ? 'rgba(126,214,199,.14)' : '#edf0ed'
  const nullBar = dark ? '#3a4d59' : '#c5cfcb'
  chart?.dispose()
  chart = echarts.init(chartRef.value)
  chart.setOption({ grid: { top: 12, right: 12, bottom: 28, left: 32 }, xAxis: { type: 'category', data: props.report.categories.map((item) => item.label), axisLabel: { color: axis, fontSize: 11 } }, yAxis: { type: 'value', max: 100, splitLine: { lineStyle: { color: split } }, axisLabel: { color: axisMinor } }, series: [{ type: 'bar', barWidth: 20, data: props.report.categories.map((item) => ({ value: item.score ?? 0, itemStyle: { color: item.score === null ? nullBar : item.color, borderRadius: [3, 3, 0, 0] } })) }] })
}

async function loadChartRuntime(): Promise<ChartRuntime> {
  return import('../utils/chartRuntime')
}

watch(() => props.report, async () => { await nextTick(); await drawChart() }, { immediate: true })
onMounted(() => window.addEventListener('life-circle:theme', handleThemeChange))
onBeforeUnmount(() => { window.removeEventListener('life-circle:theme', handleThemeChange); chart?.dispose() })

function handleThemeChange() { drawChart() }
</script>

<style scoped>
.execution-section { border-top: 1px solid #e7eeea; padding-top: 11px; }
.execution-metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; }
.execution-metrics > div { padding: 7px 8px; border-radius: 4px; background: #f1f6f3; }
.execution-metrics span, .execution-metrics strong { display: block; }
.execution-metrics span { color: #81908c; font-size: 8px; }
.execution-metrics strong { margin-top: 3px; color: #315e55; font-size: 11px; }
.execution-metrics small { color: #78918a; font-size: 8px; font-weight: 500; }
.stage-duration-list { display: flex; flex-wrap: wrap; gap: 5px 10px; margin-top: 7px; }
.stage-duration-list span { display: inline-flex; gap: 4px; color: #7b8c87; font-size: 8px; }
.stage-duration-list em { color: #4d7168; font-style: normal; }
@media (max-width: 760px) { .execution-metrics { grid-template-columns: repeat(2, 1fr); } }
html[data-theme="dark"] .execution-section { border-top-color: rgba(126,214,199,.1); }
html[data-theme="dark"] .execution-metrics > div { background: rgba(9,18,27,.6); }
html[data-theme="dark"] .execution-metrics span { color: #6f8b90; }
html[data-theme="dark"] .execution-metrics strong { color: #cfe7e1; }
html[data-theme="dark"] .execution-metrics small { color: #6f8b90; }
html[data-theme="dark"] .stage-duration-list span { color: #9db8b8; }
html[data-theme="dark"] .stage-duration-list em { color: #7ff0da; }
</style>
