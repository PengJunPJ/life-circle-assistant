import type { AnalysisCenter } from '../types/location'

type ProjectPoint = (lng: number, lat: number) => { x: number; y: number }

export function drawCanvasAnalysisCenter(
  context: CanvasRenderingContext2D,
  center: AnalysisCenter,
  project: ProjectPoint,
  minutes: number,
) {
  const point = project(center.lng, center.lat)
  context.beginPath()
  context.arc(point.x, point.y, 24, 0, Math.PI * 2)
  context.fillStyle = 'rgba(35,120,102,.10)'
  context.fill()
  context.strokeStyle = '#237866'
  context.lineWidth = 2
  context.stroke()
  context.beginPath()
  context.arc(point.x, point.y, 10, 0, Math.PI * 2)
  context.fillStyle = '#17333d'
  context.fill()
  context.strokeStyle = '#fff'
  context.lineWidth = 3
  context.stroke()
  context.strokeStyle = '#fff'
  context.lineWidth = 2
  context.beginPath()
  context.moveTo(point.x - 5, point.y)
  context.lineTo(point.x + 5, point.y)
  context.moveTo(point.x, point.y - 5)
  context.lineTo(point.x, point.y + 5)
  context.stroke()
  context.font = '700 11px sans-serif'
  context.fillStyle = '#17333d'
  context.textAlign = 'left'
  context.fillText(`${minutes}分钟步行起点`, point.x + 30, point.y - 2)
  context.font = '10px sans-serif'
  context.fillStyle = '#59716d'
  context.fillText(center.address, point.x + 30, point.y + 13)
}

export function renderBaiduAnalysisCenter(map: any, BMap: any, center: AnalysisCenter, minutes: number) {
  const point = new BMap.Point(center.lng, center.lat)
  map.addOverlay(new BMap.Circle(point, 36, { strokeColor: '#237866', strokeWeight: 2, strokeOpacity: .9, fillColor: '#237866', fillOpacity: .12 }))
  const label = new BMap.Label(
    `<span class="origin-map-label"><i></i><strong>${minutes}分钟步行起点</strong><small>${escapeHtml(center.address)}</small></span>`,
    { position: point, offset: new BMap.Size(24, -24) },
  )
  label.setStyle({ border: '0', background: 'transparent', padding: '0', whiteSpace: 'nowrap', zIndex: '30' })
  map.addOverlay(label)
}

function escapeHtml(value: string) {
  return value.replace(/[&<>'"]/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    "'": '&#39;',
    '"': '&quot;',
  })[character] || character)
}
