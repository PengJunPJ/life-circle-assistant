// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cancelAnalysisTask, resumeAnalysisTask, retryAnalysisTask, waitForAnalysis } from './analysisApi'
import type { AnalysisTask } from '../types/report'
const task: AnalysisTask = { id: 'task-one', status: 'running', progress: 40, stage: 'walking', stage_label: '计算中' }

describe('任务终态与取消协议', () => {
  beforeEach(() => { vi.useFakeTimers(); vi.stubGlobal('fetch', vi.fn()) })
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })
  it('服务端取消后停止轮询并提供可识别错误', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ ...task, status: 'cancelled' })))
    const promise = expect(waitForAnalysis(task, vi.fn())).rejects.toThrow('已取消')
    await vi.advanceTimersByTimeAsync(200)
    await promise
    expect(fetch).toHaveBeenCalledTimes(1)
  })
  it('已完成却缺失报告不被当作成功', async () => {
    await expect(waitForAnalysis({ ...task, status: 'completed' }, vi.fn())).rejects.toThrow('报告数据缺失')
    expect(fetch).not.toHaveBeenCalled()
  })
  it('离开页面终止本地等待，不暗示后台已取消', async () => {
    const controller = new AbortController()
    controller.abort()
    await expect(waitForAnalysis(task, vi.fn(), controller.signal)).rejects.toMatchObject({ name: 'AbortError' })
    expect(fetch).not.toHaveBeenCalled()
  })
  it('取消和重试都显式调用服务端接口', async () => {
    vi.mocked(fetch).mockImplementation(async () => new Response(JSON.stringify(task)))
    await cancelAnalysisTask(task.id)
    await retryAnalysisTask(task.id)
    await resumeAnalysisTask(task.id)
    expect(fetch).toHaveBeenNthCalledWith(1, expect.stringContaining('/api/analyze/task-one/cancel'), { method: 'POST' })
    expect(fetch).toHaveBeenNthCalledWith(2, expect.stringContaining('/api/analyze/task-one/retry'), { method: 'POST' })
    expect(fetch).toHaveBeenNthCalledWith(3, expect.stringContaining('/api/analyze/task-one/resume'), { method: 'POST' })
  })
})
