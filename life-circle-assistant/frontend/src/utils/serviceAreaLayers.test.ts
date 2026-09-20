import { describe, expect, it } from 'vitest'

import type { ServiceAreaFeature } from '../types/report'
import { isServiceAreaVisible, pointInPolygon } from './serviceAreaLayers'

const feature = {
  type: 'Feature',
  properties: {
    grid_id: 'school-r1c1', coordinate_system: 'BD-09', kind: 'critical', region_type: 'critical',
    label: '重点服务盲区', category: 'school', category_label: '小学', color: '#c75c43',
    threshold_minutes: 15, nearby_radius_m: 1000, nearby_facility_count: 0, lacks_nearby_facility: true,
    candidate_prefilter_radius_m: 3000, candidate_facility_count: 0,
    nearest_facility_id: null, nearest_facility_name: null, nearest_walk_minutes: null,
    nearest_walk_distance_m: null, walk_threshold_exceeded: true, critical_conditions_met: true,
    source: 'real_api', calculation_method: 'fixture',
    basis: '测试依据', confidence: 'high', failed_route_count: 0,
  },
  geometry: { type: 'Polygon', coordinates: [[]] },
} satisfies ServiceAreaFeature

describe('服务区域图层', () => {
  it('同时按设施类别和区域类型过滤', () => {
    expect(isServiceAreaVisible(feature, ['school'], { normal: false, sparse: false, critical: true })).toBe(true)
    expect(isServiceAreaVisible(feature, ['market'], { normal: false, sparse: false, critical: true })).toBe(false)
    expect(isServiceAreaVisible(feature, ['school'], { normal: false, sparse: false, critical: false })).toBe(false)
  })

  it('识别 Canvas 点击是否落在区域内', () => {
    const polygon = [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 10 }, { x: 0, y: 10 }]
    expect(pointInPolygon({ x: 5, y: 5 }, polygon)).toBe(true)
    expect(pointInPolygon({ x: 15, y: 5 }, polygon)).toBe(false)
  })
})
