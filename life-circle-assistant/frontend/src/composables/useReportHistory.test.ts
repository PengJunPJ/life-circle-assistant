import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useReportHistory } from './useReportHistory'
import { fetchReportHistory, getHistoricalReport, rerunHistoricalReport, waitForAnalysis } from '../services/analysisApi'

vi.mock('../services/analysisApi', () => ({
  fetchReportHistory: vi.fn(),
  getHistoricalReport: vi.fn(),
  rerunHistoricalReport: vi.fn(),
  waitForAnalysis: vi.fn(),
}))

const historyItem = {
  report_id: 'report-1',
  task_id: 'task-1',
  schema_version: '2.0',
  created_at: '2026-09-20T08:00:00Z',
  completed_at: '2026-09-20T08:01:00Z',
  center: { address: '测试社区', lng: 113.5, lat: 23.1 },
  minutes: 15 as const,
  mode: 'demo' as const,
  categories: ['market'],
}

describe('useReportHistory', () => {
  beforeEach(() => vi.clearAllMocks())

  it('区分空状态、成功列表和加载失败状态', async () => {
    const history = useReportHistory()
    expect(history.items.value).toEqual([])

    vi.mocked(fetchReportHistory).mockResolvedValueOnce({ items: [historyItem], total: 1, limit: 20, offset: 0 })
    await history.loadHistory()
    expect(history.items.value).toEqual([historyItem])
    expect(history.total.value).toBe(1)
    expect(history.error.value).toBe('')

    vi.mocked(fetchReportHistory).mockRejectedValueOnce(new Error('网络不可用'))
    await history.loadHistory()
    expect(history.loading.value).toBe(false)
    expect(history.error.value).toBe('网络不可用')
  })

  it('可以打开历史报告并使用原任务入口重新运行', async () => {
    const history = useReportHistory()
    const report = { report_id: 'report-1', source: 'local_snapshot' } as any
    const rerunReport = { report_id: 'report-2', source: 'local_snapshot' } as any
    vi.mocked(getHistoricalReport).mockResolvedValueOnce(report)
    vi.mocked(rerunHistoricalReport).mockResolvedValueOnce({ id: 'task-2', status: 'queued', progress: 12, stage: 'request_validation', stage_label: '请求校验' })
    vi.mocked(waitForAnalysis).mockResolvedValueOnce(rerunReport)
    vi.mocked(fetchReportHistory).mockResolvedValueOnce({ items: [historyItem], total: 1, limit: 20, offset: 0 })

    expect(await history.openHistory('report-1')).toBe(report)
    expect(await history.rerunHistory('report-1', vi.fn())).toBe(rerunReport)
    expect(rerunHistoricalReport).toHaveBeenCalledWith('report-1')
    expect(history.rerunningReportId.value).toBe('')
  })
})
