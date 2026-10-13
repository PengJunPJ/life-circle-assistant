<template>
  <aside class="report-panel" aria-labelledby="report-panel-title">
    <div class="mobile-panel-heading">
      <div><div class="eyebrow">社区体检报告</div><strong>{{ report ? '查看体检结果' : '等待分析结果' }}</strong></div>
      <button class="mobile-panel-close" type="button" aria-label="关闭体检报告面板并返回地图" @click="emit('close-mobile')">×</button>
    </div>
    <div class="report-heading clickable" role="presentation" @click="toggleCollapseIfDesktop">
      <div><div class="eyebrow">社区体检报告</div><h2 id="report-panel-title">{{ report?.center.address || '分析报告' }}</h2></div>
      <button class="panel-collapse-btn" type="button" aria-label="收起或展开体检报告面板" @click.stop="toggleCollapseIfDesktop"><ArrowRight /></button>
    </div>
    <nav class="report-actions" aria-label="报告工具">
      <button type="button" :aria-pressed="auxiliary === 'history'" @click="toggleAuxiliary('history')"><Clock />历史 <small>{{ historyTotal }}</small></button>
      <button type="button" :disabled="!report" :aria-pressed="auxiliary === 'details'" @click="toggleAuxiliary('details')"><InfoFilled />报告说明</button>
      <button type="button" :disabled="!report" :aria-pressed="auxiliary === 'export'" @click="toggleAuxiliary('export')"><Download />导出</button>
    </nav>
    <div v-if="report && !auxiliary" class="report-tabs" role="tablist" aria-label="体检报告内容">
      <button v-for="tab in tabs" :id="`report-tab-${tab.id}`" :key="tab.id" type="button" role="tab" :aria-selected="activeTab === tab.id" :aria-controls="`report-page-${tab.id}`" :tabindex="activeTab === tab.id ? 0 : -1" @click="selectTab(tab.id)" @keydown="handleTabKey($event, tab.id)">{{ tab.label }}</button>
    </div>
    <div ref="scrollRef" class="report-scroll">
      <div v-if="auxiliary" class="auxiliary-heading"><strong>{{ auxiliary === 'history' ? '历史与比较' : auxiliary === 'details' ? '报告说明' : '导出报告' }}</strong><button type="button" @click="auxiliary = null">{{ report ? '返回体检' : '返回' }} <ArrowRight /></button></div>
      <ReportHistory v-show="auxiliary === 'history'"
        :items="historyItems" :total="historyTotal" :loading="historyLoading" :loading-more="historyLoadingMore"
        :has-more="historyHasMore" :query="historyQuery" :error="historyError" :opening-report-id="openingReportId"
        :rerunning-report-id="rerunningReportId" :selected-report-ids="selectedReportIds"
        :comparison-loading="comparisonLoading" :comparison-error="comparisonError"
        @refresh="emit('refresh-history')" @open="emit('open-history', $event)" @rerun="emit('rerun-history', $event)"
        @toggle-comparison="emit('toggle-comparison', $event)" @compare="emit('compare-history')"
        @search="emit('search-history', $event)" @load-more="emit('load-more-history')" />
      <div v-if="report" v-show="auxiliary !== 'history'" class="report-content">
        <div class="quality-banner" :class="{ limited: dataLimited }" role="status">
          <div><Warning v-if="dataLimited" /><CircleCheck v-else /><strong>{{ report.quality.mode }} · {{ report.completeness === 'partial' ? '部分结果' : '结果已完成' }}</strong></div>
          <p v-if="dataLimited">{{ report.data_quality.summary }}</p>
          <button type="button" aria-label="查看报告数据与计算说明" @click="toggleAuxiliary('details')">查看说明</button>
        </div>
        <section v-show="!auxiliary && activeTab === 'overview'" id="report-page-overview" role="tabpanel" aria-labelledby="report-tab-overview">
          <div class="overview-score">
            <div><span class="score-label">综合生活圈指数</span><div class="score-value" :class="scoreTone">{{ scoreText }}<small v-if="overallScore !== null">/100</small></div></div>
            <div class="overview-context"><strong>{{ report.parameters.minutes }} 分钟步行</strong><span>{{ report.scoring.valid_category_count }}/{{ report.parameters.categories.length }} 类参与评分</span></div>
          </div>
          <p class="report-conclusion">{{ report.recommendation_summary.message }}</p>
          <div class="overview-stats">
            <button type="button" class="danger" @click="selectTab('recommendations')"><strong>{{ report.summary.critical_zone_count }}</strong><span>重点盲区 <ArrowRight /></span></button>
            <div class="amber"><strong>{{ report.summary.sparse_zone_count }}</strong><span>设施稀疏区</span></div>
            <div><strong>{{ report.summary.poi_count }}</strong><span>设施点位</span></div>
            <div><strong>{{ (report.summary.area_sqm / 1_000_000).toFixed(2) }}<small> km²</small></strong><span>可达面积</span></div>
          </div>
          <section v-if="priorityRecommendations.length" class="report-section priority-section" aria-labelledby="priority-title">
            <div class="section-title"><span id="priority-title">优先关注</span><button type="button" @click="selectTab('recommendations')">查看全部 {{ report.recommendations.length }} 项</button></div>
            <button v-for="item in priorityRecommendations" :key="item.id" type="button" class="priority-row" @click="locateRecommendation(item.id)"><span :class="['priority-mark', item.priority_level]">{{ item.priority }}</span><span><strong>{{ item.title }}</strong><small>{{ item.target_region_ids.length }} 个重点盲区</small></span><ArrowRight /></button>
          </section>
          <ReportCharts :scores="report.category_scores" :visible="!auxiliary && activeTab === 'overview'" />
        </section>
        <section v-show="!auxiliary && activeTab === 'facilities'" id="report-page-facilities" role="tabpanel" aria-labelledby="report-tab-facilities">
          <div class="page-heading"><strong>设施覆盖明细</strong><span>{{ report.category_scores.length }} 类设施</span></div>
          <p class="page-intro">{{ report.scoring.explanation }}</p>
          <ScoreBreakdown :scores="report.category_scores" />
        </section>
        <section v-show="!auxiliary && activeTab === 'recommendations'" id="report-page-recommendations" role="tabpanel" aria-labelledby="report-tab-recommendations">
          <div class="page-heading"><strong>改善建议</strong><span>{{ report.recommendations.length }} 项</span></div>
          <p class="page-intro">{{ report.recommendation_summary.message }}</p>
          <RecommendationList :recommendations="report.recommendations" :summary="report.recommendation_summary" :selected-id="focusedRecommendationId" :active="!auxiliary && activeTab === 'recommendations'" :simulation-disabled="simulationLoading || planningBusy" @locate="locateRecommendation" @simulate="simulateCandidate" />
          <div class="improvement-tools" aria-label="改善规划工具">
            <button type="button" :aria-expanded="openTool === 'simulation'" aria-controls="report-simulation" @click="toggleTool('simulation')"><TrendCharts />改善模拟</button>
            <button type="button" :aria-expanded="openTool === 'assistant'" aria-controls="report-assistant" @click="toggleTool('assistant')"><ChatDotRound />智能助手</button>
          </div>
          <div v-show="openTool === 'simulation'" id="report-simulation" ref="simulationRef"><SimulationPanel :report="report" :category="simulationCategory" :location="simulationLocation" :result="simulationResult" :loading="simulationLoading || planningBusy" :picking="simulationPicking" :error="simulationError" @update:category="emit('update:simulation-category', $event)" @pick-map="emit('pick-simulation-location')" @run="emit('run-simulation')" @clear="emit('clear-simulation')" /></div>
          <div v-if="assistantOpened" v-show="openTool === 'assistant'" id="report-assistant"><AiPlanningAssistant :report="report" :simulation-location="simulationLocation" :simulation-category="simulationCategory" :grid-id="planningGridId" :disabled="simulationLoading" @busy="planningBusy = $event" @simulation-result="emit('assistant-simulation', $event)" /></div>
        </section>
        <section v-show="auxiliary === 'details'" class="report-details" aria-label="报告数据与计算说明">
          <DataQualityDetails :quality="report.data_quality" />
          <section class="report-section"><div class="section-title"><span>评分说明</span></div><p class="page-intro">{{ report.scoring.explanation }}</p><p class="page-intro">{{ report.summary.score_explanation }}</p></section>
          <section v-if="report.multisource_validation" class="report-section multisource-validation" aria-labelledby="multisource-validation-title">
            <div class="section-title"><span id="multisource-validation-title">高德辅助验证</span></div>
            <div class="multisource-validation-status" :class="report.multisource_validation.status"><strong>{{ multisourceStatusLabel }}</strong><span>{{ report.multisource_validation.message || multisourceSummary }}</span></div>
            <div v-if="report.multisource_validation.status === 'complete'" class="multisource-validation-metrics"><span><b>{{ report.multisource_validation.matched_count || 0 }}</b>匹配</span><span><b>{{ report.multisource_validation.review_count || 0 }}</b>待复核</span><span><b>{{ report.multisource_validation.conflict_count || 0 }}</b>冲突</span><span><b>{{ report.multisource_validation.unmatched_count || 0 }}</b>未匹配</span></div>
          </section>
          <section class="report-section execution-section" aria-labelledby="execution-title">
            <div class="section-title"><span id="execution-title">执行与缓存指标</span></div>
            <dl class="execution-metrics"><div><dt>总耗时</dt><dd>{{ formatDuration(report.execution.total_duration_ms) }}</dd></div><div><dt>地图 API 调用</dt><dd>{{ report.execution.api_calls }}</dd></div><div><dt>缓存命中</dt><dd>{{ report.execution.cache.hits }}（{{ formatRate(report.execution.cache.hit_rate) }}）</dd></div><div><dt>缓存未命中</dt><dd>{{ report.execution.cache.misses }}</dd></div></dl>
            <div class="stage-duration-list" aria-label="主要阶段耗时"><span v-for="stage in stageDurations" :key="stage.code"><b>{{ stage.label }}</b><em>{{ formatDuration(stage.duration_ms) }}</em></span></div>
          </section>
        </section>
        <ReportExportMenu v-show="auxiliary === 'export'" :key="report.report_id" :report-id="report.report_id" />
      </div>
      <div v-else-if="!auxiliary" class="empty-report"><Warning /><strong>等待体检结果</strong><span>设置分析参数后开始生成报告</span><button type="button" @click="toggleAuxiliary('history')">查看历史报告</button></div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { ArrowRight, ChatDotRound, CircleCheck, Clock, Download, InfoFilled, TrendCharts, Warning } from '@element-plus/icons-vue'
