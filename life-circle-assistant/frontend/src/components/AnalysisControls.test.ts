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
  real_api_available: true,
  mock_available: true,
  snapshot_available: false,
  message: '已启用百度地图 Web 服务实时测算',
}

function mountControls(mapStatus: MapStatus | null, realMapReady: boolean) {
  return shallowMount(AnalysisControls, {
    props: {
      center: { lng: 113.4872, lat: 23.1068, address: '海韵东路', selectionMethod: 'default', source: 'fixture', supportStatus: 'supported' },
      addressQuery: '', candidates: [], coordinateLng: '113.4872', coordinateLat: '23.1068', locationError: '',
      searching: false, resolving: false, mode: 'demo', minutes: 15, visibleCategories: ['market'],
      showNormal: false, showSparse: true, showCritical: true, loading: false, source: mapStatus?.source,
      mapStatus, mapStatusLoading: false, realMapReady, mobileOpen: false,
    },
    global: { stubs: { ElSegmented: true, ElSwitch: true } },
  })
}

describe('地图测试就绪状态', () => {
  it('后端和底图都就绪时明确显示正式测试可用', async () => {
    const wrapper = mountControls(realStatus, true)
    expect(wrapper.get('.map-readiness').classes()).toContain('ready')
    expect(wrapper.get('.map-readiness').text()).toContain('正式百度地图已就绪')
    expect(wrapper.get('.map-readiness').text()).toContain('Web 服务已连接')
    expect(wrapper.get('.map-readiness').text()).toContain('百度底图已加载')

    await wrapper.get('.map-readiness button').trigger('click')
    expect(wrapper.emitted('refresh-map-status')).toHaveLength(1)
  })

  it('后端不可达时不误报为本地快照', () => {
    const wrapper = mountControls(null, false)
    expect(wrapper.get('.map-readiness').text()).toContain('无法读取地图服务状态')
    expect(wrapper.get('.map-readiness').text()).toContain('Web 服务状态未知')
    expect(wrapper.get('.map-readiness').classes()).not.toContain('snapshot')
  })
})
