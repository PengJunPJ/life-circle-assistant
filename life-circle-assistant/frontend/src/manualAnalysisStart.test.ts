// @vitest-environment jsdom
import { nextTick } from 'vue'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App.vue'
import AnalysisControls from './components/AnalysisControls.vue'
import AppHeader from './components/AppHeader.vue'
import FirstUseGuide from './components/FirstUseGuide.vue'
import MapStage from './components/MapStage.vue'
import { createAnalysis, parseAnalysisIntent, searchAddressCandidates } from './services/analysisApi'
import type { AnalysisIntent } from './types/analysisIntent'

vi.mock('./services/analysisApi', () => ({
  fetchMapStatus: vi.fn().mockResolvedValue({ mode: 'real', provider_mode: 'real', source: 'real_api', real_api_configured: true, message: '已配置' }),
  probeMapApi: vi.fn().mockResolvedValue({ configured: true, verified: true, checked_at: '', message: '探测成功' }),
  createAnalysis: vi.fn().mockRejectedValue(new Error('测试任务未配置报告')),
  waitForAnalysis: vi.fn(), parseAnalysisIntent: vi.fn(), searchAddressCandidates: vi.fn(), reverseGeocode: vi.fn(), convertCoordinate: vi.fn(),
  fetchReportHistory: vi.fn().mockResolvedValue({ items: [], total: 0 }),
}))
vi.mock('element-plus/es/components/message/index', () => ({ default: { success: vi.fn(), error: vi.fn() } }))
const intent: AnalysisIntent = { draft: { address: '', use_current_center: true, minutes: 20, mode: 'analysis', categories: ['market', 'pharmacy'], defaulted_fields: [] }, parser: 'rules', model: null, message: '已填入', missing_fields: [] }

describe('公共参数与显式启动', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: false }))
    window.localStorage.setItem('life-circle:first-use-guide:v1', 'completed')
  })
  afterEach(() => { vi.unstubAllGlobals() })
  it('顶部工作台默认打开智能体检，点击当前按钮可关闭并可切换报告', async () => {
    const wrapper = shallowMount(App)
    const header = wrapper.getComponent(AppHeader)
    expect(header.props('activeWorkbench')).toBe('controls')
    header.vm.$emit('toggle-workbench', 'report')
    await nextTick()
    expect(header.props('activeWorkbench')).toBe('report')
    header.vm.$emit('toggle-workbench', 'report')
    await nextTick()
    expect(header.props('activeWorkbench')).toBe(null)
    wrapper.unmount()
  })

  it('地图就绪与一句话填参均不启动，底部点击后使用修改过的公共参数', async () => {
    const wrapper = shallowMount(App)
    wrapper.getComponent(MapStage).vm.$emit('map-ready', true)
    wrapper.getComponent(AnalysisControls).vm.$emit('fill-intent', intent)
    await nextTick()
    expect(createAnalysis).not.toHaveBeenCalled()
    expect(wrapper.getComponent(AnalysisControls).props()).toMatchObject({ minutes: 20, mode: 'analysis', analysisCategories: ['market', 'pharmacy'] })
    wrapper.getComponent(AnalysisControls).vm.$emit('update:minutes', 10)
    wrapper.getComponent(AnalysisControls).vm.$emit('run')
    await flushPromises()
    expect(createAnalysis).toHaveBeenCalledWith(expect.objectContaining({ minutes: 10, mode: 'analysis', categories: ['market', 'pharmacy'] }))
    expect(parseAnalysisIntent).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('一句话地址的多个候选在公共位置区确认，未确认时不能使用旧地址', async () => {
    const candidates = [{ lng: 113.501, lat: 23.11, address: '候选一', source: 'real_api', provider: 'baidu' }, { lng: 113.502, lat: 23.12, address: '候选二', source: 'real_api', provider: 'baidu' }]
    vi.mocked(searchAddressCandidates).mockResolvedValue(candidates)
    const wrapper = shallowMount(App)
    wrapper.getComponent(AnalysisControls).vm.$emit('fill-intent', { ...intent, draft: { ...intent.draft, address: '同名社区', use_current_center: false } })
    await flushPromises()
    expect(wrapper.getComponent(AnalysisControls).props('candidates')).toEqual(candidates)
    expect(wrapper.getComponent(AnalysisControls).props('locationPending')).toBe(true)
    wrapper.getComponent(AnalysisControls).vm.$emit('run')
    await flushPromises()
    expect(createAnalysis).not.toHaveBeenCalled()
    wrapper.getComponent(AnalysisControls).vm.$emit('select-candidate', candidates[1])
    await nextTick()
    wrapper.getComponent(AnalysisControls).vm.$emit('run')
    await flushPromises()
    expect(createAnalysis).toHaveBeenCalledWith(expect.objectContaining({ lng: 113.502, lat: 23.12, center_address: '候选二', minutes: 20 }))
    wrapper.unmount()
  })
  it('不支持的时间必须在公共表单修正后才能启动', async () => {
    const wrapper = shallowMount(App)
    wrapper.getComponent(AnalysisControls).vm.$emit('fill-intent', { ...intent, draft: { ...intent.draft, minutes: null } })
    await nextTick()
    expect(wrapper.getComponent(AnalysisControls).props('minutesValid')).toBe(false)
    wrapper.getComponent(AnalysisControls).vm.$emit('run')
    expect(createAnalysis).not.toHaveBeenCalled()
    wrapper.getComponent(AnalysisControls).vm.$emit('update:minutes', 20)
    wrapper.getComponent(AnalysisControls).vm.$emit('run')
    await flushPromises()
    expect(createAnalysis).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
  it('明确使用当前选点会撤销未确认的地址和坐标草稿，地图选点中禁止误启动', async () => {
    const wrapper = shallowMount(App)
    const controls = wrapper.getComponent(AnalysisControls)
    const selectedAddress = controls.props('center').address
    controls.vm.$emit('update:address-query', '尚未搜索的社区')
    controls.vm.$emit('update:coordinate-lng', '113.500000')
    await nextTick()
    expect(controls.props('locationPending')).toBe(true)
    controls.vm.$emit('fill-intent', intent)
    await nextTick()
    expect(controls.props('locationPending')).toBe(false)
    expect(controls.props('addressQuery')).toBe(selectedAddress)
    controls.vm.$emit('pick-center')
    await nextTick()
    expect(controls.props('centerPicking')).toBe(true)
    controls.vm.$emit('run')
    expect(createAnalysis).not.toHaveBeenCalled()
    wrapper.getComponent(MapStage).vm.$emit('cancel-center-pick')
    await nextTick()
    controls.vm.$emit('run')
    await flushPromises()
    expect(createAnalysis).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
  it('用户关闭过向导后不自动弹出，但可从顶部重新打开', async () => {
    vi.useFakeTimers()
    window.localStorage.setItem('life-circle:first-use-guide:v1', 'dismissed')
    const wrapper = shallowMount(App)
    await vi.advanceTimersByTimeAsync(500)
    expect(wrapper.getComponent(FirstUseGuide).props('open')).toBe(false)
    wrapper.getComponent(AppHeader).vm.$emit('open-guide')
    await nextTick()
    expect(wrapper.getComponent(FirstUseGuide).props('open')).toBe(true)
    wrapper.unmount()
    vi.useRealTimers()
  })
})
