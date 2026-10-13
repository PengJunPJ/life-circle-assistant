// @vitest-environment jsdom
import { shallowMount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AnalysisControls from './AnalysisControls.vue'
import NaturalLanguageAnalysis from './NaturalLanguageAnalysis.vue'
import { ALL_CATEGORIES, DEFAULT_CATEGORIES } from '../constants/facilities'
import type { MapStatus } from '../types/report'

const realStatus: MapStatus = { mode: 'real', provider_mode: 'real', provider: 'baidu', source: 'real_api', real_api_configured: true, real_api_probe_endpoint: '/api/map/probe', mock_available: true, snapshot_available: false, message: '已配置' }
function setup() {
  return shallowMount(AnalysisControls, { props: {
    center: { lng: 113.4872, lat: 23.1068, address: '海韵东路', selectionMethod: 'default', source: 'fixture', supportStatus: 'supported' },
    addressQuery: '海韵东路', candidates: [], coordinateLng: '113.487200', coordinateLat: '23.106800', coordinateSystem: 'bd09', coordinateConversionNote: '', locationError: '', locationPending: false,
    searching: false, resolving: false, mode: 'analysis', minutes: 15, minutesValid: true, analysisCategories: [...DEFAULT_CATEGORIES], supplementCount: 0, report: null, analysisError: '', loading: false,
    mapStatus: realStatus, mapStatusLoading: false, mapProbeResult: { configured: true, verified: true, checked_at: '', message: '地理编码探测成功' }, mapProbeLoading: false, realMapReady: true, mobileOpen: false,
  } })
}

describe('公共体检表单', () => {
  it('默认自主设置，切换入口只替换输入区，公共参数和唯一启动按钮保留', async () => {
    const wrapper = setup()
    expect(wrapper.get('#manual-entry-panel').isVisible()).toBe(true)
    expect(wrapper.get('#natural-entry-panel').isVisible()).toBe(false)
    expect(wrapper.findAll('.primary-action')).toHaveLength(1)
    await wrapper.get('#natural-entry-tab').trigger('click')
    expect(wrapper.get('#manual-entry-panel').attributes('style')).toContain('display: none')
    expect(wrapper.get('#natural-entry-panel').attributes('style') ?? '').not.toContain('display: none')
    expect(wrapper.findAll('input[name="walking-time"]')).toHaveLength(3)
    expect(wrapper.findAll('.facility-toggle')).toHaveLength(7)
    expect(wrapper.getComponent(NaturalLanguageAnalysis).props('previous')).toMatchObject({ minutes: 15, mode: 'analysis', categories: DEFAULT_CATEGORIES, use_current_center: true })
    expect(wrapper.get('.analysis-footer').text()).toContain('位置已确认 · 15分钟 · 4类设施')
    expect(wrapper.find('[aria-label="服务区域状态图层"]').exists()).toBe(false)
  })

  it('尚未发送的描述只阻止当前入口启动，解析中则所有入口禁止切换和启动', async () => {
    const wrapper = setup()
    await wrapper.get('#natural-entry-tab').trigger('click')
    wrapper.getComponent(NaturalLanguageAnalysis).vm.$emit('update:blocked', true)
    await wrapper.vm.$nextTick()
    expect(wrapper.get('.primary-action').attributes('disabled')).toBeDefined()
    await wrapper.get('#manual-entry-tab').trigger('click')
    expect(wrapper.get('.primary-action').attributes('disabled')).toBeUndefined()
    wrapper.getComponent(NaturalLanguageAnalysis).vm.$emit('update:busy', true)
    await wrapper.vm.$nextTick()
    expect(wrapper.get('.primary-action').attributes('disabled')).toBeDefined()
    expect(wrapper.get('#natural-entry-tab').attributes('disabled')).toBeDefined()
  })

  it('未确认位置、时间或空设施不能启动；共享按钮支持补充体检', async () => {
    const wrapper = setup()
    for (const invalid of [{ locationPending: true }, { centerPicking: true }, { searching: true }, { minutesValid: false }, { analysisCategories: [] }]) {
      await wrapper.setProps(invalid)
      expect(wrapper.get('.primary-action').attributes('disabled')).toBeDefined()
      await wrapper.setProps({ locationPending: false, centerPicking: false, searching: false, minutesValid: true, analysisCategories: [...DEFAULT_CATEGORIES] })
    }
    await wrapper.setProps({ supplementCount: 3 })
    expect(wrapper.get('.primary-action').text()).toContain('补充体检（3类）')
    await wrapper.get('.primary-action').trigger('click')
    expect(wrapper.emitted('run')).toEqual([[]])
  })

  it('全选和全部取消修改体检范围，坐标和精度归入折叠高级设置', async () => {
    const wrapper = setup()
    await wrapper.get('.facility-selection-actions button').trigger('click')
    expect(wrapper.emitted('update:analysisCategories')?.at(-1)).toEqual([ALL_CATEGORIES])
    await wrapper.findAll('.facility-selection-actions button')[1]!.trigger('click')
    expect(wrapper.emitted('update:analysisCategories')?.at(-1)).toEqual([[]])
    expect(wrapper.get('.advanced-settings').attributes('open')).toBeUndefined()
    const select = wrapper.get('.advanced-settings select')
    await select.setValue('wgs84')
    expect(wrapper.emitted('update:coordinateSystem')).toEqual([['wgs84']])
    await wrapper.get('.map-pick-action').trigger('click')
    expect(wrapper.emitted('pick-center')).toEqual([[]])
  })

  it('数据状态缩成摘要，验证仍由用户触发，异常保持可见', async () => {
    const wrapper = setup()
    expect(wrapper.get('.compact-data-status summary').text()).toContain('接口已验证')
    expect(wrapper.get('.compact-data-status').attributes('open')).toBeUndefined()
    await wrapper.get('.data-status-details button').trigger('click')
    expect(wrapper.emitted('probe-map-api')).toEqual([[]])
    await wrapper.setProps({ mapStatus: null, realMapReady: false })
    expect(wrapper.get('.control-warning').text()).toContain('无法读取数据状态')
    expect(wrapper.get('.compact-data-status').text()).not.toContain('本地快照')
  })
})
