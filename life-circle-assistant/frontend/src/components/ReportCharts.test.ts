// @vitest-environment jsdom
import { readFileSync } from 'node:fs'
import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Report } from '../types/report'
import ReportCharts from './ReportCharts.vue'

const mocks = vi.hoisted(() => ({ init: vi.fn(), resize: vi.fn(), setOption: vi.fn(), dispose: vi.fn(), disconnect: vi.fn() }))
vi.mock('../utils/chartRuntime', () => ({ init: mocks.init }))
const fixture: Report = JSON.parse(readFileSync('../docs/validation/reports/hongshan-haiyundonglu-20260921.json', 'utf8'))
let resizeCallback: () => void
beforeEach(() => {
  vi.clearAllMocks()
  document.documentElement.dataset.theme = 'light'
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(280)
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(248)
  vi.stubGlobal('ResizeObserver', class {
    constructor(callback: () => void) { resizeCallback = callback }
    observe() {}
    unobserve() {}
    disconnect = mocks.disconnect
  })
  mocks.init.mockImplementation((host: HTMLElement) => ({ getDom: () => host, resize: mocks.resize, setOption: mocks.setOption, dispose: mocks.dispose }))
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })
describe('报告图表切换和生命周期', () => {
  it('隐藏时不初始化，显示、尺寸和主题变化后更新，卸载销毁图表', async () => {
    const wrapper = mount(ReportCharts, { props: { scores: fixture.category_scores, visible: false } })
    await flushPromises()
    expect(mocks.init).not.toHaveBeenCalled()
    await wrapper.setProps({ visible: true })
    await flushPromises()
    expect(mocks.init).toHaveBeenCalledTimes(1)
    resizeCallback()
    await flushPromises()
    expect(mocks.resize).toHaveBeenCalledTimes(2)
    document.documentElement.dataset.theme = 'dark'
    window.dispatchEvent(new Event('life-circle:theme'))
    await flushPromises()
    expect(mocks.setOption.mock.lastCall?.[0].tooltip.backgroundColor).toBe('#101f2d')
    wrapper.unmount()
    expect(mocks.dispose).toHaveBeenCalledTimes(1)
    expect(mocks.disconnect).toHaveBeenCalledTimes(1)
  })
  it('三种图表切换使用当前报告数据，更新报告后重新绘制', async () => {
    const wrapper = mount(ReportCharts, { props: { scores: fixture.category_scores, visible: true } })
    await flushPromises()
    for (const [index, type] of [[1, 'radar'], [2, 'heatmap']] as const) {
      await wrapper.findAll('.chart-switch button')[index].trigger('click')
      await flushPromises()
      expect(mocks.setOption.mock.lastCall?.[0].series[0].type).toBe(type)
    }
    const scores = structuredClone(fixture.category_scores.slice(0, 1))
    scores[0].components[0].score = null
    await wrapper.setProps({ scores })
    await flushPromises()
    expect(mocks.setOption.mock.lastCall?.[0].series[0].data).toHaveLength(3)
    expect(mocks.setOption.mock.lastCall?.[0].series[0].data[0].value[2]).toBe(-1)
    wrapper.unmount()
  })
  it('少于三类评分或无数据时明确提示，数据表保留零分和缺失状态', async () => {
    const scores = structuredClone(fixture.category_scores.slice(0, 2))
    scores[0].score = null
    scores[1].score = 0
    const wrapper = mount(ReportCharts, { props: { scores, visible: true } })
    await flushPromises()
    await wrapper.findAll('.chart-switch button')[1].trigger('click')
    await flushPromises()
    expect(wrapper.get('.chart-empty').text()).toContain('当前为 1 类')
    expect(wrapper.get('.chart-data tbody').text()).toContain('无数据')
    expect(wrapper.get('.chart-data tbody').text()).toContain('0')
    await wrapper.setProps({ scores: [] })
    expect(wrapper.get('.chart-empty').text()).toContain('暂无设施评分数据')
    wrapper.unmount()
  })
})
