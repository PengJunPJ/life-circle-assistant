// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ReportExportMenu from './ReportExportMenu.vue'
import { downloadReportExport } from '../services/analysisApi'
vi.mock('../services/analysisApi', () => ({ downloadReportExport: vi.fn() }))
beforeEach(() => { vi.resetAllMocks(); vi.mocked(downloadReportExport).mockResolvedValue('生活圈-WGS84.geojson') })
const option = (wrapper: ReturnType<typeof mount>, label: string) => wrapper.findAll('button').find(value => value.get('strong').text() === label)!
describe('标准WGS84与BD09导出入口', () => {
  it('标准格式有近似逆转换披露，按独立端点导出，原BD09出口保持可用', async () => {
    const wrapper = mount(ReportExportMenu, { props: { reportId: 'report/id' } })
    expect(option(wrapper, '标准 GeoJSON（WGS84）').text()).toContain('近似坐标逆转换')
    expect(option(wrapper, 'GeoJSON').text()).toContain('BD-09')
    await option(wrapper, '标准 GeoJSON（WGS84）').trigger('click'); await flushPromises()
    expect(downloadReportExport).toHaveBeenCalledWith('report/id', 'geojson-wgs84')
    expect(wrapper.get('[role="status"]').text()).toContain('生活圈-WGS84.geojson')
    await option(wrapper, 'GeoJSON').trigger('click'); await flushPromises()
    expect(downloadReportExport).toHaveBeenLastCalledWith('report/id', 'geojson')
  })
  it('标准导出期间所有入口禁重复请求，失败显示服务端原因', async () => {
    let reject!: (reason: Error) => void
    vi.mocked(downloadReportExport).mockReturnValue(new Promise((_resolve, failure) => { reject = failure }))
    const wrapper = mount(ReportExportMenu, { props: { reportId: 'report' } })
    await option(wrapper, '标准 GeoJSON（WGS84）').trigger('click')
    expect(wrapper.findAll('button').every(item => item.attributes('disabled') !== undefined)).toBe(true)
    reject(new Error('标准导出坐标校验未通过')); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toBe('标准导出坐标校验未通过')
    expect(downloadReportExport).toHaveBeenCalledTimes(1)
    expect(wrapper.findAll('button').every(item => item.attributes('disabled') === undefined)).toBe(true)
  })
})
