// @vitest-environment jsdom
import { nextTick } from 'vue'
import { shallowMount } from '@vue/test-utils'
import { ElTour, ElTourStep } from 'element-plus/es/components/tour/index'
import { describe, expect, it } from 'vitest'
import FirstUseGuide from './FirstUseGuide.vue'
import type { MapStatus } from '../types/report'

const realStatus: MapStatus = {
  mode: 'real', provider_mode: 'real', provider: 'baidu-web-services', source: 'real_api',
  real_api_configured: true, real_api_probe_endpoint: '/api/map/probe',
  mock_available: true, snapshot_available: false, message: '真实服务已配置',
}
const baseProps = { open: true, hasReport: false, mapStatus: realStatus, mapStatusLoading: false, mapProbeResult: null, realMapReady: true }
function mountGuide(props = {}) {
  return shallowMount(FirstUseGuide, { props: { ...baseProps, ...props }, global: { renderStubDefaultSlot: true } })
}

describe('首次使用向导', () => {
  it('根据真实服务和底图状态生成首步说明', () => {
    const ready = mountGuide()
    const description = ready.findComponent(ElTourStep).props('description')
    expect(description).toContain('已配置但尚未验证')
    expect(description).toContain('浏览器底图已加载')
    expect(description).toContain('消耗地图配额')
    const missingMap = mountGuide({ realMapReady: false })
    expect(missingMap.findComponent(ElTourStep).props('description')).toContain('浏览器底图尚未加载')
    ready.unmount()
    missingMap.unmount()
  })

  it('打开时从第一步开始并通知页面打开对应面板', async () => {
    const wrapper = mountGuide({ open: false })
    await wrapper.setProps({ open: true })
    await nextTick()
    expect(wrapper.emitted('step-change')).toContainEqual([{ id: 'source', surface: 'controls', reportPage: undefined }])
    wrapper.findComponent(ElTour).vm.$emit('change', 6)
    await nextTick()
    expect(wrapper.emitted('step-change')?.at(-1)?.[0]).toMatchObject({ id: 'map', surface: 'map' })
    await wrapper.setProps({ open: false })
    await wrapper.setProps({ open: true })
    expect(wrapper.findComponent(ElTour).props('current')).toBe(0)
    wrapper.unmount()
  })

  it('无报告时预告后续入口，后台生成报告不改变当前步骤；重新打开后定位报告各页', async () => {
    const wrapper = mountGuide()
    const titles = () => wrapper.findAllComponents(ElTourStep).map(step => step.props('title'))
    const initial = titles()
    expect(initial).toContain('报告生成后从这里阅读')
    await wrapper.setProps({ hasReport: true })
    expect(titles()).toEqual(initial)
    await wrapper.setProps({ open: false })
    await wrapper.setProps({ open: true })
    expect(titles()).toContain('逐类核对设施覆盖与空间缺口')
    expect(titles()).toContain('按用途导出报告与空间数据')
    const index = titles().indexOf('逐类核对设施覆盖与空间缺口')
    wrapper.findComponent(ElTour).vm.$emit('change', index)
    expect(wrapper.emitted('step-change')?.at(-1)?.[0]).toMatchObject({ surface: 'report', reportPage: 'facilities' })
    wrapper.unmount()
  })

  it('窄视口把面板步骤的卡片放到目标上方，避免推出屏幕', async () => {
    const original = window.matchMedia
    const listeners = new Set<(event: MediaQueryListEvent) => void>()
    let matches = true
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      writable: true,
      value: () =>
        ({
          matches,
          addEventListener: (_: string, fn: never) => listeners.add(fn),
          removeEventListener: (_: string, fn: never) =>
            listeners.delete(fn),
        }) as unknown as MediaQueryList,
    })
    const wrapper = mountGuide()
    const placements = () =>
      wrapper.findAllComponents(ElTourStep).map(step => step.props('placement'))
    expect(placements()[0]).toBe('top')
    expect(placements().at(-1)).toBe('top')
    // 对话与地图步骤仍贴着地图控件，不受视口宽度影响。
    expect(placements()[5]).toBe('bottom')
    matches = false
    listeners.forEach(fn => fn({ matches: false } as MediaQueryListEvent))
    await nextTick()
    expect(placements()[0]).toBe('right')
    expect(placements().at(-1)).toBe('left')
    wrapper.unmount()
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      writable: true,
      value: original,
    })
  })

  it('区分完成和提前退出，完成事件不会被随后的关闭覆盖', async () => {
    const wrapper = mountGuide()
    const tour = wrapper.findComponent(ElTour)
    tour.vm.$emit('close')
    tour.vm.$emit('finish')
    await wrapper.setProps({ open: false })
    await nextTick()
    expect(wrapper.emitted('close')).toEqual([[true]])
    await wrapper.setProps({ open: true })
    tour.vm.$emit('close')
    await nextTick()
    expect(wrapper.emitted('close')?.at(-1)).toEqual([false])
    expect(tour.props('targetAreaClickable')).toBe(false)
    wrapper.unmount()
  })
})
