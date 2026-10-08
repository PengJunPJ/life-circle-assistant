// @vitest-environment jsdom
import { nextTick, ref } from 'vue'
import { shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App.vue'
import AnalysisControls from './components/AnalysisControls.vue'
import AppHeader from './components/AppHeader.vue'
import FirstUseGuide from './components/FirstUseGuide.vue'
import MapStage from './components/MapStage.vue'

const mocks = vi.hoisted(() => ({ runAnalysis: vi.fn(), loadHistory: vi.fn() }))

vi.mock('./services/analysisApi', () => ({
  fetchMapStatus: vi.fn().mockResolvedValue({ mode: 'real', provider_mode: 'real', provider: 'baidu', source: 'real_api', real_api_configured: true, real_api_probe_endpoint: '/api/map/probe', mock_available: true, snapshot_available: false, message: '已配置' }),
  probeMapApi: vi.fn().mockResolvedValue({ configured: true, verified: true, checked_at: '2026-10-08T00:00:00+00:00', message: '探测成功' }),
}))
vi.mock('./composables/useAnalysisCenter', () => ({
  useAnalysisCenter: () => ({
    center: ref({ lng: 113.4872, lat: 23.1068, address: '测试中心', selectionMethod: 'default', source: 'fixture', supportStatus: 'supported' }),
    addressQuery: ref(''), candidates: ref([]), coordinateLng: ref('113.4872'), coordinateLat: ref('23.1068'),
    coordinateSystem: ref('bd09'), coordinateConversionNote: ref(''),
    searching: ref(false), resolving: ref(false), error: ref(''), searchCandidates: vi.fn(), selectCandidate: vi.fn(),
    restoreCenter: vi.fn(), selectMapPoint: vi.fn(), applyCoordinateInput: vi.fn(),
  }),
}))
vi.mock('./composables/useAnalysis', () => ({
  useAnalysis: () => ({
    mode: ref('demo'), minutes: ref(15), visibleCategories: ref(['market']), showNormal: ref(false), showSparse: ref(true), showCritical: ref(true),
    loading: ref(false), progress: ref(0), report: ref(null), error: ref(''), runAnalysis: mocks.runAnalysis, toggleCategory: vi.fn(), applyReport: vi.fn(),
  }),
}))
vi.mock('./composables/useReportHistory', () => ({
  useReportHistory: () => ({ items: ref([]), total: ref(0), loading: ref(false), error: ref(''), openingReportId: ref(''), rerunningReportId: ref(''), loadHistory: mocks.loadHistory, openHistory: vi.fn(), rerunHistory: vi.fn() }),
}))
vi.mock('./composables/useReportComparison', () => ({
  useReportComparison: () => ({ selectedReportIds: ref([]), comparison: ref(null), loading: ref(false), error: ref(''), toggleReport: vi.fn(), compareSelection: vi.fn(), closeComparison: vi.fn() }),
}))
vi.mock('./composables/useSimulation', () => ({
  useSimulation: () => ({ category: ref(''), location: ref(null), result: ref(null), loading: ref(false), picking: ref(false), error: ref(''), selectCategory: vi.fn(), beginMapPick: vi.fn(), selectMapLocation: vi.fn(), simulateCandidate: vi.fn(), run: vi.fn(), clear: vi.fn() }),
}))

describe('真实地图分析启动方式', () => {
  beforeEach(() => {
    mocks.runAnalysis.mockReset()
    window.localStorage.setItem('life-circle:first-use-guide:v1', 'completed')
  })

  it('地图就绪时不自动消耗 API，只在用户点击后分析', async () => {
    const wrapper = shallowMount(App)
    wrapper.getComponent(MapStage).vm.$emit('map-ready', true)
    await nextTick()
    expect(mocks.runAnalysis).not.toHaveBeenCalled()

    wrapper.getComponent(AnalysisControls).vm.$emit('run')
    await nextTick()
    expect(mocks.runAnalysis).toHaveBeenCalledTimes(1)
  })

  it('用户关闭过向导后不再自动弹出，但仍可从顶部重新打开', async () => {
    vi.useFakeTimers()
    window.localStorage.setItem('life-circle:first-use-guide:v1', 'dismissed')
    const wrapper = shallowMount(App)

    await vi.advanceTimersByTimeAsync(500)
    expect(wrapper.getComponent(FirstUseGuide).props('open')).toBe(false)

    wrapper.getComponent(AppHeader).vm.$emit('open-guide')
    await nextTick()
    expect(wrapper.getComponent(FirstUseGuide).props('open')).toBe(true)
    vi.useRealTimers()
  })
})
