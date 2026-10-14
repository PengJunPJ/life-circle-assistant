// @vitest-environment jsdom
import { readFileSync } from 'node:fs'
import { effectScope, nextTick, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ALL_CATEGORIES, DEFAULT_CATEGORIES } from '../constants/facilities'
import { createAnalysis, resumeAnalysisTask, retryAnalysisTask, waitForAnalysis } from '../services/analysisApi'
import { AnalysisTaskTerminalError } from '../services/analysisTaskError'
import type { AnalysisCenter } from '../types/location'
import type { Report } from '../types/report'
import { useAnalysis } from './useAnalysis'

vi.mock('../services/analysisApi', () => ({ createAnalysis: vi.fn(), waitForAnalysis: vi.fn(), cancelAnalysisTask: vi.fn(), retryAnalysisTask: vi.fn(), resumeAnalysisTask: vi.fn() }))
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
  it('失败任务复用原任务断点，取消任务创建重试任务，不重发已完成路线', async () => {
    const { controller } = setup()
    const source = { id: 'failed-task', status: 'failed' as const, progress: 55, stage: 'walking', stage_label: '中断', request: fixture.parameters }
    controller.currentTask.value = source
    vi.mocked(resumeAnalysisTask).mockResolvedValue({ ...source, status: 'queued' })
    vi.mocked(waitForAnalysis).mockResolvedValue(fixture)
    expect(await controller.retryCurrentTask()).toBe(true)
    expect(resumeAnalysisTask).toHaveBeenCalledWith('failed-task'); expect(retryAnalysisTask).not.toHaveBeenCalled()
    controller.currentTask.value = { ...source, id: 'cancelled-task', status: 'cancelled' }
    vi.mocked(retryAnalysisTask).mockResolvedValue({ ...source, id: 'replacement-task', status: 'queued' })
    expect(await controller.retryCurrentTask()).toBe(true)
    expect(retryAnalysisTask).toHaveBeenCalledWith('cancelled-task')
  })

  it('首次体检只请求勾选范围，不默认查询七类', async () => {
    const { controller } = setup()
    expect(controller.analysisCategories.value).toEqual(DEFAULT_CATEGORIES)
    controller.setAnalysisCategories(['market', 'pharmacy'])
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
    controller.setAnalysisCategories(['market'])
    expect(controller.analysisCategories.value).toEqual(['market'])
  })

  it('报告后的范围修改独立于地图显示，相同参数增加类别自动补充', async () => {
    const { controller } = setup()
    const original = report()
    controller.applyReport(original)
    await nextTick()
    controller.setVisibleCategories(['medical'])
    controller.setAnalysisCategories(ALL_CATEGORIES)
    expect(controller.visibleCategories.value).toEqual(['medical'])
    expect(controller.report.value).toEqual(original)
    expect(controller.supplementCategories.value).toEqual(['market', 'pharmacy', 'park'])
    vi.mocked(waitForAnalysis).mockResolvedValue(report(ALL_CATEGORIES, 'supplemented'))
    await controller.runAnalysis()
    expect(createAnalysis).toHaveBeenCalledWith(expect.objectContaining({ categories: ALL_CATEGORIES, minutes: original.parameters.minutes }))
    expect(controller.visibleCategories.value).toEqual(['medical', 'market', 'pharmacy', 'park'])
  })

  it('改变步行时间后按新参数体检，失败保留原报告及新选择供重试', async () => {
    const { controller } = setup()
    const original = report()
    controller.applyReport(original)
    await nextTick()
    controller.setAnalysisCategories(['market'])
    controller.minutes.value = original.parameters.minutes === 20 ? 10 : 20
    expect(controller.supplementCategories.value).toEqual([])
    vi.mocked(waitForAnalysis).mockRejectedValue(new Error('体检失败'))
    await controller.runAnalysis()
    expect(createAnalysis).toHaveBeenCalledWith(expect.objectContaining({ categories: ['market'], minutes: controller.minutes.value }))
    expect(controller.report.value).toEqual(original)
    expect(controller.analysisCategories.value).toEqual(['market'])
  })

  it('另一页面取消后台任务后保留取消终态，刷新恢复时不伪装成失败', async () => {
    const { controller } = setup()
    vi.mocked(waitForAnalysis).mockRejectedValue(new AnalysisTaskTerminalError({ id: 'task', status: 'cancelled', progress: 48, stage: 'cancelled', stage_label: '用户取消' }))
    expect(await controller.followTask({ id: 'task', status: 'running', progress: 40, stage: 'walking', stage_label: '计算中' })).toBe(false)
    expect(controller.currentTask.value?.status).toBe('cancelled')
    expect(controller.currentTask.value?.progress).toBe(48)
    expect(controller.loading.value).toBe(false)
    expect(controller.report.value).toBeNull()
    expect(controller.error.value).toBe('')
  })

  it('任务恢复完成后使用返回报告，不额外创建体检任务', async () => {
    const { controller } = setup()
    const result = report(['market'])
    vi.mocked(waitForAnalysis).mockResolvedValue(result)
    expect(await controller.followTask({ id: 'task', status: 'completed', progress: 100, stage: 'completed', stage_label: '已完成', result })).toBe(true)
    expect(controller.currentTask.value?.status).toBe('completed')
    expect(controller.report.value?.report_id).toBe(result.report_id)
    expect(createAnalysis).not.toHaveBeenCalled()
  })

  it('新建任务请求失败不把上次成功任务覆盖成失败', async () => {
    const { controller } = setup()
    vi.mocked(waitForAnalysis).mockResolvedValue(report())
    await controller.runAnalysis()
    vi.mocked(createAnalysis).mockRejectedValue(new Error('创建请求失败'))
    expect(await controller.runAnalysis()).toBe(false)
    expect(controller.currentTask.value).toBeNull()
    expect(controller.error.value).toBe('创建请求失败')
  })
})
