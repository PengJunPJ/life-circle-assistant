// @vitest-environment jsdom
import { defineComponent, h, nextTick, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Report, ServiceAreaFeature } from '../types/report'
import { useMapRenderer } from './useMapRenderer'

vi.mock('../services/analysisApi', () => ({
  fetchMapConfig: vi.fn().mockResolvedValue({ mode: 'mock', provider_mode: 'snapshot', browser_ak: '' }),
}))

const area = {
  type: 'Feature',
  properties: {
    grid_id: 'school-r1c1', coordinate_system: 'BD-09', kind: 'critical', region_type: 'critical',
    label: '重点服务盲区', category: 'school', category_label: '小学', color: '#c75c43',
    threshold_minutes: 15, nearby_radius_m: 1000, nearby_facility_count: 0, lacks_nearby_facility: true,
    candidate_prefilter_radius_m: 3000, candidate_facility_count: 1, nearest_facility_id: 'school-1',
    nearest_facility_name: '测试小学', nearest_walk_minutes: 18, nearest_walk_distance_m: 1200,
    walk_threshold_exceeded: true, critical_conditions_met: true, classification_status: 'valid', source: 'real_api',
    calculation_method: 'fixture', basis: '步行时间超过阈值且周边缺少同类设施。', confidence: 'high', failed_route_count: 0,
  },
  geometry: {
    type: 'Polygon',
    coordinates: [[[113.488, 23.107], [113.49, 23.107], [113.49, 23.109], [113.488, 23.109], [113.488, 23.107]]],
  },
} satisfies ServiceAreaFeature

const report = {
  isochrone: {
    type: 'Feature', properties: { minutes: 15 },
    geometry: { type: 'Polygon', coordinates: [[[113.48, 23.10], [113.50, 23.10], [113.50, 23.12], [113.48, 23.10]]] },
  },
  service_areas: { type: 'FeatureCollection', features: [area] },
  zones: { type: 'FeatureCollection', features: [area] },
  pois: [], recommendations: [],
} as unknown as Report

describe('服务区域选中定位', () => {
  const strokes: number[] = []
  const labels: string[] = []

  beforeEach(() => {
    strokes.length = 0
    labels.length = 0
    const context = {
      lineWidth: 1, fillStyle: '', strokeStyle: '', font: '', textAlign: '', textBaseline: '',
      setTransform: vi.fn(), fillRect: vi.fn(), beginPath: vi.fn(), moveTo: vi.fn(), lineTo: vi.fn(), closePath: vi.fn(),
      fill: vi.fn(), arc: vi.fn(), setLineDash: vi.fn(),
      stroke() { strokes.push(this.lineWidth) }, strokeRect: vi.fn(),
      fillText(value: string) { labels.push(value) },
      measureText: vi.fn().mockReturnValue({ width: 48 }),
    }
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(context as unknown as CanvasRenderingContext2D)
    vi.spyOn(HTMLCanvasElement.prototype, 'getBoundingClientRect').mockReturnValue({
      width: 900, height: 640, top: 0, left: 0, right: 900, bottom: 640, x: 0, y: 0, toJSON: () => ({}),
    })
  })

  it('从列表选中网格后重新渲染粗轮廓并显示已选标记', async () => {
    let renderer: ReturnType<typeof useMapRenderer> | null = null
    const Harness = defineComponent({
      setup() {
        renderer = useMapRenderer({
          report: ref(report),
          analysisCenter: ref({ lng: 113.4872, lat: 23.1068, address: '测试中心', selectionMethod: 'default', source: 'fixture', supportStatus: 'supported' }),
          visibleCategories: ref(['school']), showNormal: ref(true), showSparse: ref(true), showCritical: ref(true),
          focusRecommendationId: ref(null), simulation: ref(null), simulationPicking: ref(false),
          onSelectCenter: vi.fn(), onSelectSimulationLocation: vi.fn(),
        })
        return () => h('canvas', { ref: renderer!.mapCanvas })
      },
    })

    mount(Harness)
    await nextTick()
    await flushPromises()
    strokes.length = 0
    labels.length = 0

    renderer!.selectServiceArea(area)
    await nextTick()
    await flushPromises()

    expect(strokes).toContain(5)
    expect(labels).toContain('已选')
  })
})
