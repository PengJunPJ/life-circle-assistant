import { computed, ref, watch, type Ref } from 'vue'
import ElMessage from 'element-plus/es/components/message/index'
import { ALL_CATEGORIES, DEFAULT_CATEGORIES } from '../constants/facilities'
import { createAnalysis, waitForAnalysis } from '../services/analysisApi'
import type { AnalysisCenter } from '../types/location'
import type { AnalysisMode, AnalysisMinutes, Report } from '../types/report'

export function useAnalysis(center: Ref<AnalysisCenter>) {
  // 页面默认采用正式分析密度；地图数据是否实时由后端 provider 决定。
  const mode = ref<AnalysisMode>('analysis')
  const minutes = ref<AnalysisMinutes>(15)
  const analysisCategories = ref([...DEFAULT_CATEGORIES])
  const visibleCategories = ref([...DEFAULT_CATEGORIES])
  const showNormal = ref(false)
  const showSparse = ref(true)
  const showCritical = ref(true)
  const loading = ref(false)
  const progress = ref(0)
  const progressLabel = ref('')
  const report = ref<Report | null>(null)
  const error = ref('')
  const supplementCategories = computed(() => {
    const original = report.value
    if (!original || original.center.lng !== center.value.lng || original.center.lat !== center.value.lat
      || original.parameters.minutes !== minutes.value || original.parameters.mode !== mode.value
      || !original.parameters.categories.every(category => analysisCategories.value.includes(category))) return []
    return ALL_CATEGORIES.filter(category => analysisCategories.value.includes(category) && !original.parameters.categories.includes(category))
  })

  watch(center, (nextCenter) => {
    if (report.value
      && report.value.center.lng === nextCenter.lng
      && report.value.center.lat === nextCenter.lat
      && report.value.center.address === nextCenter.address) return
    // 新选点不能继续展示旧中心点的报告，避免标记、请求和报告互相矛盾。
    report.value = null
    visibleCategories.value = [...analysisCategories.value]
    progress.value = 0
    progressLabel.value = ''
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
    analysisCategories.value = [...selected.parameters.categories]
    visibleCategories.value = [...selected.parameters.categories]
    progress.value = 100
  }

  async function executeAnalysis(parameters: Parameters<typeof createAnalysis>[0], retainReport = false) {
    if (loading.value) return false
    loading.value = true
    error.value = ''
    progress.value = 18
    progressLabel.value = ''
    if (!retainReport) {
      report.value = null
      visibleCategories.value = [...parameters.categories]
    }
    try {
      if (center.value.supportStatus !== 'supported') throw new Error('请先选择当前支持范围内的分析中心点')
      if (!parameters.categories.length) throw new Error('请至少选择一种民生设施类别')
      const task = await createAnalysis(parameters)
      progress.value = 52
      const completedReport = await waitForAnalysis(task, (value, stageLabel) => {
        progress.value = value
        progressLabel.value = stageLabel
      })
      applyReport(completedReport)
      progress.value = 100
      progressLabel.value = ''
      ElMessage.success(completedReport.source === 'baidu' ? '百度地图真实体检报告已生成' : '本地快照体检报告已生成')
      return true
    } catch (caught: any) {
      const message = caught?.message || '服务暂不可用，请检查后端是否启动'
      ElMessage.error(message)
      // 除视觉 Toast 外保留可观察状态，供页面 live region 向辅助技术播报失败原因。
      error.value = message
      return false
    } finally {
      loading.value = false
    }
  }

  function runAnalysis() {
    if (supplementCategories.value.length) return supplementAnalysis(supplementCategories.value)
    return executeAnalysis({
      lng: center.value.lng,
      lat: center.value.lat,
      minutes: minutes.value,
      mode: mode.value,
      categories: [...analysisCategories.value],
      center_address: center.value.address,
      center_selection_method: center.value.selectionMethod,
    }, Boolean(report.value))
  }

  async function supplementAnalysis(categories: string[]) {
    const original = report.value
    if (!original || loading.value) return false
    const added = ALL_CATEGORIES.filter(category => categories.includes(category) && !original.parameters.categories.includes(category))
    if (!added.length) return false
    const previousVisible = [...visibleCategories.value]
    const completed = await executeAnalysis({
      ...original.parameters,
      lng: original.center.lng,
      lat: original.center.lat,
      center_address: original.center.address,
      center_selection_method: original.center.selection_method || original.parameters.center_selection_method || 'default',
      categories: ALL_CATEGORIES.filter(category => original.parameters.categories.includes(category) || added.includes(category)),
    }, true)
    if (completed) setVisibleCategories([...previousVisible, ...added])
    return completed
  }

  function setVisibleCategories(categories: string[]) {
    if (loading.value) return
    const available = report.value?.parameters.categories ?? ALL_CATEGORIES
    visibleCategories.value = ALL_CATEGORIES.filter(category => categories.includes(category) && available.includes(category))
  }

  function setAnalysisCategories(categories: string[]) {
    if (loading.value) return
    analysisCategories.value = ALL_CATEGORIES.filter(category => categories.includes(category))
    if (!report.value) visibleCategories.value = [...analysisCategories.value]
  }

  function toggleCategory(category: string) {
    setVisibleCategories(visibleCategories.value.includes(category)
      ? visibleCategories.value.filter((item) => item !== category)
      : [...visibleCategories.value, category])
  }

  return {
    mode,
    minutes,
    analysisCategories,
    supplementCategories,
    visibleCategories,
    showNormal,
    showSparse,
    showCritical,
    loading,
    progress,
    progressLabel,
    report,
    error,
    runAnalysis,
    supplementAnalysis,
    setVisibleCategories,
    setAnalysisCategories,
    toggleCategory,
    applyReport,
  }
}