import type { HistoryReportItem } from '../types/history'
import type { RecommendationCandidate } from '../types/recommendations'
import type { Report } from '../types/report'
import type { SimulationLocation, SimulationResult } from '../types/simulation'
import DataQualityDetails from './DataQualityDetails.vue'
import ScoreBreakdown from './ScoreBreakdown.vue'
import ReportHistory from './ReportHistory.vue'
import ReportCharts from './ReportCharts.vue'
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
  historyLoadingMore: boolean
  historyHasMore: boolean
  historyQuery: string
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
  planningGridId?: string | null
}>()
const emit = defineEmits<{
  'refresh-history': []
  'open-history': [reportId: string]
  'rerun-history': [reportId: string]
  'locate-recommendation': [recommendationId: string]
  'toggle-comparison': [reportId: string]
  'compare-history': []
  'search-history': [keyword: string]
  'load-more-history': []
  'simulate-candidate': [category: string, candidate: RecommendationCandidate]
  'update:simulation-category': [category: string]
  'pick-simulation-location': []
  'run-simulation': []
  'clear-simulation': []
  'close-mobile': []
  'toggle-collapse': []
  'assistant-simulation': [result: SimulationResult]
}>()
type ReportTab = 'overview' | 'facilities' | 'recommendations'
type Auxiliary = 'history' | 'details' | 'export'
type ImprovementTool = 'simulation' | 'assistant'
const tabs: { id: ReportTab; label: string }[] = [{ id: 'overview', label: '体检概览' }, { id: 'facilities', label: '设施详情' }, { id: 'recommendations', label: '改善建议' }]
const activeTab = ref<ReportTab>('overview')
const auxiliary = ref<Auxiliary | null>(null)
const openTool = ref<ImprovementTool | null>(null)
const assistantOpened = ref(false)
const planningBusy = ref(false)
const focusedRecommendationId = ref<string | null>(null)
const scrollRef = ref<HTMLElement | null>(null)
const simulationRef = ref<HTMLElement | null>(null)
const overallScore = computed(() => props.report?.summary.score ?? null)
const scoreText = computed(() => overallScore.value === null ? '—' : overallScore.value)
const scoreTone = computed(() => overallScore.value === null ? 'unavailable' : overallScore.value >= 80 ? 'good' : overallScore.value >= 60 ? 'fair' : 'risk')
const dataLimited = computed(() => props.report?.completeness === 'partial' || props.report?.data_quality.overall_status !== 'good')
const priorityRecommendations = computed(() => [...(props.report?.recommendations || [])].sort((a, b) => a.priority_rank - b.priority_rank).slice(0, 2))
const multisourceStatusLabel = computed(() => {
  const status = props.report?.multisource_validation?.status
  return status === 'complete' ? '验证已完成' : status === 'failed' ? '验证未完成' : '验证未启用'
})
const multisourceSummary = computed(() => {
  const validation = props.report?.multisource_validation
  if (!validation || validation.status === 'disabled') return '当前只使用百度地图生成正式体检结论。'
  if (validation.status === 'failed') return '高德请求失败，百度主分析结果仍然有效。'
  return `高德返回 ${validation.returned_count || 0} 条观察记录，未参与评分、盲区或步行计算。`
})
const stageLabels: Record<string, string> = {
  request_validation: '请求校验', facility_discovery: '设施发现', walking_calculation: '步行计算',
  region_classification: '区域分类', scoring: '评分生成', report_assembly: '报告组装',
}
const stageDurations = computed(() => Object.entries(props.report?.execution.stage_durations_ms || {})
  .map(([code, duration_ms]) => ({ code, duration_ms, label: stageLabels[code] || code })))
