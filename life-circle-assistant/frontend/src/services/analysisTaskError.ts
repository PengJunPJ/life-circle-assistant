import type { AnalysisTask } from '../types/report'

export class AnalysisTaskTerminalError extends Error {
  constructor(public task: AnalysisTask) {
    super(task.status === 'cancelled' ? '体检任务已取消' : task.error || '体检任务失败')
    this.name = 'AnalysisTaskTerminalError'
  }
}
