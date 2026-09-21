import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  searchAddressCandidates: vi.fn(),
  reverseGeocode: vi.fn(),
  createAnalysis: vi.fn(),
  waitForAnalysis: vi.fn(),
}))

vi.mock('../services/analysisApi', () => api)
vi.mock('element-plus/es/components/message/index', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}))

import { useAnalysis } from './useAnalysis'
import { useAnalysisCenter } from './useAnalysisCenter'

function reportFor(params: any) {
  return {
    source: params.center_selection_method === 'address' ? 'baidu' : 'local_snapshot',
    center: {
      lng: params.lng,
      lat: params.lat,
      address: params.center_address,
      selection_method: params.center_selection_method,
    },
  } as any
}

async function submitCurrentCenter(location = useAnalysisCenter()) {
  const analysis = useAnalysis(location.center)
  api.createAnalysis.mockResolvedValue({ id: 'task-1', status: 'queued', progress: 0 })
  api.waitForAnalysis.mockImplementation(async () => {
    const calls = api.createAnalysis.mock.calls
    return reportFor(calls[calls.length - 1]?.[0])
  })
  await analysis.runAnalysis()
  const calls = api.createAnalysis.mock.calls
  return { location, analysis, submitted: calls[calls.length - 1]?.[0] }
}

describe('统一分析中心选点流程', () => {
  beforeEach(() => vi.clearAllMocks())

  it('从地址候选选择后使用同一地址和坐标提交并生成报告', async () => {
    api.searchAddressCandidates.mockResolvedValue([
      { lng: 113.501, lat: 23.111, address: '广州市黄埔区候选一', source: 'real_api', provider: 'baidu' },
      { lng: 113.502, lat: 23.112, address: '广州市黄埔区候选二', source: 'real_api', provider: 'baidu' },
    ])
    const location = useAnalysisCenter()
    location.addressQuery.value = '黄埔区候选'

    expect(await location.searchCandidates()).toBe(true)
    expect(location.candidates.value).toHaveLength(2)
    location.selectCandidate(location.candidates.value[1])
    const result = await submitCurrentCenter(location)

    expect(result.submitted).toMatchObject({
      lng: 113.502,
      lat: 23.112,
      mode: 'analysis',
      center_address: '广州市黄埔区候选二',
      center_selection_method: 'address',
    })
    expect(result.analysis.report.value?.center).toMatchObject({
      lng: result.location.center.value.lng,
      lat: result.location.center.value.lat,
      address: result.location.center.value.address,
    })
  })

  it('地图点击经逆地理编码确认后同步标记请求和报告', async () => {
    api.reverseGeocode.mockResolvedValue({
      source: 'local_snapshot',
      provider: 'snapshot',
      result: { lng: 113.489, lat: 23.108, address: '萝岗街道样例社区（地图选点）' },
    })
    const location = useAnalysisCenter()

    expect(await location.selectMapPoint(113.489, 23.108)).toBe(true)
    const result = await submitCurrentCenter(location)

    expect(result.location.center.value.selectionMethod).toBe('map')
    expect(result.submitted).toMatchObject({
      lng: 113.489,
      lat: 23.108,
      center_address: '萝岗街道样例社区（地图选点）',
      center_selection_method: 'map',
    })
    expect(result.analysis.report.value?.center.lng).toBe(result.location.center.value.lng)
  })

  it('合法 BD-09 坐标确认后同步输入请求和报告', async () => {
    api.reverseGeocode.mockResolvedValue({
      source: 'real_api',
      provider: 'baidu',
      result: { lng: 113.49, lat: 23.109, address: '广州市黄埔区坐标确认地址' },
    })
    const location = useAnalysisCenter()
    location.coordinateLng.value = '113.490000'
    location.coordinateLat.value = '23.109000'

    expect(await location.applyCoordinateInput()).toBe(true)
    const result = await submitCurrentCenter(location)

    expect(result.submitted.center_selection_method).toBe('coordinates')
    expect(result.submitted.center_address).toBe('广州市黄埔区坐标确认地址')
    expect(result.analysis.report.value?.center).toMatchObject({ lng: 113.49, lat: 23.109 })
  })

  it('无效坐标和超出离线支持范围时阻止分析', async () => {
    const invalid = useAnalysisCenter()
    invalid.coordinateLng.value = '181'
    invalid.coordinateLat.value = '23.1'
    expect(await invalid.applyCoordinateInput()).toBe(false)
    expect(invalid.error.value).toContain('合法范围')
    expect(api.reverseGeocode).not.toHaveBeenCalled()

    api.reverseGeocode.mockRejectedValue(new Error('超出本地快照支持范围'))
    expect(await invalid.selectMapPoint(113.6, 23.2)).toBe(false)
    expect(invalid.center.value.supportStatus).toBe('unsupported')
    const analysis = useAnalysis(invalid.center)
    await analysis.runAnalysis()
    expect(api.createAnalysis).not.toHaveBeenCalled()
  })
})