function formatDuration(value: number) { return value < 1_000 ? `${value} ms` : `${(value / 1_000).toFixed(2)} s` }
function formatRate(value: number) { return `${Math.round(value * 100)}%` }
function toggleCollapseIfDesktop() {
  if (window.matchMedia('(max-width: 820px)').matches) return
  emit('toggle-collapse')
}
function resetScroll() { if (scrollRef.value) scrollRef.value.scrollTop = 0 }
function selectTab(tab: ReportTab) { activeTab.value = tab; auxiliary.value = null; resetScroll() }
function toggleAuxiliary(view: Auxiliary) { auxiliary.value = auxiliary.value === view ? null : view; resetScroll() }
function handleTabKey(event: KeyboardEvent, tab: ReportTab) {
  const index = tabs.findIndex(item => item.id === tab)
  const target = event.key === 'ArrowRight' ? (index + 1) % tabs.length : event.key === 'ArrowLeft' ? (index + tabs.length - 1) % tabs.length : event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : -1
  if (target < 0) return
  event.preventDefault()
  selectTab(tabs[target].id)
  document.getElementById(`report-tab-${tabs[target].id}`)?.focus()
}
function locateRecommendation(id: string) {
  focusedRecommendationId.value = id
  selectTab('recommendations')
  emit('locate-recommendation', id)
}
function toggleTool(tool: ImprovementTool) {
  openTool.value = openTool.value === tool ? null : tool
  if (tool === 'assistant') assistantOpened.value = true
}
async function showSimulation() {
  selectTab('recommendations')
  openTool.value = 'simulation'
  await nextTick()
  simulationRef.value?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
}
function simulateCandidate(category: string, candidate: RecommendationCandidate) {
  void showSimulation()
  emit('simulate-candidate', category, candidate)
}
watch(() => props.report?.report_id, () => {
  selectTab('overview')
  openTool.value = null
  assistantOpened.value = false
  focusedRecommendationId.value = null
})
watch(() => props.selectedRecommendationId, id => {
  focusedRecommendationId.value = id
  if (id) selectTab('recommendations')
}, { immediate: true })
watch(() => [props.simulationLocation, props.simulationResult, props.simulationPicking, props.simulationError], () => {
  if (props.simulationLocation || props.simulationResult || props.simulationPicking || props.simulationError) void showSimulation()
})
</script>

