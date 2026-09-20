export type CenterSelectionMethod = 'default' | 'address' | 'map' | 'coordinates'
export type CenterSupportStatus = 'supported' | 'checking' | 'unsupported'

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
