<template>
  <section class="report-charts report-section" aria-labelledby="report-charts-title">
    <div class="section-title"><span id="report-charts-title">设施评分图表</span><small>满分 100</small></div>
    <div class="chart-switch" role="group" aria-label="选择评分图表">
      <button v-for="chart in charts" :key="chart.kind" type="button" :aria-pressed="kind === chart.kind" @click="kind = chart.kind">{{ chart.label }}</button>
    </div>
    <p class="chart-caption">{{ kind === 'bar' ? '比较各类设施的覆盖评分' : kind === 'radar' ? '查看设施覆盖是否均衡' : '比较数量、步行时间与空间分布的指标评分' }}</p>
    <div v-if="!scores.length" class="chart-empty" role="status">本报告暂无设施评分数据。</div>
    <div v-else-if="kind === 'radar' && radarScores(scores).length < 3" class="chart-empty" role="status">雷达图至少需要 3 类有效评分，当前为 {{ radarScores(scores).length }} 类。请用柱状图或热力图查看已有数据。</div>
    <div v-else ref="chartRef" class="report-chart" :style="{ height: `${chartHeight}px` }" role="img" :aria-label="chartDescription"></div>
    <p v-if="missingScores.length && kind !== 'heatmap'" class="chart-note">{{ missingScores.map(item => item.label).join('、') }}暂无评分{{ kind === 'radar' ? '，未纳入雷达图' : '' }}。</p>
    <p v-if="kind === 'heatmap'" class="chart-note">颜色越绿评分越高；灰色「—」表示无数据。</p>
    <details class="chart-data"><summary>查看图表数据</summary><table><thead><tr><th>设施</th><th v-if="kind !== 'heatmap'">评分</th><template v-else><th v-for="component in HEATMAP_COMPONENTS" :key="component.key">{{ component.label }}</th></template></tr></thead><tbody><tr v-for="item in scores" :key="item.category"><th>{{ item.label }}</th><td v-if="kind !== 'heatmap'">{{ item.score ?? '无数据' }}</td><template v-else><td v-for="component in HEATMAP_COMPONENTS" :key="component.key">{{ item.components.find(value => value.key === component.key)?.score ?? '无数据' }}</td></template></tr></tbody></table></details>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { CategoryScore } from '../types/scoring'
import type { ECharts } from '../utils/chartRuntime'
import { HEATMAP_COMPONENTS, radarScores, reportChartOption, type ReportChartKind } from '../utils/reportCharts'

const props = defineProps<{ scores: CategoryScore[]; visible: boolean }>()
const charts: { kind: ReportChartKind; label: string }[] = [{ kind: 'bar', label: '柱状图' }, { kind: 'radar', label: '雷达图' }, { kind: 'heatmap', label: '热力图' }]
const kind = ref<ReportChartKind>('bar')
const chartRef = ref<HTMLElement | null>(null)
const missingScores = computed(() => props.scores.filter(item => item.score === null))
const chartHeight = computed(() => kind.value === 'radar' ? 248 : kind.value === 'heatmap' ? Math.max(190, props.scores.length * 30 + 82) : Math.max(160, props.scores.length * 28 + 38))
const chartDescription = computed(() => `${charts.find(item => item.kind === kind.value)?.label}：${props.scores.map(item => `${item.label}${item.score === null ? '暂无评分' : `${item.score}分`}`).join('，')}`)
let instance: ECharts | null = null
let observer: ResizeObserver | null = null
let runtime: Promise<typeof import('../utils/chartRuntime')> | null = null
let renderVersion = 0
let unmounted = false
async function draw() {
  const version = ++renderVersion
  await nextTick()
  const host = chartRef.value
  if (!props.visible || !host || !host.clientWidth || !host.clientHeight) {
    if (!host) { instance?.dispose(); instance = null }
    return
  }
  runtime ||= import('../utils/chartRuntime')
  const charts = await runtime
  if (unmounted || version !== renderVersion || !props.visible || host !== chartRef.value || !host.clientWidth) return
  if (instance && instance.getDom() !== host) { instance.dispose(); instance = null }
  instance ||= charts.init(host)
  instance.resize()
  instance.setOption(reportChartOption(kind.value, props.scores, document.documentElement.dataset.theme === 'dark'), { notMerge: true })
}
watch(() => [props.scores, props.visible, kind.value], () => { void draw() }, { deep: true })
watch(chartRef, (host, previous) => { if (previous) observer?.unobserve(previous); if (host) observer?.observe(host) })
onMounted(() => {
  observer = new ResizeObserver(() => { void draw() })
  if (chartRef.value) observer.observe(chartRef.value)
  window.addEventListener('life-circle:theme', draw)
  void draw()
})
onBeforeUnmount(() => {
  unmounted = true
  renderVersion++
  observer?.disconnect()
  window.removeEventListener('life-circle:theme', draw)
  instance?.dispose()
})
</script>

<style scoped>
.section-title { font-size: 13px; }
.section-title small { font-size: 11px; color: var(--report-muted); }
.chart-switch { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 3px; background: var(--report-soft); padding: 3px; border-radius: 5px; margin-top: 10px; }
.chart-switch button { height: 28px; padding: 0; background: transparent; border-radius: 3px; color: var(--report-muted); font-size: 12px; }
.chart-switch button[aria-pressed="true"] { color: var(--report-accent); background: #fff; box-shadow: 0 1px 4px #183d4514; font-weight: 700; }
:global(html[data-theme="dark"] .chart-switch button[aria-pressed="true"]) { background: #263f4b; }
.chart-switch button:focus-visible { outline: 2px solid var(--report-accent); }
.chart-caption, .chart-note { color: var(--report-muted); font-size: 11px; line-height: 1.6; margin: 8px 0; }
.report-chart { width: 100%; }
.chart-empty { padding: 24px 8px; color: var(--report-muted); font-size: 12px; line-height: 1.6; text-align: center; }
.chart-data { margin-top: 8px; font-size: 11px; color: var(--report-muted); }
.chart-data summary { cursor: pointer; padding: 4px 0; }
.chart-data table { width: 100%; border-collapse: collapse; font-size: 11px; margin-top: 6px; }
.chart-data th, .chart-data td { padding: 7px 3px; border-bottom: 1px solid var(--report-line); text-align: right; font-weight: 400; }
.chart-data th:first-child { text-align: left; }
</style>
