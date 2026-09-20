import { describe, expect, it } from 'vitest'
import type { PlanningRecommendation } from '../types/recommendations'
import type { ServiceAreaFeature } from '../types/report'
import { recommendationForServiceArea, serviceAreasForRecommendation } from './recommendationLinks'

const recommendation = {
  id: 'recommendation-market-critical',
  category: 'market',
  target_region_ids: ['market-r1c1', 'market-r1c2'],
} as PlanningRecommendation

const area = (gridId: string, category: string) => ({
  type: 'Feature',
  properties: { grid_id: gridId, category },
  geometry: { type: 'Polygon', coordinates: [] },
}) as unknown as ServiceAreaFeature

describe('规划建议与服务区域双向定位', () => {
  it('从地图区域只找到引用该稳定区域 ID 的建议', () => {
    expect(recommendationForServiceArea([recommendation], 'market-r1c2')?.id).toBe(recommendation.id)
    expect(recommendationForServiceArea([recommendation], 'school-r1c2')).toBeNull()
  })

  it('从报告建议只返回实际引用的服务区域', () => {
    const features = [area('market-r1c1', 'market'), area('market-r1c2', 'market'), area('school-r1c1', 'school')]
    expect(serviceAreasForRecommendation(features, recommendation).map((item) => item.properties.grid_id))
      .toEqual(['market-r1c1', 'market-r1c2'])
  })
})
