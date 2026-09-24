// @vitest-environment jsdom
import { nextTick, ref } from 'vue'
import { shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App.vue'
import controls from './components/AnalysisControls.vue?raw'
import mapStage from './components/MapStage.vue?raw'

const styles = readFileSync(resolve(process.cwd(), 'src/styles.css'), 'utf8')

vi.mock('./composables/useAnalysisCenter', () => ({
  useAnalysisCenter: () => ({
    center: ref({ lng: 113.4872, lat: 23.1068, address: '测试中心', selectionMethod: 'default', source: 'fixture', supportStatus: 'supported' }),
    addressQuery: ref('测试中心'), candidates: ref([]), coordinateLng: ref('113.4872'), coordinateLat: ref('23.1068'),
    searching: ref(false), resolving: ref(false), error: ref(''), searchCandidates: vi.fn(), selectCandidate: vi.fn(),
    restoreCenter: vi.fn(), selectMapPoint: vi.fn(), applyCoordinateInput: vi.fn(),
  }),
}))
vi.mock('./composables/useAnalysis', () => ({
  useAnalysis: () => ({
    mode: ref('demo'), minutes: ref(15), visibleCategories: ref(['market']), showNormal: ref(false), showSparse: ref(true), showCritical: ref(true),
    loading: ref(false), progress: ref(0), report: ref(null), error: ref(''), runAnalysis: vi.fn(), toggleCategory: vi.fn(), applyReport: vi.fn(),
  }),
}))
vi.mock('./composables/useReportHistory', () => ({
  useReportHistory: () => ({ items: ref([]), total: ref(0), loading: ref(false), error: ref(''), openingReportId: ref(''), rerunningReportId: ref(''), loadHistory: vi.fn(), openHistory: vi.fn(), rerunHistory: vi.fn() }),
}))
vi.mock('./composables/useReportComparison', () => ({
  useReportComparison: () => ({ selectedReportIds: ref([]), comparison: ref(null), loading: ref(false), error: ref(''), toggleReport: vi.fn(), compareSelection: vi.fn(), closeComparison: vi.fn() }),
}))
vi.mock('./composables/useSimulation', () => ({
  useSimulation: () => ({ category: ref(''), location: ref(null), result: ref(null), loading: ref(false), picking: ref(false), error: ref(''), selectCategory: vi.fn(), beginMapPick: vi.fn(), selectMapLocation: vi.fn(), simulateCandidate: vi.fn(), run: vi.fn(), clear: vi.fn() }),
}))

describe('响应式工作台布局契约', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 390 })
  })

  it('桌面视口为全屏地图 + 悬浮可折叠参数/报告面板', () => {
    expect(styles).toMatch(/\.workspace\s*\{[^}]*position:\s*relative;[^}]*overflow:\s*hidden;/s)
    expect(styles).toMatch(/\.map-stage\s*\{[^}]*position:\s*absolute;[^}]*inset:\s*0;/s)
    expect(styles).toMatch(/\.control-panel\s*\{[^}]*position:\s*absolute;[^}]*width:\s*296px;/s)
    expect(styles).toMatch(/\.report-panel\s*\{[^}]*position:\s*absolute;[^}]*width:\s*322px;/s)
    expect(styles).toContain('.control-panel.collapsed { transform: translateX(calc(-100% - 24px)); }')
    expect(styles).toContain('.report-panel.collapsed { transform: translateX(calc(100% + 24px)); }')
    expect(styles).toContain('.mobile-panel-heading, .mobile-workspace-actions, .mobile-panel-backdrop, .mobile-legend-toggle, .mobile-map-legend { display: none; }')
  })

  it('移动视口消除页面横向溢出并以地图作为主区域', () => {
    expect(styles).toContain('@media (max-width: 820px)')
    expect(styles).toMatch(/html, body, #app\s*\{[^}]*width:\s*100%;[^}]*overflow:\s*hidden;/s)
    expect(styles).toMatch(/@media \(max-width: 820px\)[\s\S]*?\.workspace\s*\{[^}]*display:\s*block;[^}]*width:\s*100%;[^}]*overflow:\s*hidden;/)
    expect(styles).toMatch(/\.map-stage\s*\{[^}]*position:\s*absolute;[^}]*inset:\s*0;/s)
    expect(styles).toMatch(/\.control-panel, \.report-panel\s*\{[^}]*left:\s*8px;[^}]*right:\s*8px;[^}]*width:\s*auto;[^}]*overflow-x:\s*hidden;/s)
  })

  it('移动参数抽屉和独立报告面板默认收起且可显式展开', () => {
    expect(styles).toMatch(/\.control-panel, \.report-panel\s*\{[^}]*transform:\s*translateY\(calc\(100% \+ 92px\)\);[^}]*visibility:\s*hidden;/s)
    expect(styles).toMatch(/\.control-panel\.mobile-open, \.report-panel\.mobile-open\s*\{[^}]*transform:\s*translateY\(0\);[^}]*visibility:\s*visible;/s)
  })

  it('在 jsdom 中渲染移动面板状态并支持 Escape 收起', async () => {
    const wrapper = shallowMount(App, { attachTo: document.body })
    const triggers = wrapper.findAll('.mobile-workspace-actions button')
    expect(triggers).toHaveLength(2)
    expect(triggers[0].attributes('aria-expanded')).toBe('false')

    await triggers[0].trigger('click')
    await nextTick()
    expect(triggers[0].attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('#analysis-controls-panel').classes()).toContain('mobile-open')
    expect(wrapper.find('.mobile-panel-backdrop').exists()).toBe(true)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()
    expect(triggers[0].attributes('aria-expanded')).toBe('false')
    expect(wrapper.get('#analysis-controls-panel').classes()).not.toContain('mobile-open')
    expect(wrapper.find('.mobile-panel-backdrop').exists()).toBe(false)
  })

  it('主要状态、控件和地图信息提供辅助技术可识别的表达', () => {
    const wrapper = shallowMount(App)
    expect(wrapper.get('[role="status"]').attributes('aria-live')).toBe('polite')
    expect(controls).toContain(':aria-pressed="visibleCategories.includes(category)"')
    expect(controls).toContain('aria-label="使用输入的 BD-09 坐标"')
    expect(mapStage).toContain('aria-label="重新运行当前分析"')
    expect(mapStage).toContain('红色网纹与感叹号')
    expect(mapStage).toContain('黄色斜纹与三角形')
  })
})
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
