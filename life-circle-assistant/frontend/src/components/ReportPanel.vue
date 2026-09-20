<template>
  <aside class="report-panel">
    <div class="report-heading"><div><div class="eyebrow">社区体检报告</div><h2>萝岗街道样例社区</h2></div><button class="download-btn" title="导出 JSON 报告" @click="emit('export')"><Download /></button></div>
    <div v-if="report" class="report-content">
      <div class="quality-banner"><CircleCheck /><span>{{ report.quality.mode }} · 置信度 {{ Math.round(report.quality.confidence * 100) }}%</span><button title="查看数据说明">i</button></div>
      <div class="score-block"><div><span class="score-label">综合生活圈指数</span><div class="score-value" :class="scoreTone">{{ report.summary.score }}<small>/100</small></div><span class="score-trend"><TrendCharts /> 基于四类核心设施</span></div><div class="score-ring" :style="{ '--score': `${report.summary.score * 3.6}deg` }"><b>{{ report.summary.score }}</b><span>健康度</span></div></div>
      <div class="stat-grid"><div><strong>{{ report.summary.poi_count }}</strong><span>设施点位</span></div><div><strong>{{ report.summary.area_sqm.toLocaleString() }}</strong><span>可达面积 m²</span></div><div class="danger"><strong>{{ report.summary.critical_zone_count }}</strong><span>重点盲区</span></div><div class="amber"><strong>{{ report.summary.sparse_zone_count }}</strong><span>设施稀疏区</span></div></div>
      <div class="report-section"><div class="section-title"><span>设施覆盖评分</span><small>满分 100</small></div><div ref="chartRef" class="chart"></div></div>
      <div class="report-section"><div class="section-title"><span>规划建议</span><small>{{ report.recommendations.length }} 项</small></div><article v-for="item in report.recommendations" :key="item.title" class="recommendation"><span :class="['priority', item.priority === '高' ? 'high' : 'medium']">{{ item.priority }}</span><div><strong>{{ item.title }}</strong><p>{{ item.body }}</p></div></article></div>
      <button class="export-action" @click="emit('export')"><Download />导出体检数据 <span>JSON</span></button>
    </div>
    <div v-else class="empty-report"><Warning /><strong>等待体检结果</strong><span>设置分析参数后开始生成报告</span></div>
  </aside>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { CircleCheck, Download, TrendCharts, Warning } from '@element-plus/icons-vue'
import type { Report } from '../types/report'

const props = defineProps<{ report: Report | null }>()
const emit = defineEmits<{ export: [] }>()
const chartRef = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null
const scoreTone = computed(() => (props.report?.summary.score || 0) >= 80 ? 'good' : (props.report?.summary.score || 0) >= 60 ? 'fair' : 'risk')

function drawChart() {
  if (!chartRef.value || !props.report) return
  chart?.dispose()
  chart = echarts.init(chartRef.value)
  chart.setOption({ grid: { top: 12, right: 12, bottom: 28, left: 32 }, xAxis: { type: 'category', data: props.report.categories.map((item) => item.label), axisLabel: { color: '#71838a', fontSize: 11 } }, yAxis: { type: 'value', max: 100, splitLine: { lineStyle: { color: '#edf0ed' } }, axisLabel: { color: '#9aa7a5' } }, series: [{ type: 'bar', barWidth: 20, data: props.report.categories.map((item) => ({ value: item.score, itemStyle: { color: item.color, borderRadius: [3, 3, 0, 0] } })) }] })
}

watch(() => props.report, async () => { await nextTick(); drawChart() }, { immediate: true })
onBeforeUnmount(() => chart?.dispose())
</script>
