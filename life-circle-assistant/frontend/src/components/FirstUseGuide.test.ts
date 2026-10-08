// @vitest-environment jsdom
import { nextTick } from 'vue'
import { shallowMount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import FirstUseGuide from './FirstUseGuide.vue'
import type { MapStatus } from '../types/report'

const realStatus: MapStatus = {
  mode: 'real', provider_mode: 'real', provider: 'baidu-web-services', source: 'real_api',
  real_api_configured: true, real_api_probe_endpoint: '/api/map/probe',
  mock_available: true, snapshot_available: false, message: '真实服务已配置',
}

describe('首次使用向导', () => {
  it('根据真实服务和底图状态生成首步说明', () => {
    const ready = shallowMount(FirstUseGuide, {
      props: { open: true, mapStatus: realStatus, mapStatusLoading: false, realMapReady: true },
    })
    expect((ready.vm as unknown as { sourceDescription: string }).sourceDescription).toContain('主动触发')

    const missingMap = shallowMount(FirstUseGuide, {
      props: { open: true, mapStatus: realStatus, mapStatusLoading: false, realMapReady: false },
    })
    expect((missingMap.vm as unknown as { sourceDescription: string }).sourceDescription).toContain('域名白名单')
  })

  it('打开时从第一步开始并通知页面打开对应面板', async () => {
    const wrapper = shallowMount(FirstUseGuide, {
      props: { open: false, mapStatus: realStatus, mapStatusLoading: false, realMapReady: true },
    })
    await wrapper.setProps({ open: true })
    await nextTick()
    expect(wrapper.emitted('step-change')).toContainEqual([0])
  })
})
