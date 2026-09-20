export type AnalysisMode = 'demo' | 'analysis'
export type AnalysisMinutes = 10 | 15 | 20

export type Category = {
  category: string
  label: string
  count: number
  nearest_walk_minutes: number | null
  score: number
  color: string
}

export type Poi = {
  id: string
  name: string
  category: string
  lng: number
  lat: number
  walk_minutes: number
}

export type GeoJsonFeature = {
  type: 'Feature'
  properties: Record<string, any>
  geometry: { type: string; coordinates: number[][][] }
}

export type Report = {
  source: string
  quality: { mode: string; confidence: number; message: string }
  isochrone: GeoJsonFeature
  pois: Poi[]
  zones: { type: 'FeatureCollection'; features: GeoJsonFeature[] }
  summary: {
    score: number
    area_sqm: number
    poi_count: number
    critical_zone_count: number
    sparse_zone_count: number
  }
  categories: Category[]
  recommendations: { priority: string; title: string; body: string; category: string }[]
  center: { lng: number; lat: number; address: string }
}

export type AnalysisTask = {
  id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  progress: number
  result?: Report
  error?: string
}

export type MapConfig = { mode: string; browser_ak: string }
