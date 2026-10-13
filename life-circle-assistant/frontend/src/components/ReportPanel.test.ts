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
  it.each([
    { status: 'complete', label: '验证已完成' },
    { status: 'failed', label: '验证未完成' },
    { status: 'disabled', label: '验证未启用' },
  ] as const)('概览显示高德验证状态 $status，点击后直接定位详情', async ({ status, label }) => {
    const report = structuredClone(fixture)
    report.multisource_validation = { status, provider: 'amap', affects_primary_analysis: false, returned_count: 18, matched_count: 12, review_count: 2, conflict_count: 1, unmatched_count: 3 }
    const wrapper = mountPanel(report)
    const entry = wrapper.get('button.multisource-validation-entry')
    expect(entry.isVisible()).toBe(true)
    expect(entry.text()).toContain('高德辅助验证')
    expect(entry.text()).toContain(label)
    expect(wrapper.get('.multisource-validation').isVisible()).toBe(false)
    await entry.trigger('click')
    await flushPromises()
    const details = wrapper.get('.multisource-validation')
    expect(details.isVisible()).toBe(true)
    expect(details.text()).toContain(label)
    expect(document.activeElement).toBe(details.element)
    expect(HTMLElement.prototype.scrollIntoView).toHaveBeenLastCalledWith({ block: 'start' })
    expect(wrapper.get('#report-page-overview').isVisible()).toBe(false)
    expect(wrapper.emitted('toggle-collapse')).toBeUndefined()
    if (status === 'complete') {
      expect(details.get('.multisource-validation-metrics').text()).toBe('12匹配2待复核1冲突3未匹配')
    } else {
      expect(details.find('.multisource-validation-metrics').exists()).toBe(false)
    }
    await wrapper.get('.auxiliary-heading button').trigger('click')
    expect(entry.isVisible()).toBe(true)
    wrapper.unmount()
  })
  it('旧报告仍有验证状态与详情说明，换报告后状态同步更新', async () => {
    const report = structuredClone(fixture)
    delete report.multisource_validation
    const wrapper = mountPanel(report)
    expect(wrapper.get('.multisource-validation-entry').text()).toContain('本报告未进行辅助验证')
    await wrapper.get('.multisource-validation-entry').trigger('click')
    await flushPromises()
    const details = wrapper.get('.multisource-validation')
    expect(details.isVisible()).toBe(true)
    expect(details.text()).toContain('本报告未进行辅助验证')
    expect(details.find('.multisource-validation-metrics').exists()).toBe(false)
    await wrapper.setProps({ report: { ...report, report_id: 'verified-report', multisource_validation: { status: 'complete', provider: 'amap', affects_primary_analysis: false } } })
    expect(wrapper.get('.multisource-validation-entry').isVisible()).toBe(true)
    expect(wrapper.get('.multisource-validation-entry').text()).toContain('验证已完成')
    expect(wrapper.get('.multisource-validation-entry').text()).not.toContain('本报告未进行辅助验证')
    wrapper.unmount()
  })
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
