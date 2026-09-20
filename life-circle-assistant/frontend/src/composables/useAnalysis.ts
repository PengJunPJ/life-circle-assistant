import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { DEFAULT_CATEGORIES, DEFAULT_CENTER } from '../constants/facilities'
import { createAnalysis, geocodeAddress, waitForAnalysis } from '../services/analysisApi'
import type { AnalysisMode, AnalysisMinutes, Report } from '../types/report'

export function useAnalysis(realMapReady: Ref<boolean>) {
  const address = ref('广州市黄埔区萝岗街道样例社区')
  const mode = ref<AnalysisMode>('demo')
  const minutes = ref<AnalysisMinutes>(15)
  const visibleCategories = ref([...DEFAULT_CATEGORIES])
  const showSparse = ref(true)
  const loading = ref(false)
  const progress = ref(0)
  const report = ref<Report | null>(null)
  const centerPoint = ref({ ...DEFAULT_CENTER })

  async function runAnalysis() {
    if (loading.value) return
    loading.value = true
    progress.value = 18
    report.value = null
    try {
      if (realMapReady.value && address.value.trim()) {
        const geocode = await geocodeAddress(address.value.trim())
        if (geocode.result?.location) centerPoint.value = geocode.result.location
      }
      const task = await createAnalysis({
        lng: centerPoint.value.lng,
        lat: centerPoint.value.lat,
        minutes: minutes.value,
        mode: mode.value,
        categories: visibleCategories.value,
      })
      progress.value = 52
      report.value = await waitForAnalysis(task, (value) => { progress.value = value })
      progress.value = 100
      ElMessage.success(report.value.source === 'baidu' ? '百度地图真实体检报告已生成' : '本地快照体检报告已生成')
    } catch (error: any) {
      ElMessage.error(error?.message || '服务暂不可用，请检查后端是否启动')
    } finally {
      loading.value = false
    }
  }

  function toggleCategory(category: string) {
    visibleCategories.value = visibleCategories.value.includes(category)
      ? visibleCategories.value.filter((item) => item !== category)
      : [...visibleCategories.value, category]
  }

  return { address, mode, minutes, visibleCategories, showSparse, loading, progress, report, runAnalysis, toggleCategory }
}
