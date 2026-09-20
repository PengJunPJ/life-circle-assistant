import { ref } from 'vue'
import { fetchReportHistory, getHistoricalReport, rerunHistoricalReport, waitForAnalysis } from '../services/analysisApi'
import type { HistoryReportItem } from '../types/history'
import type { Report } from '../types/report'

export function useReportHistory() {
  const items = ref<HistoryReportItem[]>([])
  const total = ref(0)
  const loading = ref(false)
  const error = ref('')
  const openingReportId = ref('')
  const rerunningReportId = ref('')

  async function loadHistory() {
    loading.value = true
    error.value = ''
    try {
      const response = await fetchReportHistory()
      items.value = response.items
      total.value = response.total
    } catch (cause: any) {
      error.value = cause?.message || '历史报告加载失败'
    } finally {
      loading.value = false
    }
  }

  async function openHistory(reportId: string): Promise<Report | null> {
    openingReportId.value = reportId
    error.value = ''
    try {
      return await getHistoricalReport(reportId)
    } catch (cause: any) {
      error.value = cause?.message || '历史报告打开失败'
      return null
    } finally {
      openingReportId.value = ''
    }
  }

  async function rerunHistory(reportId: string, onProgress: (value: number) => void): Promise<Report | null> {
    rerunningReportId.value = reportId
    error.value = ''
    try {
      const task = await rerunHistoricalReport(reportId)
      const report = await waitForAnalysis(task, onProgress)
      await loadHistory()
      return report
    } catch (cause: any) {
      error.value = cause?.message || '历史任务重新运行失败'
      return null
    } finally {
      rerunningReportId.value = ''
    }
  }

  return {
    items,
    total,
    loading,
    error,
    openingReportId,
    rerunningReportId,
    loadHistory,
    openHistory,
    rerunHistory,
  }
}
