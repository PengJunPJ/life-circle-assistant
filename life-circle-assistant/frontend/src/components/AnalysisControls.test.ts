// @vitest-environment jsdom
import { shallowMount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AnalysisControls from './AnalysisControls.vue'
import type { MapStatus } from '../types/report'

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
      addressQuery: '', candidates: [], coordinateLng: '113.4872', coordinateLat: '23.1068', locationError: '',
      searching: false, resolving: false, mode: 'demo', minutes: 15, visibleCategories: ['market'],
      showNormal: false, showSparse: true, showCritical: true, loading: false, source: mapStatus?.source,
      mapStatus, mapStatusLoading: false,
      mapProbeResult: mapStatus?.real_api_configured
        ? { configured: true, verified: true, checked_at: '2026-10-08T00:00:00+00:00', message: '地理编码探测成功' }
        : null,
      mapProbeLoading: false, realMapReady, mobileOpen: false,
    },
    global: { stubs: { ElSegmented: true, ElSwitch: true } },
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
})
