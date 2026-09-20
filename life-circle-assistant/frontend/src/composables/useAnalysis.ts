import { ref, watch, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { DEFAULT_CATEGORIES } from '../constants/facilities'
import { createAnalysis, waitForAnalysis } from '../services/analysisApi'
import type { AnalysisCenter } from '../types/location'
import type { AnalysisMode, AnalysisMinutes, Report } from '../types/report'

export function useAnalysis(center: Ref<AnalysisCenter>) {
  const mode = ref<AnalysisMode>('demo')
  const minutes = ref<AnalysisMinutes>(15)
  const visibleCategories = ref([...DEFAULT_CATEGORIES])
  const showNormal = ref(false)
  const showSparse = ref(true)
  const showCritical = ref(true)
  const loading = ref(false)
  const progress = ref(0)
  const report = ref<Report | null>(null)
  const error = ref('')

  watch(center, (nextCenter) => {
    if (report.value
      && report.value.center.lng === nextCenter.lng
      && report.value.center.lat === nextCenter.lat
      && report.value.center.address === nextCenter.address) return
    // 新选点不能继续展示旧中心点的报告，避免标记、请求和报告互相矛盾。
    report.value = null
    progress.value = 0
  })

  function applyReport(selected: Report) {
    error.value = ''
    report.value = selected
    center.value = {
      lng: selected.center.lng,
      lat: selected.center.lat,
      address: selected.center.address,
      selectionMethod: selected.center.selection_method || selected.parameters.center_selection_method || 'default',
      source: selected.center.source || selected.source,
      supportStatus: 'supported',
    }
    mode.value = selected.parameters.mode
    minutes.value = selected.parameters.minutes
    visibleCategories.value = [...selected.parameters.categories]
    progress.value = 100
  }

  async function runAnalysis() {
    if (loading.value) return
    loading.value = true
    error.value = ''
    progress.value = 18
    report.value = null
    try {
      if (center.value.supportStatus !== 'supported') throw new Error('请先选择当前支持范围内的分析中心点')
      if (!visibleCategories.value.length) throw new Error('请至少选择一种民生设施类别')
      const task = await createAnalysis({
        lng: center.value.lng,
        lat: center.value.lat,
        minutes: minutes.value,
        mode: mode.value,
        categories: visibleCategories.value,
        center_address: center.value.address,
        center_selection_method: center.value.selectionMethod,
      })
      progress.value = 52
      const completedReport = await waitForAnalysis(task, (value) => { progress.value = value })
      applyReport(completedReport)
      progress.value = 100
      ElMessage.success(completedReport.source === 'baidu' ? '百度地图真实体检报告已生成' : '本地快照体检报告已生成')
    } catch (caught: any) {
      const message = caught?.message || '服务暂不可用，请检查后端是否启动'
      ElMessage.error(message)
      // 除视觉 Toast 外保留可观察状态，供页面 live region 向辅助技术播报失败原因。
      error.value = message
    } finally {
      loading.value = false
    }
  }

  function toggleCategory(category: string) {
    visibleCategories.value = visibleCategories.value.includes(category)
      ? visibleCategories.value.filter((item) => item !== category)
      : [...visibleCategories.value, category]
  }

  return {
    mode,
    minutes,
    visibleCategories,
    showNormal,
    showSparse,
    showCritical,
    loading,
    progress,
    report,
    error,
    runAnalysis,
    toggleCategory,
    applyReport,
  }
}
