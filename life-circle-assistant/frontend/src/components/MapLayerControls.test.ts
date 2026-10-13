// @vitest-environment jsdom
import { readFileSync } from 'node:fs'
import { shallowMount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { ALL_CATEGORIES, DEFAULT_CATEGORIES } from '../constants/facilities'
import type { Report } from '../types/report'
import MapLayerControls from './MapLayerControls.vue'

const fixture: Report = JSON.parse(readFileSync('../docs/validation/reports/hongshan-haiyundonglu-20260921.json', 'utf8'))
function setup() {
  const report = structuredClone(fixture)
  report.parameters.categories = [...DEFAULT_CATEGORIES]
  return shallowMount(MapLayerControls, { props: { report, visibleCategories: ['medical'], loading: false, showNormal: false, showSparse: true, showCritical: true }, global: { stubs: { ElSwitch: true } } })
}

describe('报告地图显示控制', () => {
  it('全选只能展示报告已分析的类别，未体检类别禁用并提供填参入口', async () => {
    const wrapper = setup()
    await wrapper.get('.map-layer-trigger').trigger('click')
    await wrapper.get('.facility-selection-actions button').trigger('click')
    expect(wrapper.emitted('update:visibleCategories')).toEqual([[DEFAULT_CATEGORIES]])
    expect(wrapper.findAll('.facility-toggle.unanalyzed')).toHaveLength(3)
    for (const button of wrapper.findAll('.facility-toggle.unanalyzed')) {
      expect(button.attributes('disabled')).toBeDefined()
      expect(button.attributes('aria-pressed')).toBe('false')
      expect(button.text()).toContain('未体检')
    }
    await wrapper.get('.prepare-supplement').trigger('click')
    expect(wrapper.emitted('prepare-supplement')).toEqual([[]])
    expect(wrapper.find('.map-layer-menu').exists()).toBe(false)
  })
  it('隐藏图层仅提交显示筛选，补充报告到达后新增类别可展示', async () => {
    const wrapper = setup()
    await wrapper.get('.map-layer-trigger').trigger('click')
    await wrapper.findAll('.facility-selection-actions button')[1]!.trigger('click')
    expect(wrapper.emitted('update:visibleCategories')).toEqual([[[]]])
    await wrapper.setProps({ report: { ...fixture, parameters: { ...fixture.parameters, categories: [...ALL_CATEGORIES] } } })
    expect(wrapper.findAll('.facility-toggle.unanalyzed')).toHaveLength(0)
    await wrapper.get('.facility-selection-actions button').trigger('click')
    expect(wrapper.emitted('update:visibleCategories')?.at(-1)).toEqual([ALL_CATEGORIES])
    await wrapper.get('.map-layer-menu').trigger('keydown', { key: 'Escape' })
    expect(wrapper.get('.map-layer-trigger').attributes('aria-expanded')).toBe('false')
  })
})