<style scoped>
/* 报告容器负责信息层级和滚动；图表与明细保留各自组件样式。 */
.report-panel { --report-ink: #294d46; --report-muted: #667d75; --report-line: #dce6e0; --report-accent: #2f7d6d; --report-soft: #e9f2ec; display: flex; flex-direction: column; overflow: hidden; }
:global(html[data-theme="dark"] .report-panel) { --report-ink: #eaf6f3; --report-muted: #a7bfb9; --report-line: rgba(126,214,199,.18); --report-accent: #7ff0da; --report-soft: rgba(46,230,197,.1); }
.report-heading { flex-shrink: 0; gap: 8px; padding-bottom: 12px; }
.report-heading > div { min-width: 0; }
.report-heading h2 { font-size: 17px; line-height: 1.4; overflow-wrap: anywhere; }
.report-actions { display: flex; gap: 5px; padding: 10px 0; flex-shrink: 0; }
.report-actions button { display: inline-flex; justify-content: center; align-items: center; gap: 4px; min-height: 28px; padding: 3px 7px; border: 1px solid var(--report-line); border-radius: 5px; background: transparent; color: var(--report-muted); font-size: 12px; }
.report-actions small { font-size: 11px; }
.report-actions svg, .improvement-tools svg { width: 13px; height: 13px; flex: 0 0 auto; }
.report-actions button[aria-pressed="true"], .report-actions button:hover:not(:disabled) { background: var(--report-soft); color: var(--report-accent); }
.report-actions button:disabled { opacity: .45; cursor: not-allowed; }
button:focus-visible { outline: 2px solid var(--report-accent); outline-offset: -2px; }
.report-tabs { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); flex-shrink: 0; border-bottom: 1px solid var(--report-line); margin-bottom: 10px; }
.report-tabs button { min-height: 34px; padding: 4px 0 8px; border-bottom: 2px solid transparent; background: transparent; color: var(--report-muted); font-size: 12px; }
.report-tabs button[aria-selected="true"] { border-color: var(--report-accent); color: var(--report-accent); font-weight: 700; }
.report-scroll { min-height: 0; overflow-y: auto; overflow-x: hidden; scrollbar-width: thin; padding-right: 2px; }
.report-content { padding-bottom: 4px; }
.auxiliary-heading { display: flex; justify-content: space-between; align-items: center; margin: 3px 0 12px; color: var(--report-ink); font-size: 13px; }
.auxiliary-heading button { display: inline-flex; align-items: center; gap: 3px; background: transparent; color: var(--report-accent); font-size: 12px; }
.auxiliary-heading svg { width: 12px; }
.quality-banner { display: block; position: relative; height: auto; margin: 0 0 10px; padding: 9px 10px; font-size: 12px; border-radius: 5px; }
.quality-banner > div { display: flex; align-items: center; gap: 5px; padding-right: 56px; }
.quality-banner svg { width: 14px; height: 14px; flex-shrink: 0; }
.quality-banner strong { font-size: 11px; line-height: 1.5; }
.quality-banner p { margin: 6px 0 0; font-size: 12px; line-height: 1.55; }
.quality-banner button { position: absolute; right: 7px; top: 9px; width: auto; height: auto; border: 0; border-radius: 0; background: transparent; font-size: 11px; text-decoration: underline; text-underline-offset: 3px; }
.quality-banner.limited { color: #815b21; background: #fff1d9; }
.quality-banner.limited svg, .quality-banner.limited button { color: inherit; }
:global(html[data-theme="dark"] .quality-banner.limited) { color: #ffcf8a; background: rgba(255,181,71,.12); }
.overview-score { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 7px 0 0; }
.score-label { font-size: 12px; }
.score-value { font-size: 44px; line-height: 1.2; }
.score-value small { font-size: 12px; margin-left: 3px; }
.overview-context { display: grid; gap: 6px; color: var(--report-muted); text-align: right; font-size: 11px; }
.overview-context strong { color: var(--report-ink); font-size: 12px; }
.report-conclusion { margin: 10px 0 14px; color: var(--report-ink); font-size: 13px; line-height: 1.6; }
.overview-stats { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px 10px; padding: 12px 0; border-top: 1px solid var(--report-line); border-bottom: 1px solid var(--report-line); }
.overview-stats > * { min-width: 0; text-align: left; background: transparent; padding: 0; }
.overview-stats strong { display: block; color: var(--report-ink); font-size: 20px; font-weight: 700; }
.overview-stats strong small { font-size: 11px; font-weight: 400; }
.overview-stats span { display: flex; align-items: center; gap: 3px; color: var(--report-muted); font-size: 12px; margin-top: 2px; }
.overview-stats span svg { width: 11px; }
.overview-stats .danger strong { color: #c65b45; }
.overview-stats .amber strong { color: #af7b2d; }
:global(html[data-theme="dark"] .overview-stats .danger strong) { color: #ff9d8d; }
:global(html[data-theme="dark"] .overview-stats .amber strong) { color: #ffcf8a; }
.section-title { font-size: 13px; align-items: center; gap: 6px; }
.section-title button { background: transparent; color: var(--report-accent); font-size: 11px; padding: 0; }
.priority-row { display: flex; width: 100%; align-items: center; gap: 8px; padding: 10px 0; border-bottom: 1px solid var(--report-line); background: transparent; text-align: left; }
.priority-row > span:nth-child(2) { flex: 1; min-width: 0; }
.priority-row strong { display: block; color: var(--report-ink); font-size: 12px; line-height: 1.5; }
.priority-row small { display: block; color: var(--report-muted); font-size: 11px; margin-top: 2px; }
.priority-row > svg { width: 12px; color: var(--report-muted); flex: 0 0 auto; }
.priority-mark { display: grid; place-items: center; width: 22px; height: 22px; border-radius: 5px; color: #aa4d3a; background: #fbe8e2; font-size: 11px; }
.priority-mark.medium { color: #896326; background: #f8edd5; }
:global(html[data-theme="dark"] .priority-mark) { background: rgba(255,107,87,.14); color: #ff9d8d; }
:global(html[data-theme="dark"] .priority-mark.medium) { background: rgba(255,181,71,.12); color: #ffcf8a; }
.page-heading { display: flex; justify-content: space-between; align-items: center; color: var(--report-ink); padding-top: 8px; font-size: 13px; }
.page-heading span { color: var(--report-muted); font-size: 12px; }
.page-intro { color: var(--report-muted); font-size: 12px; line-height: 1.6; margin: 8px 0 12px; }
.improvement-tools { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--report-line); }
.improvement-tools button { display: flex; justify-content: center; align-items: center; gap: 5px; min-height: 32px; border: 1px solid var(--report-line); border-radius: 5px; color: var(--report-accent); background: transparent; font-size: 12px; }
.improvement-tools button[aria-expanded="true"] { background: var(--report-soft); border-color: var(--report-accent); }
.execution-metrics { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 12px 0; }
.execution-metrics dt { color: var(--report-muted); font-size: 11px; }
.execution-metrics dd { margin: 4px 0 0; color: var(--report-ink); font-size: 13px; }
.stage-duration-list { display: grid; gap: 8px; }
.stage-duration-list span { display: flex; justify-content: space-between; gap: 8px; color: var(--report-muted); font-size: 11px; }
.stage-duration-list em { font-style: normal; color: var(--report-ink); }
.report-details :deep(.quality-details) { margin-top: 0; }
.report-details :deep(.quality-source strong), .report-details :deep(.quality-details-heading strong) { font-size: 12px; }
.report-details :deep(.quality-source span), .report-details :deep(.quality-failures), .report-details :deep(.quality-events), .report-details :deep(.quality-details p), .report-details :deep(.quality-source em) { font-size: 11px; line-height: 1.6; }
.report-scroll :deep(.history-section) { padding-top: 0; border-bottom: 0; }
.report-scroll :deep(.history-list) { max-height: 340px; }
.report-scroll :deep(.history-open strong) { font-size: 12px; }
.report-scroll :deep(.history-open span) { font-size: 11px; line-height: 1.5; }
.report-scroll :deep(.export-menu) { margin-top: 4px; padding-top: 8px; }
.report-scroll :deep(.export-options strong) { font-size: 12px; }
.report-scroll :deep(.export-options small) { font-size: 11px; }
.empty-report button { background: var(--report-soft); color: var(--report-accent); border-radius: 5px; padding: 8px 12px; font-size: 12px; }
@media (max-width: 820px) {
  .report-panel { height: min(76dvh, 680px); }
  .mobile-panel-heading { flex-shrink: 0; }
  .report-heading { padding: 11px 0; }
  .report-heading h2 { font-size: 15px; }
  .report-actions { padding: 8px 0; }
}
</style>
