import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import type { Report } from '../types/report'
import { radarScores, reportChartOption } from './reportCharts'

const report: Report = JSON.parse(readFileSync(new URL('../../../docs/validation/reports/hongshan-haiyundonglu-20260921.json', import.meta.url), 'utf8'))
describe('报告图表数据真实性', () => {
  it('柱状图区分真实零分与缺失评分', () => {
    const scores = structuredClone(report.category_scores)
    scores[0].score = null
    scores[1].score = 0
    const option = reportChartOption('bar', scores, false)
    expect(option.series).toEqual([expect.objectContaining({ data: expect.arrayContaining([
      expect.objectContaining({ value: '-' }), expect.objectContaining({ value: 0 }),
    ]) })])
  })
  it('雷达图不把缺失评分补成零分，少于三类不伪造多边形', () => {
    const scores = structuredClone(report.category_scores)
    scores[0].score = null
    expect(radarScores(scores)).toHaveLength(scores.length - 1)
    expect(reportChartOption('radar', scores.slice(0, 3), false).series).toEqual([])
    expect(reportChartOption('radar', scores, false).series).toEqual([expect.objectContaining({ data: [expect.objectContaining({ value: radarScores(scores).map(item => item.score) })] })])
  })
  it('热力图按指标键取原始分，缺失单元格为灰色且不属于评分色阶', () => {
    const scores = structuredClone(report.category_scores.slice(0, 1))
    scores[0].components = [scores[0].components[2], scores[0].components[0]]
    const option = reportChartOption('heatmap', scores, false)
    expect(option.visualMap).toEqual(expect.objectContaining({ min: 0, max: 100 }))
    expect(option.series).toEqual([expect.objectContaining({ data: [
      expect.objectContaining({ value: [0, 0, scores[0].components[1].score] }),
      expect.objectContaining({ value: [1, 0, -1], itemStyle: expect.objectContaining({ color: '#e3e9e6' }) }),
      expect.objectContaining({ value: [2, 0, scores[0].components[0].score] }),
    ] })])
  })
})
