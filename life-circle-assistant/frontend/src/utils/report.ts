import type { Report } from '../types/report'

export function exportReport(report: Report | null) {
  if (!report) return
  const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = '黄埔区生活圈体检报告.json'
  link.click()
  URL.revokeObjectURL(url)
}
