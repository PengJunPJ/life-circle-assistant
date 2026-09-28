import { computed, ref } from 'vue'
import { fetchReportHistory, getHistoricalReport, rerunHistoricalReport, waitForAnalysis } from '../services/analysisApi'
import type { HistoryReportItem } from '../types/history'
import type { Report } from '../types/report'

const PAGE_SIZE = 20
const SEARCH_DEBOUNCE_MS = 300

export function useReportHistory() {
  const items = ref<HistoryReportItem[]>([])
  const total = ref(0)
  const loading = ref(false)
  const loadingMore = ref(false)
  const error = ref('')
  const openingReportId = ref('')
  const rerunningReportId = ref('')
  const query = ref('')
  const hasMore = computed(() => items.value.length < total.value)

  let searchTimer: ReturnType<typeof setTimeout> | null = null
  let requestToken = 0

  async function fetchPage(offset: number, keyword: string, token: number) {
    const trimmed = keyword.trim()
    return fetchReportHistory(PAGE_SIZE, offset, trimmed || undefined).then((response) => {
      if (token !== requestToken) return null
      return response
    })
  }

  async function loadHistory() {
    const token = ++requestToken
    loading.value = true
    error.value = ''
    try {
      const response = await fetchPage(0, query.value, token)
      if (!response) return
      items.value = response.items
      total.value = response.total
    } catch (cause: any) {
      if (token !== requestToken) return
      error.value = cause?.message || '历史报告加载失败'
    } finally {
      if (token === requestToken) loading.value = false
    }
  }

  async function loadMoreHistory() {
    if (loading.value || loadingMore.value || !hasMore.value) return
    const token = requestToken
    const offset = items.value.length
    loadingMore.value = true
    error.value = ''
    try {
      const response = await fetchPage(offset, query.value, token)
      if (!response) return
      const existing = new Set(items.value.map((item) => item.report_id))
      const appended = response.items.filter((item) => !existing.has(item.report_id))
      items.value = [...items.value, ...appended]
      total.value = response.total
    } catch (cause: any) {
      if (token !== requestToken) return
      error.value = cause?.message || '历史报告加载失败'
    } finally {
      if (token === requestToken) loadingMore.value = false
    }
  }

  function searchHistory(keyword: string) {
    query.value = keyword
    if (searchTimer) clearTimeout(searchTimer)
    searchTimer = setTimeout(() => {
      searchTimer = null
      void loadHistory()
    }, SEARCH_DEBOUNCE_MS)
  }

  function cancelPendingSearch() {
    if (searchTimer) {
      clearTimeout(searchTimer)
      searchTimer = null
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
    loadingMore,
    error,
    openingReportId,
    rerunningReportId,
    query,
    hasMore,
    loadHistory,
    loadMoreHistory,
    searchHistory,
    cancelPendingSearch,
    openHistory,
    rerunHistory,
  }
}
