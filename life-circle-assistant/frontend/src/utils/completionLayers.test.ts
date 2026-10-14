import { describe, expect, it } from 'vitest'
import { buildEvidenceOverlays, buildSamplingPoints } from './completionLayers'
import { DEFAULT_STATUS_LAYERS, type SamplingLayers } from '../types/completion'
import type { Report } from '../types/report'

const polygon = { type: 'Polygon' as const, coordinates: [[[113, 23], [114, 23], [114, 24], [113, 23]]] }
const report = { parameters: { minutes: 15 }, service_areas: { features: [
  { geometry: polygon, properties: { category: 'pharmacy', grid_id: 'scarce-reachable', kind: 'normal', nearby_scarcity: true, walking_reachable: true, classification_status: 'valid', failed_route_count: 0 } },
  { geometry: polygon, properties: { category: 'pharmacy', grid_id: 'timeout-abundant', kind: 'normal', nearby_scarcity: false, walking_reachable: false, walking_reachability_status: 'measured', source: 'local_snapshot', classification_status: 'valid', failed_route_count: 0 } },
  { geometry: polygon, properties: { category: 'pharmacy', grid_id: 'unknown', kind: 'unknown', nearby_scarcity: null, walking_reachable: false, classification_status: 'calculation_incomplete', failed_route_count: 1 } },
] }, gap_groups: { features: [{ geometry: { type: 'MultiPolygon', coordinates: [polygon.coordinates] }, properties: { id: 'group', category: 'pharmacy', gap_kind: 'scarcity' } }] } } as unknown as Report

describe('独立空间证据图层', () => {
  it('1公里稀缺与步行超时独立呈现，失败路线不能伪装成确认缺口', () => {
    const layers = { ...DEFAULT_STATUS_LAYERS, scarcity: true, walking_timeout: true }
    expect(buildEvidenceOverlays(report, ['pharmacy'], layers).map(item => item.id)).toEqual(['scarcity:scarce-reachable', 'walking:timeout-abundant'])
    expect(buildEvidenceOverlays(report, ['school'], layers)).toEqual([])
  })
  it('保留分组多边形，观测/估计/未决分开且拒绝混用坐标系', () => {
    const collection = (coordinate: string, point: string) => ({ type: 'FeatureCollection' as const, features: [{ type: 'Feature' as const, geometry: polygon, properties: { coordinate_system: coordinate, point_id: point, mean_minutes: 12 } }] })
    const sampling: SamplingLayers = { observed: { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [113.5, 23.5] }, properties: { coordinate_system: 'BD-09', point_id: 'measured', mean_minutes: 12 } }] }, observed_boundary: collection('BD-09', 'measured'), estimated: collection('BD-09', 'estimated'), unresolved: collection('BD-09', 'unknown'), time_field: collection('WGS84', 'wrong-system') }
    const result = buildEvidenceOverlays(report, ['pharmacy'], { ...DEFAULT_STATUS_LAYERS, gap_groups: true, sampling: true }, sampling)
    expect(result.map(item => item.id)).toEqual(['group:0', 'estimated:estimated:0', 'unresolved:unknown:0', 'observed_boundary:measured:0'])
    expect(result.find(item => item.id === 'group:0')?.rings).toEqual(polygon.coordinates)
    expect(result.find(item => item.id.startsWith('observed'))?.label).toContain('非整格可达认证')
    expect(buildSamplingPoints({ ...DEFAULT_STATUS_LAYERS, sampling: true }, sampling)).toEqual([{ lng: 113.5, lat: 23.5, label: '真实观测点 measured · 12.0分钟' }])
    expect(buildSamplingPoints(DEFAULT_STATUS_LAYERS, sampling)).toEqual([])
  })
  it('仅可信实测或可信来源缓存可显示确认超时，估算和未知来源均不冒充实测', () => {
    const timeout = report.service_areas.features[1]!
    const variants = [
      { source: 'real_api', walking_reachability_status: 'measured' },
      { source: 'cache', underlying_source: 'local_snapshot', walking_reachability_status: 'measured' },
      { source: 'local_snapshot', walking_reachability_status: undefined },
      { source: 'mock', walking_reachability_status: 'measured' },
      { source: 'degraded_estimate', walking_reachability_status: 'estimated' },
      { source: 'cache', underlying_source: 'mock', walking_reachability_status: 'measured' },
      { source: 'cache', walking_reachability_status: 'measured' },
      { source: 'unknown', walking_reachability_status: undefined },
      { source: 'real_api', walking_reachability_status: 'estimated' },
    ]
    const scenarios = { ...report, service_areas: { ...report.service_areas, features: variants.map((value,index) => ({ ...timeout, properties: { ...timeout.properties, ...value, grid_id: `case-${index}` } })) } } as Report
    expect(buildEvidenceOverlays(scenarios, ['pharmacy'], { ...DEFAULT_STATUS_LAYERS, walking_timeout: true }).map(item => item.id)).toEqual(['walking:case-0', 'walking:case-1', 'walking:case-2'])
  })
})
