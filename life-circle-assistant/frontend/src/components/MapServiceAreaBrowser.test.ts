// @vitest-environment jsdom
import { readFileSync } from 'node:fs'
import { mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import type { Report } from '../types/report'
import MapServiceAreaBrowser from './MapServiceAreaBrowser.vue'

const fixture: Report = JSON.parse(readFileSync('../docs/validation/reports/hongshan-haiyundonglu-20260921.json', 'utf8'))
const sparse = fixture.service_areas.features.find(area => area.properties.category === 'market' && area.properties.kind === 'sparse')!
const critical = fixture.service_areas.features.find(area => area.properties.category === 'school' && area.properties.kind === 'critical')!
const names = new Map([[sparse.properties.grid_id, '菜市场 · 区域 4'], [critical.properties.grid_id, '小学 · 区域 8']])
let wrapper: VueWrapper | undefined
function setup() {
  wrapper = mount(MapServiceAreaBrowser, { props: { areas: [sparse, critical], names, selectedId: null }, attachTo: document.body })
  return wrapper
}
afterEach(() => { wrapper?.unmount(); wrapper = undefined })

describe('地图区域判定浏览器', () => {
  it('默认收起，展开后按设施顺序分组，用自然名称说明区域与点击用途', async () => {
    const view = setup()
    expect(view.get('.service-area-trigger').text()).toContain('2 个可见区域')
    expect(view.find('.service-area-menu').exists()).toBe(false)
    await view.get('.service-area-trigger').trigger('click')
    expect(view.get('#service-area-help').text()).toContain('分析网格')
    expect(view.findAll('.service-area-group h3').map(group => group.text())).toEqual(['学小学1 个区域', '菜菜市场1 个区域'])
    expect(view.get('.service-area-summary').text()).toContain('重点盲区 1')
    expect(view.get('.service-area-summary').text()).toContain('稀疏区 1')
    const rows = view.findAll('.service-area-row')
    expect(rows[0]!.text()).toContain('小学 · 区域 8')
    expect(rows[0]!.attributes('aria-label')).toContain('定位并查看判定依据')
    for (const area of [sparse, critical]) {
      expect(view.text()).not.toContain(area.properties.grid_id)
      expect(rows.some(row => row.attributes('aria-label')?.includes(area.properties.grid_id))).toBe(false)
    }
  })

  it('选择时传递完整区域与内部标识并收起，重复选择恢复入口焦点', async () => {
    const view = setup()
    await view.get('.service-area-trigger').trigger('click')
    await view.findAll('.service-area-row')[0]!.trigger('click')
    expect(view.emitted('select')).toEqual([[critical]])
    expect(view.find('.service-area-menu').exists()).toBe(false)
    expect(view.emitted('update:open')?.at(-1)).toEqual([false])
    await view.setProps({ selectedId: critical.properties.grid_id })
    await view.get('.service-area-trigger').trigger('click')
    expect(view.get('.service-area-row').attributes('aria-pressed')).toBe('true')
    expect(view.get('.service-area-row').text()).toContain('已选中')
    await view.get('.service-area-row').trigger('click')
    expect(document.activeElement).toBe(view.get('.service-area-trigger').element)
  })

  it('显示筛选更新区域数量和分组，保持既有编号，全部隐藏后移除入口', async () => {
    const view = setup()
    await view.get('.service-area-trigger').trigger('click')
    await view.setProps({ areas: [sparse] })
    expect(view.get('.service-area-trigger').text()).toContain('1 个可见区域')
    expect(view.findAll('.service-area-group')).toHaveLength(1)
    expect(view.get('.service-area-row').text()).toContain('菜市场 · 区域 4')
    expect(view.get('.service-area-summary').text()).not.toContain('重点盲区')
    await view.setProps({ areas: [] })
    expect(view.find('.service-area-browser').exists()).toBe(false)
    expect(view.emitted('update:open')?.at(-1)).toEqual([false])
  })

  it('支持 Escape、关闭按钮与外部点击收起，报告更换时关闭旧列表', async () => {
    const view = setup()
    await view.get('.service-area-trigger').trigger('click')
    await view.get('.service-area-row').trigger('keydown', { key: 'Escape' })
    expect(view.find('.service-area-menu').exists()).toBe(false)
    expect(document.activeElement).toBe(view.get('.service-area-trigger').element)
    await view.get('.service-area-trigger').trigger('click')
    await view.get('.service-area-heading button').trigger('click')
    expect(document.activeElement).toBe(view.get('.service-area-trigger').element)
    await view.get('.service-area-trigger').trigger('click')
    document.body.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    await view.vm.$nextTick()
    expect(view.find('.service-area-menu').exists()).toBe(false)
    await view.get('.service-area-trigger').trigger('click')
    await view.setProps({ names: new Map(names) })
    expect(view.find('.service-area-menu').exists()).toBe(false)
  })
})
