export type CenterSelectionMethod = 'default' | 'address' | 'map' | 'coordinates'
export type CenterSupportStatus = 'supported' | 'checking' | 'unsupported'
export type CoordinateSystem = 'wgs84' | 'gcj02' | 'bd09'

export type AnalysisCenter = {
  lng: number
  lat: number
  address: string
  selectionMethod: CenterSelectionMethod
  source: string
  supportStatus: CenterSupportStatus
}

export type LocationCandidate = {
  lng: number
  lat: number
  address: string
  source: string
  provider: string
}

export type LocationApiResponse = {
  source: string
  provider: string
  result: { lng: number; lat: number; address: string }
}

export type CoordinateConversionResponse = {
  source: string
  provider: string
  input: { lng: number; lat: number; coordinate_system: CoordinateSystem }
  result: { lng: number; lat: number; coordinate_system: 'bd09' }
  method: string
}

export type WalkingRoute = {
  origin: { lng: number; lat: number }
  destination: { lng: number; lat: number }
  distance_m: number
  duration_s: number
  polyline: [number, number][]
  source: string
}
