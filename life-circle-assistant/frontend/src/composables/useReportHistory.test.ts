import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
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

function makeItem(id: string, address: string) {
  return { ...historyItem, report_id: id, task_id: `task-${id}`, center: { ...historyItem.center, address } }
}

describe('useReportHistory', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

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

  it('触底加载下一页时追加并去重', async () => {
    const history = useReportHistory()
    const page1 = Array.from({ length: 20 }, (_, i) => makeItem(`r${i}`, `地址${i}`))
    const page2 = [page1[19], makeItem('r20', '地址20'), makeItem('r21', '地址21')]
    vi.mocked(fetchReportHistory)
      .mockResolvedValueOnce({ items: page1, total: 22, limit: 20, offset: 0 })
      .mockResolvedValueOnce({ items: page2, total: 22, limit: 20, offset: 20 })

    await history.loadHistory()
    expect(history.items.value).toHaveLength(20)
    expect(history.hasMore.value).toBe(true)

    await history.loadMoreHistory()
    expect(fetchReportHistory).toHaveBeenLastCalledWith(20, 20, undefined)
    expect(history.items.value).toHaveLength(22)
    expect(history.items.value.map((i) => i.report_id)).toEqual([
      ...page1.map((i) => i.report_id),
      'r20',
      'r21',
    ])
    expect(history.hasMore.value).toBe(false)
    expect(history.loadingMore.value).toBe(false)

    await history.loadMoreHistory()
    expect(fetchReportHistory).toHaveBeenCalledTimes(2)
  })

  it('搜索关键词防抖后重新拉取第一页', async () => {
    const history = useReportHistory()
    vi.mocked(fetchReportHistory).mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 })

    history.searchHistory('海淀')
    expect(fetchReportHistory).not.toHaveBeenCalled()
    vi.advanceTimersByTime(299)
    expect(fetchReportHistory).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    await Promise.resolve()
    expect(fetchReportHistory).toHaveBeenCalledWith(20, 0, '海淀')
    expect(history.query.value).toBe('海淀')
  })

  it('连续输入只触发一次搜索请求', async () => {
    const history = useReportHistory()
    vi.mocked(fetchReportHistory).mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 })

    history.searchHistory('海')
    vi.advanceTimersByTime(100)
    history.searchHistory('海淀')
    vi.advanceTimersByTime(100)
    history.searchHistory('海淀区')
    vi.advanceTimersByTime(300)
    await Promise.resolve()
    expect(fetchReportHistory).toHaveBeenCalledTimes(1)
    expect(fetchReportHistory).toHaveBeenCalledWith(20, 0, '海淀区')
    expect(history.query.value).toBe('海淀区')
  })

  it('空关键词不传 q 参数', async () => {
    const history = useReportHistory()
    vi.mocked(fetchReportHistory).mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 })
    history.searchHistory('   ')
    vi.advanceTimersByTime(300)
    await Promise.resolve()
    expect(fetchReportHistory).toHaveBeenCalledWith(20, 0, undefined)
  })
})
