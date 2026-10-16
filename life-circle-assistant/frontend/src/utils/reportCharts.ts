import type { EChartsOption } from 'echarts'
import type { CategoryScore, ScoreComponentKey } from '../types/scoring'

export type ReportChartKind = 'bar' | 'radar' | 'heatmap'
export const HEATMAP_COMPONENTS: { key: ScoreComponentKey; label: string }[] = [
  { key: 'quantity', label: '数量' }, { key: 'walking_time', label: '步行时间' }, { key: 'spatial_distribution', label: '空间分布' },
]
export function radarScores(scores: CategoryScore[]) { return scores.filter(item => item.score !== null) }
function escapeHtml(value: string) {
  return value.replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character] || character))
}
export function reportChartOption(kind: ReportChartKind, scores: CategoryScore[], dark: boolean): EChartsOption {
  const ink = dark ? '#cfe7e1' : '#49655d'
  const muted = dark ? '#9db8b8' : '#71838a'
  const split = dark ? 'rgba(126,214,199,.14)' : '#e3eae6'
  const accent = dark ? '#2ee6c5' : '#3e9b8b'
  const tooltip = {
    trigger: 'item' as const, confine: true,
    backgroundColor: dark ? '#101f2d' : '#ffffff', borderColor: split,
    textStyle: { color: ink, fontSize: 12 }, extraCssText: 'max-width:240px;white-space:normal;line-height:1.6;',
  }
  if (kind === 'bar') return {
    animation: false,
    grid: { top: 8, right: 35, bottom: 25, left: 65 },
    tooltip: { ...tooltip, formatter: params => {
      const item = scores[Array.isArray(params) ? params[0].dataIndex : params.dataIndex]
      return item ? `${escapeHtml(item.label)}：${item.score === null ? '暂无评分' : `${item.score} 分`}<br/>设施数量：${item.count} 个<br/>最近步行：${item.nearest_walk_minutes === null ? '未测算' : `${item.nearest_walk_minutes} 分钟`}<br/>${escapeHtml(item.status_explanation)}` : ''
    } },
    xAxis: { type: 'value', min: 0, max: 100, interval: 25, axisLabel: { color: muted, fontSize: 10 }, splitLine: { lineStyle: { color: split } } },
    yAxis: { type: 'category', inverse: true, data: scores.map(item => item.label), axisLabel: { color: ink, fontSize: 12, width: 60, overflow: 'truncate' }, axisLine: { show: false }, axisTick: { show: false } },
    series: [{ type: 'bar', barWidth: 12, showBackground: true, backgroundStyle: { color: split, borderRadius: 3 }, label: { show: true, position: 'right', color: ink, fontSize: 12 }, data: scores.map(item => ({ value: item.score ?? '-', itemStyle: { color: item.color, borderRadius: [0, 3, 3, 0] } })) }],
  }
  if (kind === 'radar') {
    const valid = radarScores(scores)
    return {
      animation: false,
      tooltip: { ...tooltip, formatter: () => valid.map(item => `${escapeHtml(item.label)}：${item.score} 分`).join('<br/>') },
      radar: { indicator: valid.map(item => ({ name: item.label, max: 100 })), radius: '60%', center: ['50%', '51%'], axisName: { color: ink, fontSize: 12 }, axisLine: { lineStyle: { color: split } }, splitLine: { lineStyle: { color: split } }, splitArea: { show: false } },
      series: valid.length < 3 ? [] : [{ type: 'radar', symbolSize: 5, data: [{ name: '类别评分', value: valid.map(item => item.score as number), lineStyle: { color: accent, width: 2 }, itemStyle: { color: accent }, areaStyle: { color: accent, opacity: .16 } }] }],
    }
  }
  return {
    animation: false,
    grid: { top: 30, right: 3, bottom: 52, left: 65 },
    tooltip: { ...tooltip, formatter: params => {
      const index = Array.isArray(params) ? params[0].dataIndex : params.dataIndex
      const item = scores[Math.floor(index / HEATMAP_COMPONENTS.length)]
      const key = HEATMAP_COMPONENTS[index % HEATMAP_COMPONENTS.length]
      const component = item?.components.find(component => component.key === key.key)
      return `${escapeHtml(item?.label || '')} · ${key.label}<br/>${component?.score == null ? '暂无数据' : `${component.score} 分 / 100`}<br/>${escapeHtml(component?.reason || '未提供该指标评分')}`
    } },
    xAxis: { type: 'category', position: 'top', data: HEATMAP_COMPONENTS.map(item => item.label), splitArea: { show: true }, axisLabel: { color: ink, fontSize: 11, interval: 0 }, axisLine: { show: false }, axisTick: { show: false } },
    yAxis: { type: 'category', inverse: true, data: scores.map(item => item.label), splitArea: { show: true }, axisLabel: { color: ink, fontSize: 12, width: 60, overflow: 'truncate' }, axisLine: { show: false }, axisTick: { show: false } },
    visualMap: { type: 'continuous', min: 0, max: 100, orient: 'horizontal', left: 'center', bottom: 0, itemWidth: 8, itemHeight: 100, text: ['高分', '低分'], textStyle: { color: muted, fontSize: 11 }, calculable: false, inRange: { color: ['#d77c69', '#e4bc67', '#72baa0', '#287b68'] } },
    series: [{ type: 'heatmap', label: { show: true, fontSize: 12, color: '#102d26', formatter: params => {
      const value = params.value as number[]
      return value[2] < 0 ? '—' : `${value[2]}`
    } }, data: scores.flatMap((item, row) => HEATMAP_COMPONENTS.map((component, column) => {
      const score = item.components.find(value => value.key === component.key)?.score ?? null
      // -1 是缺失值占位，独立灰色显示，不参与 0–100 评分色阶。
      return { value: [column, row, score ?? -1], itemStyle: { borderWidth: 2, borderColor: dark ? '#182838' : '#f8faf7', ...(score === null ? { color: dark ? '#344751' : '#e3e9e6' } : {}) }, ...(score === null ? { label: { color: muted } } : {}) }
    })) }],
  }
}
