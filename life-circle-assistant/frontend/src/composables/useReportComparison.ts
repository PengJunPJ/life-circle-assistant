import { ref } from 'vue'
import { compareHistoricalReports } from '../services/analysisApi'
import type { ReportComparison } from '../types/comparison'

export function useReportComparison() {
  const selectedReportIds = ref<string[]>([])
  const comparison = ref<ReportComparison | null>(null)
  const loading = ref(false)
  const error = ref('')

  function toggleReport(reportId: string) {
    error.value = ''
    const index = selectedReportIds.value.indexOf(reportId)
    if (index >= 0) {
      selectedReportIds.value.splice(index, 1)
      return
    }
    if (selectedReportIds.value.length >= 2) {
      error.value = '一次只能比较两份报告，请先取消一份已选报告。'
      return
    }
    selectedReportIds.value.push(reportId)
  }

  async function compareSelection(): Promise<ReportComparison | null> {
    error.value = ''
    if (selectedReportIds.value.length !== 2) {
      error.value = '请选择两份不同的已完成报告进行比较。'
      return null
    }
    const [leftId, rightId] = selectedReportIds.value
    if (!leftId || !rightId || leftId === rightId) {
      error.value = '请选择两份不同的已完成报告进行比较。'
      return null
    }
    loading.value = true
    try {
      comparison.value = await compareHistoricalReports([leftId, rightId])
      return comparison.value
    } catch (cause: any) {
      error.value = cause?.message || '报告比较失败'
      comparison.value = null
      return null
    } finally {
      loading.value = false
    }
  }

  function closeComparison() {
    comparison.value = null
  }

  return {
    selectedReportIds,
    comparison,
    loading,
    error,
    toggleReport,
    compareSelection,
    closeComparison,
  }
}
