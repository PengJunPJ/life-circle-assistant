import { afterEach, describe, expect, it, vi } from 'vitest'
import { downloadReportExport } from './analysisApi'
import { triggerBlobDownload } from '../utils/report'
vi.mock('../utils/report', async importOriginal => ({ ...await importOriginal<typeof import('../utils/report')>(), triggerBlobDownload: vi.fn() }))
afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks() })
describe('独立标准GeoJSON下载协议', () => {
  it.each(['geojson-wgs84', 'geojson'] as const)('格式%s仅请求对应出口，保留后端下载内容', async format => {
    const blob = new Blob(['{"type":"FeatureCollection","features":[]}'], { type: 'application/geo+json' })
    const fetch = vi.fn().mockResolvedValue({ ok: true, headers: new Headers(), blob: async () => blob }); vi.stubGlobal('fetch', fetch)
    const filename = await downloadReportExport('report/id', format)
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining(`/api/reports/report%2Fid/exports/${format}`))
    expect(filename).toBe(format === 'geojson-wgs84' ? '生活圈体检-report/i-WGS84.geojson' : '生活圈体检-report/i.geojson')
    expect(triggerBlobDownload).toHaveBeenCalledWith(blob, filename)
  })
  it('标准导出响应失败不会触发文件下载', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, json: async () => ({ detail: '坐标转换结果不可用' }) }))
    await expect(downloadReportExport('report', 'geojson-wgs84')).rejects.toThrow('坐标转换结果不可用')
    expect(triggerBlobDownload).not.toHaveBeenCalled()
  })
})
