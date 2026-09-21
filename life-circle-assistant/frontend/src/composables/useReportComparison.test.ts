import { beforeEach, describe, expect, it, vi } from 'vitest'
import { compareHistoricalReports } from '../services/analysisApi'
import { useReportComparison } from './useReportComparison'

vi.mock('../services/analysisApi', () => ({ compareHistoricalReports: vi.fn() }))

describe('useReportComparison', () => {
  beforeEach(() => vi.clearAllMocks())

  it('限制选择两份且再次点击会取消选择', () => {
    const state = useReportComparison()
    state.toggleReport('report-1')
    state.toggleReport('report-2')
    state.toggleReport('report-3')
    expect(state.selectedReportIds.value).toEqual(['report-1', 'report-2'])
    expect(state.error.value).toContain('只能比较两份')

    state.toggleReport('report-1')
    expect(state.selectedReportIds.value).toEqual(['report-2'])
  })

  it('选择不足时不会请求比较接口', async () => {
    const state = useReportComparison()
    state.toggleReport('report-1')
    expect(await state.compareSelection()).toBeNull()
    expect(state.error.value).toContain('请选择两份不同')
    expect(compareHistoricalReports).not.toHaveBeenCalled()
  })

  it('比较成功后保存结果，并保留返回原报告所需标识', async () => {
    const state = useReportComparison()
    const response = {
      report_ids: ['report-1', 'report-2'],
      reports: [{ report_id: 'report-1' }, { report_id: 'report-2' }],
      categories: [],
    } as any
    vi.mocked(compareHistoricalReports).mockResolvedValueOnce(response)
    state.toggleReport('report-1')
    state.toggleReport('report-2')

    expect(await state.compareSelection()).toEqual(response)
    expect(compareHistoricalReports).toHaveBeenCalledWith(['report-1', 'report-2'])
    expect(state.comparison.value?.reports.map((item) => item.report_id)).toEqual(['report-1', 'report-2'])
    expect(state.loading.value).toBe(false)
  })

  it('无效报告错误会明确显示且不保留旧比较结果', async () => {
    const state = useReportComparison()
    state.toggleReport('report-1')
    state.toggleReport('missing')
    vi.mocked(compareHistoricalReports).mockRejectedValueOnce(new Error('报告 missing 不存在或尚未完成'))

    expect(await state.compareSelection()).toBeNull()
    expect(state.error.value).toContain('不存在或尚未完成')
    expect(state.comparison.value).toBeNull()
  })
})
