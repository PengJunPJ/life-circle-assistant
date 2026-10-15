export type ReportGuidePage = 'overview' | 'facilities' | 'recommendations' | 'ai' | 'details' | 'history' | 'export'

export type GuideStep = {
  id: string
  surface: 'controls' | 'map' | 'conversation' | 'report'
  reportPage?: ReportGuidePage
}
