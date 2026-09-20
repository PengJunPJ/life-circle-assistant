import { ref, watch, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { simulateFacility } from '../services/analysisApi'
import type { RecommendationCandidate } from '../types/recommendations'
import type { Report } from '../types/report'
import type { SimulationLocation, SimulationResult } from '../types/simulation'

export function useSimulation(report: Ref<Report | null>) {
  const category = ref('')
  const location = ref<SimulationLocation | null>(null)
  const result = ref<SimulationResult | null>(null)
  const loading = ref(false)
  const picking = ref(false)
  const error = ref('')

  watch(() => report.value?.report_id, () => resetForReport(), { immediate: true })

  function resetForReport() {
    category.value = report.value?.parameters.categories[0] || ''
    location.value = null
    result.value = null
    loading.value = false
    picking.value = false
    error.value = ''
  }

  function selectCategory(value: string) {
    if (category.value === value) return
    category.value = value
    if (location.value?.selectionMethod === 'recommendation') location.value = null
    result.value = null
    error.value = ''
  }

  function beginMapPick() {
    if (!report.value) return
    if (!category.value) category.value = report.value.parameters.categories[0] || ''
    picking.value = true
    result.value = null
    error.value = ''
    ElMessage.info('请在地图上点击假设设施位置')
  }

  function selectMapLocation(lng: number, lat: number) {
    location.value = { lng, lat, selectionMethod: 'map' }
    picking.value = false
    result.value = null
    error.value = ''
  }

  async function simulateCandidate(categoryValue: string, candidate: RecommendationCandidate) {
    category.value = categoryValue
    location.value = {
      lng: candidate.lng,
      lat: candidate.lat,
      selectionMethod: 'recommendation',
      candidateId: candidate.id,
    }
    result.value = null
    await run()
  }

  async function run() {
    if (!report.value || !category.value || !location.value || loading.value) return
    loading.value = true
    error.value = ''
    try {
      result.value = await simulateFacility(report.value.report_id, {
        category: category.value,
        lng: location.value.lng,
        lat: location.value.lat,
        selection_method: location.value.selectionMethod,
        candidate_id: location.value.candidateId,
      })
      ElMessage.success('新增设施改善效果已完成计算')
    } catch (cause: any) {
      error.value = cause?.message || '规划模拟失败'
      ElMessage.error(error.value)
    } finally {
      loading.value = false
    }
  }

  function clear() {
    location.value = null
    result.value = null
    picking.value = false
    error.value = ''
  }

  return {
    category,
    location,
    result,
    loading,
    picking,
    error,
    selectCategory,
    beginMapPick,
    selectMapLocation,
    simulateCandidate,
    run,
    clear,
  }
}
