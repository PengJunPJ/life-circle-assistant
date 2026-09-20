import type { ServiceAreaFeature, ServiceAreaKind } from '../types/report'

export type ServiceAreaVisibility = Record<ServiceAreaKind, boolean>

export function isServiceAreaVisible(
  feature: ServiceAreaFeature,
  categories: string[],
  visibility: ServiceAreaVisibility,
) {
  return categories.includes(feature.properties.category) && visibility[feature.properties.kind]
}

export function pointInPolygon(point: { x: number; y: number }, polygon: { x: number; y: number }[]) {
  let inside = false
  for (let index = 0, previous = polygon.length - 1; index < polygon.length; previous = index++) {
    const currentPoint = polygon[index]
    const previousPoint = polygon[previous]
    const crosses = (currentPoint.y > point.y) !== (previousPoint.y > point.y)
      && point.x < ((previousPoint.x - currentPoint.x) * (point.y - currentPoint.y))
        / (previousPoint.y - currentPoint.y) + currentPoint.x
    if (crosses) inside = !inside
  }
  return inside
}
