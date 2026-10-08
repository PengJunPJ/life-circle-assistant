import { ref } from 'vue'
import { DEFAULT_CENTER } from '../constants/facilities'
import { convertCoordinate, reverseGeocode, searchAddressCandidates } from '../services/analysisApi'
import type { AnalysisCenter, CenterSelectionMethod, CoordinateSystem, LocationCandidate } from '../types/location'

const DEFAULT_ADDRESS = '广州市黄埔区红山街道海韵东路离线样例中心'

export function useAnalysisCenter() {
  const center = ref<AnalysisCenter>({
    ...DEFAULT_CENTER,
    address: DEFAULT_ADDRESS,
    selectionMethod: 'default',
    source: 'local_snapshot',
    supportStatus: 'supported',
  })
  const addressQuery = ref(DEFAULT_ADDRESS)
  const candidates = ref<LocationCandidate[]>([])
  const coordinateLng = ref(DEFAULT_CENTER.lng.toFixed(6))
  const coordinateLat = ref(DEFAULT_CENTER.lat.toFixed(6))
  const coordinateSystem = ref<CoordinateSystem>('bd09')
  const coordinateConversionNote = ref('')
  const searching = ref(false)
  const resolving = ref(false)
  const error = ref('')

  function validateCoordinates(lng: number, lat: number, system: CoordinateSystem = 'bd09') {
    const label = system === 'wgs84' ? 'WGS84' : system === 'gcj02' ? 'GCJ-02' : 'BD-09'
    if (!Number.isFinite(lng) || !Number.isFinite(lat)) return `请输入数字格式的 ${label} 经纬度`
    if (lng < -180 || lng > 180 || lat < -90 || lat > 90) return `请输入合法范围内的 ${label} 经纬度`
    return ''
  }

  function commitCenter(
    location: { lng: number; lat: number; address: string; source: string },
    selectionMethod: CenterSelectionMethod,
  ) {
    center.value = {
      lng: location.lng,
      lat: location.lat,
      address: location.address || `BD-09：${location.lng.toFixed(6)}, ${location.lat.toFixed(6)}`,
      selectionMethod,
      source: location.source,
      supportStatus: 'supported',
    }
    addressQuery.value = center.value.address
    coordinateLng.value = location.lng.toFixed(6)
    coordinateLat.value = location.lat.toFixed(6)
    coordinateSystem.value = 'bd09'
    coordinateConversionNote.value = ''
    candidates.value = []
    error.value = ''
  }

  async function searchCandidates() {
    const query = addressQuery.value.trim()
    if (!query) {
      error.value = '请输入要搜索的地址'
      candidates.value = []
      return false
    }
    searching.value = true
    error.value = ''
    try {
      candidates.value = await searchAddressCandidates(query)
      if (!candidates.value.length) {
        error.value = '没有找到可选择的地址候选'
        return false
      }
      return true
    } catch (reason: any) {
      candidates.value = []
      error.value = reason?.message || '地址无法解析，请检查后重试'
      return false
    } finally {
      searching.value = false
    }
  }

  function selectCandidate(candidate: LocationCandidate) {
    commitCenter(candidate, 'address')
  }

  function restoreCenter(location: {
    lng: number
    lat: number
    address: string
    source: string
    selectionMethod: CenterSelectionMethod
  }) {
    commitCenter(location, location.selectionMethod)
  }

  async function selectCoordinates(lng: number, lat: number, selectionMethod: 'map' | 'coordinates') {
    const validationError = validateCoordinates(lng, lat)
    if (validationError) {
      center.value = { ...center.value, supportStatus: 'unsupported' }
      error.value = validationError
      return false
    }
    resolving.value = true
    error.value = ''
    coordinateLng.value = lng.toFixed(6)
    coordinateLat.value = lat.toFixed(6)
    center.value = {
      lng,
      lat,
      address: `BD-09：${lng.toFixed(6)}, ${lat.toFixed(6)}（地址确认中）`,
      selectionMethod,
      source: 'pending',
      supportStatus: 'checking',
    }
    try {
      const response = await reverseGeocode(lng, lat)
      commitCenter({ ...response.result, source: response.source }, selectionMethod)
      return true
    } catch (reason: any) {
      center.value = { ...center.value, supportStatus: 'unsupported' }
      error.value = reason?.message || '该位置无法确认或超出当前支持范围'
      return false
    } finally {
      resolving.value = false
    }
  }

  function selectMapPoint(lng: number, lat: number) {
    coordinateConversionNote.value = ''
    return selectCoordinates(lng, lat, 'map')
  }

  async function applyCoordinateInput() {
    const lng = Number(coordinateLng.value)
    const lat = Number(coordinateLat.value)
    const inputSystem = coordinateSystem.value
    const validationError = validateCoordinates(lng, lat, inputSystem)
    if (validationError) {
      center.value = { ...center.value, supportStatus: 'unsupported' }
      error.value = validationError
      coordinateConversionNote.value = ''
      return false
    }
    if (inputSystem === 'bd09') {
      coordinateConversionNote.value = ''
      return selectCoordinates(lng, lat, 'coordinates')
    }

    resolving.value = true
    error.value = ''
    coordinateConversionNote.value = ''
    try {
      const conversion = await convertCoordinate(lng, lat, inputSystem)
      const selected = await selectCoordinates(
        conversion.result.lng,
        conversion.result.lat,
        'coordinates',
      )
      if (selected) {
        const inputLabel = inputSystem === 'wgs84' ? 'WGS84' : 'GCJ-02'
        coordinateConversionNote.value = `已通过百度 Geoconv V2 将 ${inputLabel} 转换为 BD-09`
      }
      return selected
    } catch (reason: any) {
      center.value = { ...center.value, supportStatus: 'unsupported' }
      error.value = reason?.message || '坐标转换失败，请检查真实百度地图服务后重试'
      return false
    } finally {
      resolving.value = false
    }
  }

  return {
    center,
    addressQuery,
    candidates,
    coordinateLng,
    coordinateLat,
    coordinateSystem,
    coordinateConversionNote,
    searching,
    resolving,
    error,
    searchCandidates,
    selectCandidate,
    restoreCenter,
    selectMapPoint,
    applyCoordinateInput,
  }
}
