// @vitest-environment jsdom
import { defineComponent, nextTick, ref } from 'vue'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App.vue'
import controls from './components/AnalysisControls.vue?raw'
import mapStage from './components/MapStage.vue?raw'
import MapStage from './components/MapStage.vue'
import type { Report } from './types/report'

const styles = readFileSync(resolve(process.cwd(), 'src/styles.css'), 'utf8')
const fixture: Report = JSON.parse(readFileSync('../docs/validation/reports/hongshan-haiyundonglu-20260921.json', 'utf8'))
const analysisReport = ref<Report | null>(null)
const ReportPanelStub = defineComponent({ name: 'ReportPanel', props: ['planningGridId', 'selectedRecommendationId'], template: '<aside />' })

vi.mock('./composables/useAnalysisCenter', () => ({
  useAnalysisCenter: () => ({
    center: ref({ lng: 113.4872, lat: 23.1068, address: '测试中心', selectionMethod: 'default', source: 'fixture', supportStatus: 'supported' }),
    addressQuery: ref('测试中心'), candidates: ref([]), coordinateLng: ref('113.4872'), coordinateLat: ref('23.1068'),
    coordinateSystem: ref('bd09'), coordinateConversionNote: ref(''),
    searching: ref(false), resolving: ref(false), error: ref(''), locationPending: ref(false), updateAddressQuery: vi.fn(), requireLocation: vi.fn(), searchCandidates: vi.fn(), selectCandidate: vi.fn(),
    restoreCenter: vi.fn(), selectMapPoint: vi.fn(), applyCoordinateInput: vi.fn(),
  }),
}))
vi.mock('./composables/useAnalysis', () => ({
  useAnalysis: () => ({
    mode: ref('demo'), minutes: ref(15), analysisCategories: ref(['market']), visibleCategories: ref(['market']), showNormal: ref(false), showSparse: ref(true), showCritical: ref(true),
    loading: ref(false), progress: ref(0), report: analysisReport, error: ref(''), runAnalysis: vi.fn(), supplementCategories: ref([]), setVisibleCategories: vi.fn(), setAnalysisCategories: vi.fn(), applyReport: vi.fn(),
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
    analysisReport.value = null
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 390 })
  })

  it('桌面视口为全屏地图 + 顶部按钮控制的悬浮参数/报告面板', () => {
    expect(styles).toMatch(/\.workspace\s*\{[^}]*position:\s*relative;[^}]*overflow:\s*hidden;/s)
    expect(styles).toMatch(/\.map-stage\s*\{[^}]*position:\s*absolute;[^}]*inset:\s*0;/s)
    expect(styles).toContain('.map-toolbar .map-caption { position: relative;')
    expect(styles).toContain('background: transparent; border: 0; border-right: 1px solid #d4e0da;')
    expect(styles).toContain('.map-toolbar .map-caption::before { content:')
    expect(styles).toContain('.map-toolbar .layer-status { flex: 1 1 auto; min-width: 0; overflow: hidden; }')
    expect(styles).toContain('.map-top-right .service-area-dock { position: relative; left: auto; right: auto; top: auto; bottom: auto; width: max-content; max-width: min(260px, 100%); }')
    expect(styles).toMatch(/\.service-area-trigger\s*\{[^}]*width:\s*max-content;[^}]*height:\s*31px;[^}]*min-height:\s*31px;/s)
    expect(styles).toContain('.service-area-menu { position: absolute; left: 0; top: calc(100% + 8px); width: min(350px, calc(100vw - var(--hud-left) - 24px));')
    expect(styles).toContain('.service-area-evidence { position: absolute; left: 0; top: calc(100% + 8px); width: min(350px, calc(100vw - var(--hud-left) - 24px));')
    expect(styles).toContain('.service-area-menu, .service-area-evidence { width: 100%; }')
    expect(styles).toMatch(/\.facility-legend\s*\{[^}]*height:\s*31px;[^}]*align-items:\s*center;/s)
    expect(styles).toContain('--map-hud-background: rgba(24,40,56,.9);')
    expect(styles).toContain('html[data-theme="dark"] .map-toolbar,\nhtml[data-theme="dark"] .facility-legend,\nhtml[data-theme="dark"] .service-area-trigger { background: var(--map-hud-background);')
    expect(styles).toContain('--panel-background: rgba(24,40,56,.9); background: var(--panel-background);')
    expect(styles).toContain('html[data-theme="dark"] .analysis-footer { background: transparent; border-top-color: rgba(126,214,199,.16); }')
    expect(styles).toMatch(/html\[data-theme="dark"\] \.service-area-menu \{ background: rgba\(24,40,56,\.97\);/)
    expect(styles).toMatch(/\.workspace\.report-active\s*\{[^}]*--hud-left:\s*calc\(var\(--report-panel-width\) \+ 32px\);[^}]*--hud-right:\s*20px;/s)
    expect(styles).not.toContain('.workspace.report-active .map-stage')
    expect(styles).toMatch(/\.control-panel\s*\{[^}]*position:\s*absolute;[^}]*width:\s*296px;/s)
    expect(styles).toMatch(/\.report-panel\s*\{[^}]*position:\s*absolute;[^}]*left:\s*16px;[^}]*right:\s*auto;[^}]*width:\s*322px;/s)
    expect(styles).toContain('.control-panel,\n.report-panel { transition: opacity .12s ease, visibility .12s ease; }')
    expect(styles).toContain('.control-panel.collapsed,\n.report-panel.collapsed { transform: none; opacity: 0; visibility: hidden; pointer-events: none; }')
    expect(styles).not.toContain('.workspace.report-active .report-panel')
    expect(styles).not.toContain('.panel-rail')
    expect(styles).not.toContain('.panel-bulk-toggle')
    expect(styles).toContain('.mobile-panel-heading, .mobile-workspace-actions, .mobile-panel-backdrop, .mobile-legend-toggle, .mobile-map-legend { display: none; }')
  })

  it('原生地图控件复用主题配色，保留滑杆动态尺寸和独立比例尺', () => {
    expect(styles).toMatch(/\.map-container\s*\{[^}]*--map-control-background:\s*rgba\(249,252,248,\.96\);[^}]*--map-control-accent:\s*#2f8f80;/s)
    expect(styles).toMatch(/html\[data-theme="dark"\] \.map-container\s*\{[^}]*--map-control-background:\s*var\(--map-hud-background\);[^}]*--map-control-border:\s*var\(--map-hud-border\);[^}]*--map-control-accent:\s*#2ee6c5;/s)
    expect(styles).toContain('.map-container .BMap_stdMpCtrl .BMap_button:hover,')
    expect(styles).toContain('.map-container .BMap_stdMpCtrl .BMap_button:focus-visible')
    expect(styles).toMatch(/\.map-container \.BMap_stdMpCtrl::before\s*\{[^}]*pointer-events:\s*none;/s)
    for (const selector of ['BMap_stdMpSliderBgTop', 'BMap_stdMpSliderBgBot', 'BMap_stdMpSliderBar']) {
      const rule = styles.match(new RegExp(`\\.map-container \\.${selector}\\s*\\{([^}]*)\\}`))?.[1]
      expect(rule).toBeDefined()
      expect(rule).toContain('var(--map-control-')
      expect(rule).not.toMatch(/(?:^|;)\s*(?:height|width|top|left):/)
    }
    expect(styles).toContain('.map-container .BMap_scaleCtrl { left: var(--hud-left) !important;')
    expect(styles).toContain('.map-container .BMap_scaleTxt { color: var(--map-control-text) !important;')
    expect(styles).toContain('.map-container .BMap_scaleBar { background: var(--map-control-text) !important; }')
    expect(styles).toContain('.has-conversation .map-container .BMap_scaleCtrl { bottom: calc(var(--conversation-height, 0px) + 92px + env(safe-area-inset-bottom)) !important; }')
    expect(styles).not.toMatch(/\.map-container \.BMap_cpyCtrl\s*\{/)
    expect(mapStage).toContain('<div v-if="!realMapReady" class="map-scale">')
  })

  it('移动视口消除页面横向溢出并以地图作为主区域', () => {
    expect(styles).toContain('@media (max-width: 820px)')
    expect(styles).toMatch(/html, body, #app\s*\{[^}]*width:\s*100%;[^}]*overflow:\s*hidden;/s)
    expect(styles).toMatch(/@media \(max-width: 820px\)[\s\S]*?\.workspace\s*\{[^}]*display:\s*block;[^}]*width:\s*100%;[^}]*overflow:\s*hidden;/)
    expect(styles).toMatch(/\.map-stage\s*\{[^}]*position:\s*absolute;[^}]*inset:\s*0;[^}]*min-width:\s*0;/s)
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
    expect(controls).toContain(':aria-pressed="analysisCategories.includes(category)"')
    expect(controls).toContain('aria-label="输入坐标系"')
    expect(controls).toContain('使用输入的 ${coordinateSystemLabel} 坐标')
    expect(mapStage).toContain('<MapLayerControls')
    expect(styles).toMatch(/\.controls-scroll\s*\{[^}]*min-height:\s*0;[^}]*overflow-y:\s*auto;/s)
    expect(styles).toMatch(/\.analysis-footer\s*\{[^}]*flex:\s*0 0 auto;/s)
    expect(mapStage).toContain('红色网纹与感叹号')
    expect(mapStage).toContain('黄色斜纹与三角形')
  })

  for (const mobile of [true, false]) {
    it(`${mobile ? '手机' : '桌面'}查看区域保留报告开合状态，并继续关联报告建议和规划区域`, async () => {
      Object.defineProperty(window, 'innerWidth', { configurable: true, value: mobile ? 390 : 1440 })
      analysisReport.value = structuredClone(fixture)
      const wrapper = shallowMount(App, { global: { stubs: { ReportPanel: ReportPanelStub } } })
      await flushPromises()
      const report = wrapper.getComponent({ name: 'ReportPanel' })
      const recommendation = fixture.recommendations[0]!
      const gridId = recommendation.target_region_ids[0]!
      const map = wrapper.getComponent(MapStage)
      map.vm.$emit('service-area-select', gridId)
      await nextTick()
      expect(map.props('focusRecommendationId')).toBe(recommendation.id)
      expect(report.props('planningGridId')).toBe(gridId)
      expect(wrapper.find('.mobile-panel-backdrop').exists()).toBe(false)
      map.vm.$emit('service-area-select', null)
      await nextTick()
      expect(map.props('focusRecommendationId')).toBeNull()
      expect(report.props('planningGridId')).toBeNull()
      wrapper.unmount()
    })
  }
})
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
