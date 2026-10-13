// @vitest-environment jsdom
import { readFileSync } from 'node:fs'
import { mount, flushPromises } from '@vue/test-utils'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import type { Report } from '../types/report'
import ReportPanel from './ReportPanel.vue'
import RecommendationList from './RecommendationList.vue'
import ReportHistory from './ReportHistory.vue'
import SimulationPanel from './SimulationPanel.vue'

const fixture: Report = JSON.parse(readFileSync('../docs/validation/reports/hongshan-haiyundonglu-20260921.json', 'utf8'))
beforeAll(() => {
  HTMLElement.prototype.scrollIntoView = vi.fn()
  window.matchMedia = vi.fn().mockReturnValue({ matches: false })
})
function mountPanel(report = structuredClone(fixture)) {
  return mount(ReportPanel, {
    props: { report, selectedRecommendationId: null, historyItems: [], historyTotal: 3, historyLoading: false, historyLoadingMore: false, historyHasMore: false, historyQuery: '', historyError: '', openingReportId: '', rerunningReportId: '', selectedReportIds: [], comparisonLoading: false, comparisonError: '', simulationCategory: 'school', simulationLocation: null, simulationResult: null, simulationLoading: false, simulationPicking: false, simulationError: '', mobileOpen: false },
    global: { stubs: { ReportCharts: true, AiPlanningAssistant: true, ReportExportMenu: true } },
    attachTo: document.body,
  })
}
describe('报告信息分层与联动', () => {
  it('默认展示结论，历史和技术信息按需查看，质量提示始终可见', async () => {
    const report = structuredClone(fixture)
    report.completeness = 'partial'
    const wrapper = mountPanel(report)
    expect(wrapper.get('#report-page-overview').isVisible()).toBe(true)
    expect(wrapper.get('.report-conclusion').text()).toBe(report.recommendation_summary.message)
    expect(wrapper.findComponent(ReportHistory).isVisible()).toBe(false)
    expect(wrapper.get('.execution-section').isVisible()).toBe(false)
    expect(wrapper.get('.quality-banner').text()).toContain('部分结果')
    expect(wrapper.get('.quality-banner').text()).toContain(report.data_quality.summary)
    await wrapper.get('.report-actions button:nth-child(2)').trigger('click')
    expect(wrapper.get('.execution-section').isVisible()).toBe(true)
    expect(wrapper.get('#report-page-overview').isVisible()).toBe(false)
    await wrapper.get('.report-actions button:first-child').trigger('click')
    expect(wrapper.findComponent(ReportHistory).isVisible()).toBe(true)
    wrapper.findComponent(ReportHistory).vm.$emit('search', '海韵')
    expect(wrapper.emitted('search-history')).toEqual([['海韵']])
    wrapper.unmount()
  })
  it('设施摘要可直接查看数量和步行时间，计算依据默认折叠', async () => {
    const wrapper = mountPanel()
    await wrapper.get('#report-tab-facilities').trigger('click')
    expect(wrapper.get('#report-page-facilities').isVisible()).toBe(true)
    expect(wrapper.get('.facility-metrics').text()).toContain(`${fixture.category_scores[0].count} 个设施`)
    expect(wrapper.get('.score-category').attributes('open')).toBeUndefined()
    wrapper.unmount()
  })
  it('选择地图盲区时切到对应建议、展开依据并高亮，换报告回到概览', async () => {
    const wrapper = mountPanel()
    expect(wrapper.get('.recommendation-card details').attributes('open')).toBeUndefined()
    const id = fixture.recommendations[0].id
    await wrapper.setProps({ selectedRecommendationId: id })
    await flushPromises()
    expect(wrapper.get('#report-page-recommendations').isVisible()).toBe(true)
    expect(wrapper.get('.recommendation-card.selected').attributes('id')).toBe(`recommendation-card-${id}`)
    expect(wrapper.get('.recommendation-card.selected details').attributes('open')).toBeDefined()
    expect(HTMLElement.prototype.scrollIntoView).toHaveBeenCalled()
    await wrapper.setProps({ report: { ...structuredClone(fixture), report_id: 'next-report' }, selectedRecommendationId: null })
    expect(wrapper.get('#report-page-overview').isVisible()).toBe(true)
    wrapper.unmount()
  })
  it('候选点模拟自动打开工具，助手和模拟状态在切页后保留', async () => {
    const wrapper = mountPanel()
    await wrapper.get('#report-tab-recommendations').trigger('click')
    await wrapper.get('.improvement-tools button:nth-child(2)').trigger('click')
    const assistant = wrapper.findComponent({ name: 'AiPlanningAssistant' }).vm
    await wrapper.get('#report-tab-overview').trigger('click')
    await wrapper.get('#report-tab-recommendations').trigger('click')
    expect(wrapper.findComponent({ name: 'AiPlanningAssistant' }).vm).toBe(assistant)
    const item = fixture.recommendations[0]
    wrapper.findComponent(RecommendationList).vm.$emit('simulate', item.category, item.candidate_locations[0])
    await flushPromises()
    expect(wrapper.findComponent(SimulationPanel).isVisible()).toBe(true)
    expect(wrapper.emitted('simulate-candidate')).toEqual([[item.category, item.candidate_locations[0]]])
    wrapper.unmount()
  })
  it('键盘方向键切换页面，工具入口不会触发面板收起', async () => {
    const wrapper = mountPanel()
    await wrapper.get('#report-tab-overview').trigger('keydown', { key: 'ArrowRight' })
    expect(wrapper.get('#report-tab-facilities').attributes('aria-selected')).toBe('true')
    await wrapper.get('.report-actions button:first-child').trigger('click')
    expect(wrapper.emitted('toggle-collapse')).toBeUndefined()
    wrapper.unmount()
  })
})
