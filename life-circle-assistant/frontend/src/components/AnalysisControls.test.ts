// @vitest-environment jsdom
import { shallowMount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AnalysisControls from './AnalysisControls.vue'
import { readFileSync } from 'node:fs'
import type { MapStatus, Report } from '../types/report'
import { ALL_CATEGORIES, DEFAULT_CATEGORIES } from '../constants/facilities'

const realStatus: MapStatus = {
  mode: 'real',
  provider_mode: 'real',
  provider: 'baidu-web-services',
  source: 'real_api',
  real_api_configured: true,
  real_api_probe_endpoint: '/api/map/probe',
  mock_available: true,
  snapshot_available: false,
  message: '已配置百度地图 Web 服务；接口连通性尚未探测',
}

function mountControls(mapStatus: MapStatus | null, realMapReady: boolean) {
  return shallowMount(AnalysisControls, {
    props: {
      center: { lng: 113.4872, lat: 23.1068, address: '海韵东路', selectionMethod: 'default', source: 'fixture', supportStatus: 'supported' },
      addressQuery: '', candidates: [], coordinateLng: '113.4872', coordinateLat: '23.1068',
      coordinateSystem: 'bd09', coordinateConversionNote: '', locationError: '',
      searching: false, resolving: false, mode: 'demo', minutes: 15, visibleCategories: ['market'],
      report: null, analysisError: '',
      showNormal: false, showSparse: true, showCritical: true, loading: false, source: mapStatus?.source,
      mapStatus, mapStatusLoading: false,
      mapProbeResult: mapStatus?.real_api_configured
        ? { configured: true, verified: true, checked_at: '2026-10-08T00:00:00+00:00', message: '地理编码探测成功' }
        : null,
      mapProbeLoading: false, realMapReady, mobileOpen: false,
    },
    global: { stubs: { ElSwitch: true } },
  })
}

describe('地图测试就绪状态', () => {
  it('后端和底图都就绪时明确显示正式测试可用', async () => {
    const wrapper = mountControls(realStatus, true)
    expect(wrapper.get('.map-readiness').classes()).toContain('ready')
    expect(wrapper.get('.map-readiness').text()).toContain('Web API 探测成功，浏览器底图已加载')
    expect(wrapper.get('.map-readiness').text()).toContain('Web API探测成功')
    expect(wrapper.get('.map-readiness').text()).toContain('百度底图已加载')
    expect(wrapper.get('.primary-action').text()).toContain('开始真实分析')
    expect(wrapper.get('.mode-note').text()).toContain('两种精度都会请求百度')

    await wrapper.get('.map-readiness button').trigger('click')
    expect(wrapper.emitted('probe-map-api')).toHaveLength(1)
  })

  it('后端不可达时不误报为本地快照', () => {
    const wrapper = mountControls(null, false)
    expect(wrapper.get('.map-readiness').text()).toContain('无法读取地图服务状态')
    expect(wrapper.get('.map-readiness').text()).toContain('Web API状态未知')
    expect(wrapper.get('.map-readiness').classes()).not.toContain('snapshot')
  })

  it('允许明确选择 WGS84、GCJ-02 或 BD-09 输入坐标系', async () => {
    const wrapper = mountControls(realStatus, true)
    const select = wrapper.get('select[aria-label="输入坐标系"]')

    await select.setValue('wgs84')

    expect(wrapper.emitted('update:coordinateSystem')).toEqual([['wgs84']])
    expect(select.findAll('option')).toHaveLength(3)
  })
})

describe('按需体检的设施展示与补充入口', () => {
  const fixture: Report = JSON.parse(readFileSync('../docs/validation/reports/hongshan-haiyundonglu-20260921.json', 'utf8'))
  function fourCategoryReport() {
    const report = structuredClone(fixture)
    report.parameters.categories = [...DEFAULT_CATEGORIES]
    return report
  }

  it('体检前全选七类；完成后只能全选报告范围，其余类别标注未体检', async () => {
    const wrapper = mountControls(realStatus, true)
    await wrapper.get('.facility-selection-actions button').trigger('click')
    expect(wrapper.emitted('update:visibleCategories')?.at(-1)).toEqual([ALL_CATEGORIES])
    await wrapper.setProps({ report: fourCategoryReport(), visibleCategories: ['medical'] })
    expect(wrapper.get('.layer-section-title').text()).toContain('本报告已体检 4 类')
    expect(wrapper.get('.layer-count').text()).toBe('1/4 类')
    await wrapper.get('.facility-selection-actions button').trigger('click')
    expect(wrapper.emitted('update:visibleCategories')?.at(-1)).toEqual([DEFAULT_CATEGORIES])
    const unanalyzed = wrapper.findAll('.facility-toggle.unanalyzed')
    expect(unanalyzed.map(button => button.text())).toEqual(['菜菜市场未体检', '药药店未体检', '园公园绿地未体检'])
    for (const button of unanalyzed) {
      expect(button.attributes('disabled')).toBeDefined()
      expect(button.attributes('aria-pressed')).toBe('false')
    }
  })

  it('全部隐藏只提交展示筛选；主动选择未体检类别后才能补充', async () => {
    const wrapper = mountControls(realStatus, true)
    await wrapper.setProps({ report: fourCategoryReport(), visibleCategories: [...DEFAULT_CATEGORIES] })
    await wrapper.findAll('.facility-selection-actions button')[1]!.trigger('click')
    expect(wrapper.emitted('update:visibleCategories')?.at(-1)).toEqual([[]])
    expect(wrapper.emitted('run')).toBeUndefined()
    expect(wrapper.get('.supplement-submit').attributes('disabled')).toBeDefined()
    await wrapper.get('.supplement-category-list input[value="market"]').setValue(true)
    expect(wrapper.get('.supplement-submit').text()).toContain('1类')
    await wrapper.get('.supplement-submit').trigger('click')
    expect(wrapper.emitted('supplement-analysis')).toEqual([[['market']]])
    expect(wrapper.emitted('toggle-category')).toBeUndefined()
    await wrapper.setProps({ loading: true })
    expect(wrapper.get('.supplement-submit').attributes('disabled')).toBeDefined()
    expect(wrapper.get('.facility-selection-actions button').attributes('disabled')).toBeDefined()
    await wrapper.setProps({ loading: false, analysisError: '测算失败' })
    expect(wrapper.get('.supplement-analysis [role="alert"]').text()).toContain('原报告已保留')
  })

  it('新报告包含补充类别后解除禁用，并清空补充选择', async () => {
    const report = fourCategoryReport()
    const wrapper = mountControls(realStatus, true)
    await wrapper.setProps({ report, visibleCategories: [...DEFAULT_CATEGORIES] })
    await wrapper.get('.supplement-category-list input[value="market"]').setValue(true)
    await wrapper.setProps({ report: { ...report, report_id: 'supplemented', parameters: { ...report.parameters, categories: [...DEFAULT_CATEGORIES, 'market'] } }, visibleCategories: [...DEFAULT_CATEGORIES, 'market'] })
    const market = wrapper.findAll('.facility-toggle').find(button => button.text().includes('菜市场'))!
    expect(market.attributes('disabled')).toBeUndefined()
    expect(market.attributes('aria-pressed')).toBe('true')
    expect(wrapper.findAll('.facility-toggle.unanalyzed')).toHaveLength(2)
    expect(wrapper.get('.supplement-submit').attributes('disabled')).toBeDefined()
  })
})
