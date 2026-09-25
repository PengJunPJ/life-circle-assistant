// @vitest-environment jsdom
import { nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import type { Report, ServiceAreaFeature } from '../types/report'
import MapStage from './MapStage.vue'

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
  geometry: { type: 'Polygon', coordinates: [[[113.48, 23.10], [113.49, 23.10], [113.49, 23.11], [113.48, 23.10]]] },
} satisfies ServiceAreaFeature

const selectedServiceArea = ref<ServiceAreaFeature | null>(null)
const hoverTarget = ref<any>(null)
vi.mock('../composables/useMapRenderer', () => ({
  useMapRenderer: () => ({
    mapCanvas: ref(null), mapContainer: ref(null), realMapReady: ref(false), mapLoadComplete: ref(false), selectedServiceArea,
    hoverTarget,
    routePreview: ref(null), setRoutePreview: vi.fn(), retainHover: vi.fn(), clearHover: vi.fn(),
    visibleServiceAreas: () => [area], selectServiceArea: (feature: ServiceAreaFeature) => { selectedServiceArea.value = feature },
    handleCanvasClick: vi.fn(), handleCanvasMouseMove: vi.fn(), handleCanvasMouseLeave: vi.fn(),
    closeServiceAreaEvidence: () => { selectedServiceArea.value = null },
  }),
}))

describe('地图服务区域键盘证据入口', () => {
  it('可聚焦按钮支持回车选择区域并展示判定依据', async () => {
    selectedServiceArea.value = null
    const report = { recommendations: [], service_areas: { type: 'FeatureCollection', features: [area] } } as unknown as Report
    const wrapper = mount(MapStage, {
      props: {
        report, analysisCenter: { lng: 113.4872, lat: 23.1068, address: '测试中心', selectionMethod: 'default', source: 'fixture', supportStatus: 'supported' },
        minutes: 15, visibleCategories: ['school'], showNormal: false, showSparse: true, showCritical: true,
        loading: false, progress: 0, focusRecommendationId: null, simulation: null, simulationPicking: false,
      },
    })
    const button = wrapper.get('.service-area-keyboard-list button')
    expect(button.attributes('aria-label')).toContain('查看判定依据')
    await button.trigger('keydown.enter')
    await button.trigger('click')
    await nextTick()
    expect(wrapper.get('.service-area-evidence').text()).toContain('步行时间超过阈值')
    const selections = wrapper.emitted('service-area-select') || []
    expect(selections[selections.length - 1]).toEqual(['school-r1c1'])
  })

  it('悬浮卡片展示设施步行时间、距离与状态色', async () => {
    selectedServiceArea.value = null
    hoverTarget.value = {
      poi: { id: 'poi-1', name: '测试菜市场', category: 'market', lng: 113.48, lat: 23.1, walk_minutes: 6, walk_distance_m: 430, source: 'real_api', semantic_type_label: '生鲜超市/菜市场' },
      x: 120, y: 140,
    }
    const report = { recommendations: [], service_areas: { type: 'FeatureCollection', features: [area] } } as unknown as Report
    const wrapper = mount(MapStage, {
      props: {
        report, analysisCenter: { lng: 113.4872, lat: 23.1068, address: '测试中心', selectionMethod: 'default', source: 'fixture', supportStatus: 'supported' },
        minutes: 15, visibleCategories: ['school'], showNormal: false, showSparse: true, showCritical: true,
        loading: false, progress: 0, focusRecommendationId: null, simulation: null, simulationPicking: false,
      },
    })
    await nextTick()
    const card = wrapper.get('.map-hover-card')
    expect(card.classes()).toContain('st-ok')
    expect(card.text()).toContain('测试菜市场')
    expect(card.text()).toContain('6')
    expect(card.text()).toContain('430 米')
    expect(card.text()).toContain('15分钟内')
    hoverTarget.value = null
  })
})
