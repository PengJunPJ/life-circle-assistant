import type { Combination, SamplingLayers, StatusLayers } from '../types/completion'
import type { Report } from '../types/report'

export type MapEvidenceOverlay = { id: string; rings: number[][][]; stroke: string; fill: string; label: string }
export function buildSamplingPoints(layers: StatusLayers, sampling?: SamplingLayers | null): { lng: number; lat: number; label: string }[] {
  if (!layers.sampling) return []
  return (sampling?.observed.features || []).flatMap(feature => {
    if (feature.geometry.type !== 'Point' || (feature.properties.coordinate_system && feature.properties.coordinate_system !== 'BD-09')) return []
    const [lng, lat] = feature.geometry.coordinates
    if (!Number.isFinite(lng) || !Number.isFinite(lat)) return []
    const minutes = feature.properties.measured_minutes ?? feature.properties.mean_minutes
    return [{ lng, lat, label: `真实观测点 ${feature.properties.point_id || ''}${typeof minutes === 'number' ? ` · ${minutes.toFixed(1)}分钟` : ''}` }]
  })
}

export function buildEvidenceOverlays(report: Report | null, categories: string[], layers: StatusLayers, sampling?: SamplingLayers | null, combination?: Combination | null): MapEvidenceOverlay[] {
  if (!report) return []
  const output: MapEvidenceOverlay[] = []
  for (const area of report.service_areas?.features || []) {
    const p = area.properties
    if (!categories.includes(p.category)) continue
    if (layers.scarcity && p.nearby_scarcity === true) output.push({ id: `scarcity:${p.grid_id}`, rings: area.geometry.coordinates, stroke: '#bd922c', fill: 'rgba(218,176,69,.20)', label: '1公里设施稀缺' })
    const measuredSource = ['real_api', 'local_snapshot'].includes(p.source === 'cache' ? p.underlying_source || '' : p.source)
    const measuredStatus = !p.walking_reachability_status || p.walking_reachability_status === 'measured'
    if (layers.walking_timeout && measuredSource && measuredStatus && p.walking_reachable === false && p.classification_status === 'valid' && p.failed_route_count === 0) output.push({ id: `walking:${p.grid_id}`, rings: area.geometry.coordinates, stroke: '#885cac', fill: 'rgba(136,92,172,.19)', label: '已核验步行超时' })
  }
  if (layers.gap_groups) for (const group of report.gap_groups?.features || []) {
    if (!categories.includes(group.properties.category)) continue
    const kind = group.properties.gap_kind || 'walking_timeout'
    group.geometry.coordinates.forEach((rings, index) => output.push({ id: `${group.properties.id}:${index}`, rings, stroke: kind === 'critical' ? '#ac4831' : kind === 'scarcity' ? '#bd922c' : '#885cac', fill: 'rgba(118,72,154,.07)', label: `${kind === 'critical' ? '重点盲区' : kind === 'scarcity' ? '设施稀缺' : '步行超时'}片区` }))
  }
  if (layers.sampling && sampling) for (const key of ['time_field', 'estimated', 'unresolved', 'observed_boundary', 'native_boundary'] as const) {
    for (const feature of sampling[key]?.features || []) {
      if (feature.properties.coordinate_system && feature.properties.coordinate_system !== 'BD-09') continue
      if (feature.geometry.type === 'Point') continue
      const p = feature.properties
      const time = typeof p.mean_minutes === 'number' ? p.mean_minutes : null
      const color = key === 'observed_boundary' ? '#277c70' : key === 'native_boundary' ? '#437651' : key === 'unresolved' ? '#677681' : time !== null && time > report.parameters.minutes ? '#ab7139' : '#4f84b1'
      const polys = feature.geometry.type === 'MultiPolygon' ? feature.geometry.coordinates : [feature.geometry.coordinates]
      polys.forEach((rings, index) => output.push({ id: `${key}:${p.point_id}:${index}`, rings, stroke: color, fill: key === 'unresolved' ? 'rgba(103,118,129,.22)' : key === 'observed_boundary' ? 'rgba(39,124,112,.12)' : 'rgba(79,132,177,.12)', label: `${key === 'observed_boundary' ? '观测中心网格外沿，非整格可达认证' : key === 'native_boundary' ? '地图服务原生等时圈' : key === 'unresolved' ? '未决' : '估计'}${time === null ? '' : ` ${time.toFixed(1)}分钟`}` }))
    }
  }
  for (const area of combination?.after.service_areas?.features || []) {
    if (categories.includes(area.properties.category)) output.push({ id: `combination:${area.properties.grid_id}`, rings: area.geometry.coordinates, stroke: '#286995', fill: 'rgba(40,105,149,.15)', label: '组合假设情景' })
  }
  return output
}
