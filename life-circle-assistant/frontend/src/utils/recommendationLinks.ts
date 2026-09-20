import type { PlanningRecommendation } from '../types/recommendations'
import type { ServiceAreaFeature } from '../types/report'

export function recommendationForServiceArea(
  recommendations: PlanningRecommendation[],
  serviceAreaId: string,
) {
  return recommendations.find((item) => item.target_region_ids.includes(serviceAreaId)) || null
}

export function serviceAreasForRecommendation(
  serviceAreas: ServiceAreaFeature[],
  recommendation: PlanningRecommendation,
) {
  const targetIds = new Set(recommendation.target_region_ids)
  return serviceAreas.filter((feature) => targetIds.has(feature.properties.grid_id))
}
