<template>
  <aside class="report-panel" aria-labelledby="report-panel-title">
    <div class="mobile-panel-heading">
      <div><div class="eyebrow">社区体检报告</div><strong>{{ report ? '查看完整报告' : '等待分析结果' }}</strong></div>
      <button class="mobile-panel-close" type="button" aria-label="关闭体检报告面板并返回地图" @click="emit('close-mobile')">×</button>
    </div>
    <div class="report-heading"><div><div class="eyebrow">社区体检报告</div><h2 id="report-panel-title">{{ report?.center.address || '分析报告' }}</h2></div></div>
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
      <ReportExportMenu :report-id="report.report_id" />
    </div>
    <div v-else class="empty-report"><Warning /><strong>等待体检结果</strong><span>设置分析参数后开始生成报告</span></div>
  </aside>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { CircleCheck, TrendCharts, Warning } from '@element-plus/icons-vue'
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
}>()
const chartRef = ref<HTMLDivElement | null>(null)
const showQualityDetails = ref(false)
let chart: echarts.ECharts | null = null
const overallScore = computed(() => props.report?.summary.score ?? null)
const scoreText = computed(() => overallScore.value === null ? '—' : overallScore.value)
const scoreTone = computed(() => overallScore.value === null ? 'unavailable' : overallScore.value >= 80 ? 'good' : overallScore.value >= 60 ? 'fair' : 'risk')
const scoreRingStyle = computed(() => ({ '--score': `${(overallScore.value ?? 0) * 3.6}deg` }))

function drawChart() {
  if (!chartRef.value || !props.report) return
  chart?.dispose()
  chart = echarts.init(chartRef.value)
  chart.setOption({ grid: { top: 12, right: 12, bottom: 28, left: 32 }, xAxis: { type: 'category', data: props.report.categories.map((item) => item.label), axisLabel: { color: '#71838a', fontSize: 11 } }, yAxis: { type: 'value', max: 100, splitLine: { lineStyle: { color: '#edf0ed' } }, axisLabel: { color: '#9aa7a5' } }, series: [{ type: 'bar', barWidth: 20, data: props.report.categories.map((item) => ({ value: item.score ?? 0, itemStyle: { color: item.score === null ? '#c5cfcb' : item.color, borderRadius: [3, 3, 0, 0] } })) }] })
}

watch(() => props.report, async () => { await nextTick(); drawChart() }, { immediate: true })
onBeforeUnmount(() => chart?.dispose())
</script>
