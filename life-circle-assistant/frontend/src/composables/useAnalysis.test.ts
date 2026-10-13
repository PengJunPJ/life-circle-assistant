// @vitest-environment jsdom
import { readFileSync } from 'node:fs'
import { effectScope, nextTick, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ALL_CATEGORIES, DEFAULT_CATEGORIES } from '../constants/facilities'
import { createAnalysis, waitForAnalysis } from '../services/analysisApi'
import type { AnalysisCenter } from '../types/location'
import type { Report } from '../types/report'
import { useAnalysis } from './useAnalysis'

vi.mock('../services/analysisApi', () => ({ createAnalysis: vi.fn(), waitForAnalysis: vi.fn() }))
vi.mock('element-plus/es/components/message/index', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

const fixture: Report = JSON.parse(readFileSync('../docs/validation/reports/hongshan-haiyundonglu-20260921.json', 'utf8'))
let scope: ReturnType<typeof effectScope>
function setup() {
  scope = effectScope()
  const center = ref<AnalysisCenter>({ lng: fixture.center.lng, lat: fixture.center.lat, address: fixture.center.address, selectionMethod: 'default', source: fixture.source, supportStatus: 'supported' })
  return { center, controller: scope.run(() => useAnalysis(center))! }
}
function report(categories = DEFAULT_CATEGORIES, id = 'four-category-report') {
  const value = structuredClone(fixture)
  value.report_id = id
  value.parameters.categories = [...categories]
  return value
}

describe('体检范围与地图展示分离', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.mocked(createAnalysis).mockResolvedValue({ id: 'task', status: 'completed', progress: 100, stage: 'completed', stage_label: '已完成' })
  })
  afterEach(() => { scope?.stop() })

  it('首次体检只请求勾选范围，不默认查询七类', async () => {
    const { controller } = setup()
    expect(controller.analysisCategories.value).toEqual(DEFAULT_CATEGORIES)
    controller.setVisibleCategories(['market', 'pharmacy'])
    vi.mocked(waitForAnalysis).mockResolvedValue(report(['market', 'pharmacy']))
    await controller.runAnalysis()
    expect(createAnalysis).toHaveBeenCalledWith(expect.objectContaining({ categories: ['market', 'pharmacy'] }))
    expect(controller.report.value?.parameters.categories).toEqual(['market', 'pharmacy'])
  })

  it('报告后的全选仅展示已体检类别，隐藏不改变范围或重新体检请求', async () => {
    const { controller } = setup()
    const original = report()
    controller.applyReport(original)
    await nextTick()
    controller.toggleCategory('market')
    expect(controller.visibleCategories.value).toEqual(DEFAULT_CATEGORIES)
    controller.setVisibleCategories(ALL_CATEGORIES)
    expect(controller.visibleCategories.value).toEqual(DEFAULT_CATEGORIES)
    controller.setVisibleCategories([])
    expect(controller.analysisCategories.value).toEqual(DEFAULT_CATEGORIES)
    expect(controller.report.value).toEqual(original)
    expect(createAnalysis).not.toHaveBeenCalled()
    vi.mocked(waitForAnalysis).mockResolvedValue(report())
    await controller.runAnalysis()
    expect(createAnalysis).toHaveBeenCalledWith(expect.objectContaining({ categories: DEFAULT_CATEGORIES }))
  })

  it('补充沿用原报告参数，包含全部原类别，成功后只新增对应展示', async () => {
    const { controller } = setup()
    const original = report()
    controller.applyReport(original)
    await nextTick()
    controller.setVisibleCategories(['medical'])
    controller.minutes.value = 20
    controller.mode.value = original.parameters.mode === 'demo' ? 'analysis' : 'demo'
    let finish!: (value: Report) => void
    vi.mocked(waitForAnalysis).mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const pending = controller.supplementAnalysis(['market', 'invalid', 'market'])
    await nextTick()
    expect(controller.report.value).toEqual(original)
    expect(controller.visibleCategories.value).toEqual(['medical'])
    expect(createAnalysis).toHaveBeenCalledWith(expect.objectContaining({ categories: [...DEFAULT_CATEGORIES, 'market'], minutes: original.parameters.minutes, mode: original.parameters.mode, lng: original.center.lng, lat: original.center.lat, center_address: original.center.address }))
    const updated = report([...DEFAULT_CATEGORIES, 'market'], 'supplemented')
    finish(updated)
    expect(await pending).toBe(true)
    expect(controller.analysisCategories.value).toEqual([...DEFAULT_CATEGORIES, 'market'])
    expect(controller.visibleCategories.value).toEqual(['medical', 'market'])
    expect(controller.report.value?.report_id).toBe('supplemented')
    controller.setVisibleCategories(ALL_CATEGORIES)
    expect(controller.visibleCategories.value).toEqual([...DEFAULT_CATEGORIES, 'market'])
  })

  it('补充失败保留原报告和展示，允许选择相同类别重试', async () => {
    const { controller } = setup()
    const original = report()
    controller.applyReport(original)
    await nextTick()
    controller.setVisibleCategories([])
    vi.mocked(waitForAnalysis).mockRejectedValueOnce(new Error('接口暂不可用')).mockResolvedValueOnce(report(ALL_CATEGORIES, 'retry-report'))
    expect(await controller.supplementAnalysis(['market', 'pharmacy', 'park'])).toBe(false)
    expect(controller.report.value).toEqual(original)
    expect(controller.analysisCategories.value).toEqual(DEFAULT_CATEGORIES)
    expect(controller.visibleCategories.value).toEqual([])
    expect(controller.error.value).toBe('接口暂不可用')
    expect(controller.loading.value).toBe(false)
    expect(await controller.supplementAnalysis(['market', 'pharmacy', 'park'])).toBe(true)
    expect(controller.visibleCategories.value).toEqual(['market', 'pharmacy', 'park'])
    expect(controller.analysisCategories.value).toEqual(ALL_CATEGORIES)
    expect(controller.error.value).toBe('')
  })

  it('未选择新增类别或任务进行中不发起额外请求', async () => {
    const { controller } = setup()
    controller.applyReport(report())
    await nextTick()
    expect(await controller.supplementAnalysis(['medical'])).toBe(false)
    controller.loading.value = true
    expect(await controller.supplementAnalysis(['market'])).toBe(false)
    expect(createAnalysis).not.toHaveBeenCalled()
  })

  it('换选点恢复体检范围选择，不沿用上一报告的隐藏状态', async () => {
    const { controller, center } = setup()
    controller.applyReport(report())
    await nextTick()
    controller.setVisibleCategories([])
    center.value = { ...center.value, lng: center.value.lng + .001 }
    await nextTick()
    expect(controller.report.value).toBeNull()
    expect(controller.visibleCategories.value).toEqual(DEFAULT_CATEGORIES)
    controller.setVisibleCategories(['market'])
    expect(controller.analysisCategories.value).toEqual(['market'])
  })
})
