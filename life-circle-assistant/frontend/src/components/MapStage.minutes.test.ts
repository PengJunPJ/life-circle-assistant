// @vitest-environment jsdom
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fetchMapConfig } from '../services/analysisApi'
import type { AnalysisMinutes, Report } from '../types/report'
import MapStage from './MapStage.vue'

vi.mock('../services/analysisApi', () => ({ fetchMapConfig: vi.fn() }))
vi.mock('../utils/baiduSdk', () => ({ loadBaiduSdk: vi.fn().mockResolvedValue(undefined) }))

const previousReport = {
  isochrone: {
    type: 'Feature', properties: { minutes: 15 },
    geometry: { type: 'Polygon', coordinates: [[[113.48, 23.10], [113.50, 23.10], [113.50, 23.12], [113.48, 23.10]]] },
  },
  service_areas: { type: 'FeatureCollection', features: [] },
  zones: { type: 'FeatureCollection', features: [] },
  pois: [], recommendations: [],
} as unknown as Report

describe('地图起点步行时间同步', () => {
  const canvasLabels: string[] = []
  const baiduLabels: string[] = []
  let navigationOffset: { width: number; height: number } | null = null
  let wrapper: VueWrapper | undefined

  beforeEach(() => {
    canvasLabels.length = 0
    baiduLabels.length = 0
    navigationOffset = null
    const context = {
      setTransform: vi.fn(), fillRect: vi.fn(), beginPath: vi.fn(), moveTo: vi.fn(), lineTo: vi.fn(),
      closePath: vi.fn(), fill: vi.fn(), stroke: vi.fn(), arc: vi.fn(), setLineDash: vi.fn(),
      fillText: (text: string) => { canvasLabels.push(text) },
    }
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(context as unknown as CanvasRenderingContext2D)
    vi.spyOn(HTMLCanvasElement.prototype, 'getBoundingClientRect').mockReturnValue({
      width: 900, height: 640, top: 0, left: 0, right: 900, bottom: 640, x: 0, y: 0, toJSON: () => ({}),
    })

    class Shape {}
    class Label {
      constructor(readonly text: string) {}
      setStyle() {}
    }
    class Size {
      constructor(readonly width: number, readonly height: number) {}
    }
    class NavigationControl {
      constructor(options: { offset: { width: number; height: number } }) { navigationOffset = options.offset }
    }
    class BaiduMap {
      enableScrollWheelZoom() {}
      addControl() {}
      addEventListener() {}
      centerAndZoom() {}
      clearOverlays() { baiduLabels.length = 0 }
      addOverlay(overlay: unknown) {
        if (overlay instanceof Label) baiduLabels.push(overlay.text)
      }
    }
    vi.stubGlobal('BMap', {
      Map: BaiduMap, Label, Point: Shape, Size, Circle: Shape, Polygon: Shape,
      NavigationControl, ScaleControl: Shape,
    })
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = undefined
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  for (const mode of ['Canvas', '百度地图'] as const) {
    for (const { scenario, report } of [
      { scenario: '尚无报告', report: null },
      { scenario: '已有15分钟报告', report: previousReport },
    ]) {
      it(`${mode}在${scenario}时，初始标注及切换时间均跟随当前参数`, async () => {
        vi.mocked(fetchMapConfig).mockResolvedValue(mode === '百度地图'
          ? { mode: 'real', provider_mode: 'real', browser_ak: 'test-key' }
          : { mode: 'mock', provider_mode: 'snapshot', browser_ak: '' })
        wrapper = mount(MapStage, {
          props: {
            report,
            analysisCenter: { lng: 113.4872, lat: 23.1068, address: '测试中心', selectionMethod: 'default', source: 'fixture', supportStatus: 'supported' },
            minutes: 20, visibleCategories: [], showNormal: false, showSparse: false, showCritical: false,
            loading: false, progress: 0, focusRecommendationId: null, simulation: null, simulationPicking: false,
          },
        })
        await flushPromises()
        expect(wrapper.get('.map-container').classes().includes('hidden')).toBe(mode === 'Canvas')
        expect(wrapper.find('.map-scale').exists()).toBe(mode === 'Canvas')
        if (mode === '百度地图') expect(navigationOffset).toEqual({ width: 10, height: 110 })

        const originLabel = () => {
          const labels = mode === 'Canvas' ? canvasLabels : baiduLabels
          return labels.filter(text => text.includes('分钟步行起点')).slice(-1)[0]?.match(/\d+分钟步行起点/)?.[0]
        }
        expect(originLabel()).toBe('20分钟步行起点')

        for (const minutes of [10, 15, 20] satisfies AnalysisMinutes[]) {
          await wrapper.setProps({ minutes })
          await flushPromises()
          expect(originLabel()).toBe(`${minutes}分钟步行起点`)
        }
        if (report) expect(report.isochrone.properties.minutes).toBe(15)
      })
    }
  }
})
