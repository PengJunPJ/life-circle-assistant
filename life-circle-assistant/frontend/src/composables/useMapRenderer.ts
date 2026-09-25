import { nextTick, onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'
import ElMessage from 'element-plus/es/components/message/index'
import { ROUTE_ARROW_SPACING, ROUTE_BORDER, ROUTE_COLOR, categoryColor, categoryShort } from '../constants/facilities'
import { drawCanvasAnalysisCenter, renderBaiduAnalysisCenter } from '../mapLayers/analysisCenterLayer'
import { fetchMapConfig } from '../services/analysisApi'
import type { AnalysisCenter, WalkingRoute } from '../types/location'
import type { Poi, Report, ServiceAreaFeature } from '../types/report'
import type { PlanningRecommendation } from '../types/recommendations'
import type { SimulationResult } from '../types/simulation'
import { isServiceAreaVisible, pointInPolygon } from '../utils/serviceAreaLayers'
import { computeRouteArrows } from '../utils/routeArrows'

export type MapHoverTarget = { poi: Poi; x: number; y: number }
export type MapRoutePreview = { poi: Poi; route: WalkingRoute }

function drawRouteEndpointLabel(context: CanvasRenderingContext2D, x: number, y: number, text: string) {
  context.font = '700 10px sans-serif'
  const width = context.measureText(text).width + 14
  const anyCtx = context as any
  context.fillStyle = ROUTE_BORDER
  context.beginPath()
  if (typeof anyCtx.roundRect === 'function') anyCtx.roundRect(x - width / 2, y - 9, width, 18, 9)
  else context.rect(x - width / 2, y - 9, width, 18)
  context.fill()
  context.fillStyle = '#fff'
  context.textAlign = 'center'
  context.textBaseline = 'middle'
  context.fillText(text, x, y + .5)
}

type MapRendererOptions = {
  report: Ref<Report | null>
  analysisCenter: Ref<AnalysisCenter>
  visibleCategories: Ref<string[]>
  showNormal: Ref<boolean>
  showSparse: Ref<boolean>
  showCritical: Ref<boolean>
  focusRecommendationId: Ref<string | null>
  simulation: Ref<SimulationResult | null>
  simulationPicking: Ref<boolean>
  onSelectCenter: (lng: number, lat: number) => void
  onSelectSimulationLocation: (lng: number, lat: number) => void
}

export function useMapRenderer({ report, analysisCenter, visibleCategories, showNormal, showSparse, showCritical, focusRecommendationId, simulation, simulationPicking, onSelectCenter, onSelectSimulationLocation }: MapRendererOptions) {
  const mapCanvas = ref<HTMLCanvasElement | null>(null)
  const mapContainer = ref<HTMLDivElement | null>(null)
  const realMapReady = ref(false)
  const mapLoadComplete = ref(false)
  const selectedServiceArea = ref<ServiceAreaFeature | null>(null)
  let baiduMap: any = null
  let baiduClickBound = false
  const hoverTarget = ref<MapHoverTarget | null>(null)
  const routePreview = ref<MapRoutePreview | null>(null)
  let hoverTimer: number | undefined
  let hoverClearTimer: number | undefined

  function clearHoverTimer() {
    if (hoverTimer !== undefined) { window.clearTimeout(hoverTimer); hoverTimer = undefined }
  }

  function clearHoverClearTimer() {
    if (hoverClearTimer !== undefined) { window.clearTimeout(hoverClearTimer); hoverClearTimer = undefined }
  }

  function clearHover() {
    clearHoverTimer()
    clearHoverClearTimer()
    hoverTarget.value = null
  }

  // 鼠标从 marker 移向卡片按钮时会先触发 mouseout；给一个宽限期，
  // 若期间进入卡片（retainHover）则取消隐藏，保证按钮点得到。
  function requestClearHover() {
    clearHoverTimer()
    clearHoverClearTimer()
    hoverClearTimer = window.setTimeout(() => { hoverTarget.value = null }, 160)
  }

  function retainHover() {
    clearHoverTimer()
    clearHoverClearTimer()
  }

  function scheduleHover(poi: Poi, x: number, y: number, sticky = false) {
    clearHoverTimer()
    clearHoverClearTimer()
    if (sticky) { hoverTarget.value = { poi, x, y }; return }
    hoverTimer = window.setTimeout(() => { hoverTarget.value = { poi, x, y } }, 120)
  }

  function visiblePois(): Poi[] {
    return (report.value?.pois || []).filter((poi) => visibleCategories.value.includes(poi.category))
  }

  function hitTestPoi(point: { x: number; y: number }, width: number, height: number): MapHoverTarget | null {
    const hit = [...visiblePois()].reverse().find((poi) => {
      const projected = project(poi.lng, poi.lat, width, height)
      return Math.hypot(point.x - projected.x, point.y - projected.y) <= 14
    })
    if (!hit) return null
    const projected = project(hit.lng, hit.lat, width, height)
    return { poi: hit, x: projected.x, y: projected.y }
  }

  function serviceAreaCenter(feature: ServiceAreaFeature) {
    const coordinates = feature.geometry.coordinates[0]
    const vertices = coordinates.length > 1
      && coordinates[0][0] === coordinates[coordinates.length - 1][0]
      && coordinates[0][1] === coordinates[coordinates.length - 1][1]
      ? coordinates.slice(0, -1)
      : coordinates
    const total = vertices.reduce((sum, [lng, lat]) => ({ lng: sum.lng + lng, lat: sum.lat + lat }), { lng: 0, lat: 0 })
    return { lng: total.lng / Math.max(vertices.length, 1), lat: total.lat / Math.max(vertices.length, 1) }
  }

  function canvasViewport() {
    const selected = selectedServiceArea.value
    return selected
      ? { center: serviceAreaCenter(selected), scale: 72000 }
      : { center: analysisCenter.value, scale: 42000 }
  }

  function project(lng: number, lat: number, width: number, height: number) {
    const viewport = canvasViewport()
    return {
      x: width / 2 + (lng - viewport.center.lng) * viewport.scale,
      y: height / 2 - (lat - viewport.center.lat) * viewport.scale,
    }
  }

  function unproject(x: number, y: number, width: number, height: number) {
    const viewport = canvasViewport()
    return {
      lng: viewport.center.lng + (x - width / 2) / viewport.scale,
      lat: viewport.center.lat - (y - height / 2) / viewport.scale,
    }
  }

  function drawMap() {
    const canvas = mapCanvas.value
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const dpr = window.devicePixelRatio || 1
    canvas.width = rect.width * dpr
    canvas.height = rect.height * dpr
    const ctx = canvas.getContext('2d')!
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    const w = rect.width
    const h = rect.height
    ctx.fillStyle = '#dce3df'
    ctx.fillRect(0, 0, w, h)
    ctx.strokeStyle = '#c2cec9'
    ctx.lineWidth = 1
    for (let i = -h; i < w + h; i += 92) { ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i + h, h); ctx.stroke() }
    ctx.strokeStyle = '#b3c5c1'
    ctx.lineWidth = 8
    for (let i = -h; i < w + h; i += 160) { ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i + h, h); ctx.stroke() }
    ctx.strokeStyle = '#e9efea'
    ctx.lineWidth = 3
    for (let i = -h; i < w + h; i += 160) { ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i + h, h); ctx.stroke() }

    const drawPolygon = (coordinates: number[][], fill: string, stroke: string, lineWidth = 2, marker = '') => {
      ctx.beginPath()
      coordinates.forEach(([lng, lat], index) => {
        const point = project(lng, lat, w, h)
        index ? ctx.lineTo(point.x, point.y) : ctx.moveTo(point.x, point.y)
      })
      ctx.closePath(); ctx.fillStyle = fill; ctx.fill(); ctx.strokeStyle = stroke; ctx.lineWidth = lineWidth
      ctx.setLineDash(marker === '!' ? [3, 3] : marker === '△' ? [9, 4] : [])
      ctx.stroke()
      ctx.setLineDash([])
      if (marker) {
        const points = coordinates.slice(0, -1).map(([lng, lat]) => project(lng, lat, w, h))
        const center = points.reduce((sum, point) => ({ x: sum.x + point.x, y: sum.y + point.y }), { x: 0, y: 0 })
        center.x /= Math.max(points.length, 1)
        center.y /= Math.max(points.length, 1)
        ctx.beginPath(); ctx.arc(center.x, center.y, 8, 0, Math.PI * 2); ctx.fillStyle = 'rgba(255,255,255,.86)'; ctx.fill()
        ctx.fillStyle = stroke; ctx.font = '800 10px sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(marker, center.x, center.y + .5)
      }
    }
    const currentReport = report.value
    if (currentReport) {
      drawPolygon(currentReport.isochrone.geometry.coordinates[0], 'rgba(61, 155, 139, .22)', '#237866')
      visibleServiceAreas().forEach((zone) => {
        const selected = isSelectedRegion(zone.properties.grid_id)
        const style = serviceAreaStyle(zone, selected, isFocusedRegion(zone.properties.grid_id), hasSelectedRegion() && !selected)
        const marker = zone.properties.kind === 'critical' ? '!' : zone.properties.kind === 'sparse' ? '△' : ''
        if (selected) drawPolygon(zone.geometry.coordinates[0], 'rgba(255,255,255,0)', 'rgba(255,255,255,.96)', 9)
        drawPolygon(zone.geometry.coordinates[0], style.fill, style.stroke, style.strokeWeight, marker)
        if (selected) drawCanvasSelectionMarker(zone, ctx, w, h)
      })
      simulationAreas().forEach((zone) => {
        drawPolygon(zone.geometry.coordinates[0], 'rgba(51, 126, 184, .18)', '#2f70a5', 3)
      })
      const preview = routePreview.value
      if (preview) {
        // 首尾补上起点/终点，保证路线真正连到地图上的两个点
        const drawnPath: [number, number][] = [
          [preview.route.origin.lng, preview.route.origin.lat],
          ...preview.route.polyline,
          [preview.route.destination.lng, preview.route.destination.lat],
        ]
        if (drawnPath.length > 1) {
          const tracePath = () => {
            ctx.beginPath()
            drawnPath.forEach(([lng, lat], index) => {
              const point = project(lng, lat, w, h)
              index ? ctx.lineTo(point.x, point.y) : ctx.moveTo(point.x, point.y)
            })
          }
          // 导航式实线：白色外发光 + 深绿描边 + 浅绿芯线，圆角连接
          ctx.lineJoin = 'round'
          ctx.lineCap = 'round'
          tracePath(); ctx.strokeStyle = 'rgba(255,255,255,.8)'; ctx.lineWidth = 10; ctx.stroke()
          tracePath(); ctx.strokeStyle = ROUTE_BORDER; ctx.lineWidth = 8; ctx.stroke()
          tracePath(); ctx.strokeStyle = ROUTE_COLOR; ctx.lineWidth = 5; ctx.stroke()
          computeRouteArrows(drawnPath, (lng, lat) => project(lng, lat, w, h), (x, y) => unproject(x, y, w, h), ROUTE_ARROW_SPACING)
            .forEach((arrow) => {
              ctx.save()
              ctx.translate(arrow.x, arrow.y)
              ctx.rotate((arrow.bearing * Math.PI) / 180)
              ctx.beginPath()
              ctx.moveTo(-4, -4.5); ctx.lineTo(4.5, 0); ctx.lineTo(-4, 4.5); ctx.lineTo(-1.5, 0); ctx.closePath()
              ctx.fillStyle = 'rgba(255,255,255,.95)'
              ctx.fill()
              ctx.restore()
            })
        }
        const start = project(preview.route.origin.lng, preview.route.origin.lat, w, h)
        const end = project(preview.route.destination.lng, preview.route.destination.lat, w, h)
        drawRouteEndpointLabel(ctx, start.x, start.y - 16, '起点')
        drawRouteEndpointLabel(ctx, end.x, end.y + 16, '终点')
      }
      currentReport.pois.filter((poi) => visibleCategories.value.includes(poi.category)).forEach((poi) => {
        const point = project(poi.lng, poi.lat, w, h)
        ctx.beginPath(); ctx.arc(point.x, point.y, 12, 0, Math.PI * 2); ctx.fillStyle = 'rgba(255,255,255,.96)'; ctx.fill()
        ctx.strokeStyle = categoryColor(poi.category); ctx.lineWidth = 2; ctx.stroke()
        ctx.fillStyle = categoryColor(poi.category); ctx.beginPath(); ctx.arc(point.x, point.y, 8, 0, Math.PI * 2); ctx.fill()
        ctx.font = '700 9px sans-serif'; ctx.fillStyle = '#fff'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(categoryShort(poi.category), point.x, point.y + 1)
        ctx.font = '600 10px sans-serif'; ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic'
        const name = poi.name.length > 10 ? `${poi.name.slice(0, 10)}…` : poi.name
        const labelWidth = ctx.measureText(name).width + 10
        ctx.fillStyle = 'rgba(255,255,255,.92)'; ctx.fillRect(point.x + 15, point.y - 10, labelWidth, 17)
        ctx.fillStyle = '#24434a'; ctx.fillText(name, point.x + 20, point.y + 2)
      })
      visibleCandidates().forEach(({ candidate, recommendation }) => {
        const point = project(candidate.lng, candidate.lat, w, h)
        const focused = recommendation.id === focusRecommendationId.value
        ctx.beginPath(); ctx.arc(point.x, point.y, focused ? 13 : 10, 0, Math.PI * 2)
        ctx.fillStyle = focused ? 'rgba(23, 51, 61, .18)' : 'rgba(47, 143, 128, .13)'; ctx.fill()
        ctx.beginPath(); ctx.moveTo(point.x, point.y - 8); ctx.lineTo(point.x + 8, point.y); ctx.lineTo(point.x, point.y + 8); ctx.lineTo(point.x - 8, point.y); ctx.closePath()
        ctx.fillStyle = focused ? '#17333d' : '#2f8f80'; ctx.fill(); ctx.strokeStyle = '#fff'; ctx.lineWidth = 2; ctx.stroke()
        ctx.font = '700 9px sans-serif'; ctx.fillStyle = '#17333d'; ctx.textAlign = 'left'; ctx.fillText(`${recommendation.category_label}候选点`, point.x + 12, point.y + 3)
      })
      if (simulation.value) {
        const facility = simulation.value.hypothetical_facility
        const point = project(facility.lng, facility.lat, w, h)
        ctx.beginPath(); ctx.arc(point.x, point.y, 15, 0, Math.PI * 2); ctx.fillStyle = 'rgba(47, 112, 165, .2)'; ctx.fill()
        ctx.beginPath(); ctx.moveTo(point.x, point.y - 10); ctx.lineTo(point.x + 10, point.y); ctx.lineTo(point.x, point.y + 10); ctx.lineTo(point.x - 10, point.y); ctx.closePath()
        ctx.fillStyle = '#2f70a5'; ctx.fill(); ctx.strokeStyle = '#fff'; ctx.lineWidth = 2; ctx.stroke()
        ctx.font = '700 10px sans-serif'; ctx.fillStyle = '#214e73'; ctx.textAlign = 'left'; ctx.fillText(`假设${simulation.value.category_label}`, point.x + 15, point.y + 4)
      }
    }
    drawCanvasAnalysisCenter(ctx, analysisCenter.value, (lng, lat) => project(lng, lat, w, h), currentReport?.isochrone.properties.minutes || 15)
  }

  function visibility() {
    return { normal: showNormal.value, sparse: showSparse.value, critical: showCritical.value, unknown: true }
  }

  function visibleServiceAreas() {
    return (report.value?.service_areas.features || report.value?.zones.features || [])
      .filter((feature) => isServiceAreaVisible(feature, visibleCategories.value, visibility()))
  }

  function serviceAreaStyle(feature: ServiceAreaFeature, selected = false, focused = false, dimmed = false) {
    if (selected) {
      if (feature.properties.kind === 'critical') return { fill: 'rgba(180, 64, 43, .52)', stroke: '#762719', strokeWeight: 5 }
      if (feature.properties.kind === 'sparse') return { fill: 'rgba(205, 142, 37, .50)', stroke: '#815713', strokeWeight: 5 }
      if (feature.properties.kind === 'unknown') return { fill: 'rgba(94, 106, 115, .42)', stroke: '#39444b', strokeWeight: 5 }
      return { fill: 'rgba(45, 138, 105, .36)', stroke: '#145b49', strokeWeight: 5 }
    }
    if (dimmed) {
      if (feature.properties.kind === 'critical') return { fill: 'rgba(199, 92, 67, .10)', stroke: '#c98e80', strokeWeight: 1 }
      if (feature.properties.kind === 'sparse') return { fill: 'rgba(216, 166, 78, .10)', stroke: '#ceb27a', strokeWeight: 1 }
      if (feature.properties.kind === 'unknown') return { fill: 'rgba(123, 135, 144, .08)', stroke: '#a1aaaf', strokeWeight: 1 }
      return { fill: 'rgba(79, 157, 127, .035)', stroke: '#a5c4b7', strokeWeight: 1 }
    }
    if (focused) return { fill: 'rgba(177, 65, 42, .42)', stroke: '#7f2f20', strokeWeight: 4 }
    if (feature.properties.kind === 'critical') return { fill: 'rgba(199, 92, 67, .28)', stroke: '#b74a35', strokeWeight: 2 }
    if (feature.properties.kind === 'sparse') return { fill: 'rgba(216, 166, 78, .27)', stroke: '#c18b31', strokeWeight: 2 }
    if (feature.properties.kind === 'unknown') return { fill: 'rgba(123, 135, 144, .18)', stroke: '#69757d', strokeWeight: 2 }
    return { fill: 'rgba(79, 157, 127, .08)', stroke: '#6eac94', strokeWeight: 2 }
  }

  function hasSelectedRegion() {
    return selectedServiceArea.value !== null
  }

  function isSelectedRegion(regionId: string) {
    return selectedServiceArea.value?.properties.grid_id === regionId
  }

  function drawCanvasSelectionMarker(feature: ServiceAreaFeature, context: CanvasRenderingContext2D, width: number, height: number) {
    const center = serviceAreaCenter(feature)
    const point = project(center.lng, center.lat, width, height)
    context.fillStyle = 'rgba(23, 51, 61, .94)'
    context.fillRect(point.x - 21, point.y - 12, 42, 24)
    context.strokeStyle = '#fff'
    context.lineWidth = 2
    context.strokeRect?.(point.x - 21, point.y - 12, 42, 24)
    context.fillStyle = '#fff'
    context.font = '800 11px sans-serif'
    context.textAlign = 'center'
    context.textBaseline = 'middle'
    context.fillText('已选', point.x, point.y + .5)
  }

  function focusedRecommendation(): PlanningRecommendation | null {
    return report.value?.recommendations.find((item) => item.id === focusRecommendationId.value) || null
  }

  function isFocusedRegion(regionId: string) {
    return focusedRecommendation()?.target_region_ids.includes(regionId) || false
  }

  function visibleCandidates() {
    return (report.value?.recommendations || [])
      .filter((recommendation) => visibleCategories.value.includes(recommendation.category))
      .flatMap((recommendation) => recommendation.candidate_locations.map((candidate) => ({ candidate, recommendation })))
  }

  function simulationAreas() {
    return simulation.value?.after.service_areas.features || []
  }

  function handleCanvasClick(event: MouseEvent) {
    const canvas = mapCanvas.value
    if (!canvas || realMapReady.value) return
    const rect = canvas.getBoundingClientRect()
    const point = { x: event.clientX - rect.left, y: event.clientY - rect.top }
    if (simulationPicking.value) {
      const location = unproject(point.x, point.y, rect.width, rect.height)
      onSelectSimulationLocation(location.lng, location.lat)
      return
    }
    const poiHit = hitTestPoi(point, rect.width, rect.height)
    if (poiHit) {
      scheduleHover(poiHit.poi, point.x, point.y, true)
      return
    }
    clearHover()
    const candidateHit = [...visibleCandidates()].reverse().find(({ candidate }) => {
      const projected = project(candidate.lng, candidate.lat, rect.width, rect.height)
      return Math.hypot(point.x - projected.x, point.y - projected.y) <= 14
    })
    if (candidateHit) {
      selectedServiceArea.value = serviceAreaById(candidateHit.candidate.region_id)
      return
    }
    const serviceAreaHit = [...visibleServiceAreas()].reverse().find((feature) => {
      const polygon = feature.geometry.coordinates[0].map(([lng, lat]) => project(lng, lat, rect.width, rect.height))
      return pointInPolygon(point, polygon)
    })
    if (serviceAreaHit) {
      selectedServiceArea.value = serviceAreaHit
      return
    }
    selectedServiceArea.value = null
    const location = unproject(point.x, point.y, rect.width, rect.height)
    onSelectCenter(location.lng, location.lat)
  }

  function handleCanvasMouseMove(event: MouseEvent) {
    if (realMapReady.value || simulationPicking.value) return
    const canvas = mapCanvas.value
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const point = { x: event.clientX - rect.left, y: event.clientY - rect.top }
    const hit = hitTestPoi(point, rect.width, rect.height)
    if (!hit) { requestClearHover(); return }
    if (hoverTarget.value?.poi.id === hit.poi.id) return
    scheduleHover(hit.poi, point.x, point.y)
  }

  function handleCanvasMouseLeave() {
    if (realMapReady.value) return
    clearHover()
  }

  function serviceAreaById(regionId: string): ServiceAreaFeature | null {
    return (report.value?.service_areas.features || report.value?.zones.features || [])
      .find((feature) => feature.properties.grid_id === regionId) || null
  }
  function loadScript(src: string) {
    return new Promise<void>((resolve, reject) => {
      const script = document.createElement('script')
      script.src = src
      script.onload = () => resolve()
      script.onerror = () => reject(new Error('百度地图 JavaScript API 加载失败'))
      document.head.appendChild(script)
    })
  }

  async function loadBaiduMap() {
    try {
      const config = await fetchMapConfig()
      if (config.mode !== 'real' || !config.browser_ak) return
      ;(window as any).__lifeCircleBaiduReady = () => undefined
      await loadScript(`https://api.map.baidu.com/api?v=3.0&ak=${encodeURIComponent(config.browser_ak)}&callback=__lifeCircleBaiduReady`)
      await new Promise<void>((resolve, reject) => {
        const timer = window.setInterval(() => {
          if ((window as any).BMap) { window.clearInterval(timer); resolve() }
        }, 50)
        window.setTimeout(() => { window.clearInterval(timer); reject(new Error('百度地图初始化超时')) }, 8000)
      })
      realMapReady.value = true
      await nextTick()
      renderBaiduMap()
    } catch {
      ElMessage.warning('百度地图底图加载失败，请检查浏览器端 AK 的域名白名单')
    } finally {
      // 无论使用真实底图还是 Canvas 降级图，都只在地图探测结束后通知页面开始首次分析。
      mapLoadComplete.value = true
    }
  }

  function renderBaiduMap() {
    const BMap = (window as any).BMap
    if (!BMap || !mapContainer.value) return
    clearHover()
    if (!baiduMap) {
      baiduMap = new BMap.Map(mapContainer.value)
      baiduMap.enableScrollWheelZoom(true)
      baiduMap.addControl(new BMap.NavigationControl({ anchor: (window as any).BMAP_ANCHOR_TOP_RIGHT }))
      baiduMap.addControl(new BMap.ScaleControl({ anchor: (window as any).BMAP_ANCHOR_BOTTOM_LEFT }))
    }
    if (!baiduClickBound) {
      baiduMap.addEventListener('click', (event: any) => {
        if (simulationPicking.value) onSelectSimulationLocation(event.point.lng, event.point.lat)
        else onSelectCenter(event.point.lng, event.point.lat)
      })
      baiduMap.addEventListener('movestart', () => clearHover())
      baiduMap.addEventListener('zoomstart', () => clearHover())
      baiduClickBound = true
    }
    const center = new BMap.Point(analysisCenter.value.lng, analysisCenter.value.lat)
    const selectedCenter = selectedServiceArea.value ? serviceAreaCenter(selectedServiceArea.value) : null
    const focusedCandidate = focusedRecommendation()?.candidate_locations[0]
    const hypothetical = simulation.value?.hypothetical_facility
    const viewCenter = selectedCenter
      ? new BMap.Point(selectedCenter.lng, selectedCenter.lat)
      : hypothetical
      ? new BMap.Point(hypothetical.lng, hypothetical.lat)
      : focusedCandidate ? new BMap.Point(focusedCandidate.lng, focusedCandidate.lat) : center
    baiduMap.centerAndZoom(viewCenter, selectedCenter || hypothetical || focusedCandidate ? 17 : 16)
    baiduMap.clearOverlays()
    const currentReport = report.value
    if (currentReport) {
      const polygon = currentReport.isochrone.geometry.coordinates[0].map(([lng, lat]) => new BMap.Point(lng, lat))
      baiduMap.addOverlay(new BMap.Polygon(polygon, { strokeColor: '#237866', strokeWeight: 4, strokeOpacity: .95, strokeStyle: 'dashed', fillColor: '#3d9b8b', fillOpacity: .2 }))
      visibleServiceAreas().forEach((zone) => {
        const points = zone.geometry.coordinates[0].map(([lng, lat]) => new BMap.Point(lng, lat))
        const selected = isSelectedRegion(zone.properties.grid_id)
        const focused = isFocusedRegion(zone.properties.grid_id)
        const dimmed = hasSelectedRegion() && !selected
        const style = serviceAreaStyle(zone, selected, focused, dimmed)
        if (selected) {
          baiduMap.addOverlay(new BMap.Polygon(points, {
            strokeColor: '#ffffff', strokeWeight: 10, strokeOpacity: .96, fillColor: '#ffffff', fillOpacity: 0,
          }))
        }
        const areaPolygon = new BMap.Polygon(points, {
          strokeColor: style.stroke,
          strokeWeight: style.strokeWeight,
          strokeOpacity: dimmed ? .62 : 1,
          strokeStyle: zone.properties.kind === 'normal' ? 'solid' : 'dashed',
          fillColor: selected || focused ? style.stroke : zone.properties.color,
          fillOpacity: selected ? .42 : focused ? .42 : dimmed ? .08 : zone.properties.kind === 'normal' ? .08 : .25,
        })
        areaPolygon.addEventListener('click', (event: any) => {
          selectedServiceArea.value = zone
          event?.domEvent?.stopPropagation?.()
        })
        baiduMap.addOverlay(areaPolygon)
        if (selected) {
          const zoneCenter = serviceAreaCenter(zone)
          const label = new BMap.Label('<span class="selected-area-map-label">已选</span>', {
            position: new BMap.Point(zoneCenter.lng, zoneCenter.lat), offset: new BMap.Size(-21, -13),
          })
          label.setStyle({ border: '0', background: 'transparent', padding: '0', whiteSpace: 'nowrap', zIndex: '60' })
          baiduMap.addOverlay(label)
        }
      })
      simulationAreas().forEach((zone) => {
        const points = zone.geometry.coordinates[0].map(([lng, lat]) => new BMap.Point(lng, lat))
        baiduMap.addOverlay(new BMap.Polygon(points, { strokeColor: '#2f70a5', strokeWeight: 3, strokeOpacity: 1, fillColor: '#6aa2cc', fillOpacity: .18 }))
      })
      const preview = routePreview.value
      if (preview && preview.route.polyline.length > 0) {
        const drawnPath: [number, number][] = [
          [preview.route.origin.lng, preview.route.origin.lat],
          ...preview.route.polyline,
          [preview.route.destination.lng, preview.route.destination.lat],
        ]
        const points = drawnPath.map(([lng, lat]) => new BMap.Point(lng, lat))
        const solid = { strokeStyle: 'solid' as const, strokeLineCap: 'round' as const, strokeLineJoin: 'round' as const }
        // 导航式实线：白色外发光 + 深绿描边 + 浅绿芯线
        baiduMap.addOverlay(new BMap.Polyline(points, { ...solid, strokeColor: '#ffffff', strokeWeight: 10, strokeOpacity: .8 }))
        baiduMap.addOverlay(new BMap.Polyline(points, { ...solid, strokeColor: ROUTE_BORDER, strokeWeight: 8, strokeOpacity: .96 }))
        baiduMap.addOverlay(new BMap.Polyline(points, { ...solid, strokeColor: ROUTE_COLOR, strokeWeight: 5, strokeOpacity: 1 }))
        computeRouteArrows(
          drawnPath,
          (lng, lat) => baiduMap.pointToOverlayPixel(new BMap.Point(lng, lat)),
          (x, y) => baiduMap.overlayPixelToPoint(new BMap.Pixel(x, y)),
          ROUTE_ARROW_SPACING,
        ).forEach((arrow) => {
          const arrowLabel = new BMap.Label(`<span class="route-arrow" style="transform: rotate(${arrow.bearing.toFixed(1)}deg)"></span>`, {
            position: new BMap.Point(arrow.lng, arrow.lat), offset: new BMap.Size(0, 0),
          })
          arrowLabel.setStyle({ border: '0', background: 'transparent', padding: '0', zIndex: '26' })
          baiduMap.addOverlay(arrowLabel)
        })
        const startLabel = new BMap.Label('<span class="route-endpoint-label">起点</span>', {
          position: new BMap.Point(preview.route.origin.lng, preview.route.origin.lat), offset: new BMap.Size(-16, -34),
        })
        startLabel.setStyle({ border: '0', background: 'transparent', padding: '0', zIndex: '27' })
        baiduMap.addOverlay(startLabel)
        const endLabel = new BMap.Label('<span class="route-endpoint-label">终点</span>', {
          position: new BMap.Point(preview.route.destination.lng, preview.route.destination.lat), offset: new BMap.Size(-16, 14),
        })
        endLabel.setStyle({ border: '0', background: 'transparent', padding: '0', zIndex: '27' })
        baiduMap.addOverlay(endLabel)
      }
      visiblePois().forEach((poi) => {
        const point = new BMap.Point(poi.lng, poi.lat)
        const marker = new BMap.Marker(point)
        const showAt = (event: any, sticky = false) => {
          const pixel = event?.pixel || baiduMap.pointToOverlayPixel(point)
          scheduleHover(poi, pixel.x, pixel.y, sticky)
        }
        const label = new BMap.Label(`<span class="facility-map-label facility-${poi.category}"><b>${categoryShort(poi.category)}</b><span>${poi.name}</span></span>`, { position: point, offset: new BMap.Size(-15, -15) })
        label.setStyle({ border: '0', background: 'transparent', padding: '0', whiteSpace: 'nowrap', zIndex: '20' })
        // 名称标签 pill 覆盖在 marker 之上，两者都要绑定悬停，保证鼠标移到可见图形上即弹卡片
        ;[marker, label].forEach((overlay) => {
          overlay.addEventListener('mouseover', (event: any) => showAt(event))
          overlay.addEventListener('mouseout', () => requestClearHover())
          overlay.addEventListener('click', (event: any) => {
            showAt(event, true)
            event?.domEvent?.stopPropagation?.()
          })
        })
        baiduMap.addOverlay(marker)
        baiduMap.addOverlay(label)
      })
      visibleCandidates().forEach(({ candidate, recommendation }) => {
        const point = new BMap.Point(candidate.lng, candidate.lat)
        const marker = new BMap.Marker(point)
        marker.setTitle(`${recommendation.category_label}规划候选点 · ${candidate.region_id}`)
        marker.addEventListener('click', (event: any) => {
          selectedServiceArea.value = serviceAreaById(candidate.region_id)
          event?.domEvent?.stopPropagation?.()
        })
        baiduMap.addOverlay(marker)
        const focused = recommendation.id === focusRecommendationId.value
        const label = new BMap.Label(`<span class="candidate-map-label ${focused ? 'focused' : ''}"><b>候</b><span>${recommendation.category_label}候选点</span></span>`, { position: point, offset: new BMap.Size(14, -11) })
        label.setStyle({ border: '0', background: 'transparent', padding: '0', whiteSpace: 'nowrap', zIndex: focused ? '35' : '24' })
        baiduMap.addOverlay(label)
      })
      if (simulation.value) {
        const facility = simulation.value.hypothetical_facility
        const point = new BMap.Point(facility.lng, facility.lat)
        const marker = new BMap.Marker(point)
        marker.setTitle(`假设${simulation.value.category_label}`)
        baiduMap.addOverlay(marker)
        const label = new BMap.Label(`<span class="simulation-map-label"><b>拟</b><span>假设${simulation.value.category_label}</span></span>`, { position: point, offset: new BMap.Size(14, -11) })
        label.setStyle({ border: '0', background: 'transparent', padding: '0', whiteSpace: 'nowrap', zIndex: '40' })
        baiduMap.addOverlay(label)
      }
    }
    renderBaiduAnalysisCenter(baiduMap, BMap, analysisCenter.value, currentReport?.isochrone.properties.minutes || 15)
  }

  function resize() {
    if (realMapReady.value && baiduMap) baiduMap.checkResize()
    else drawMap()
  }

  watch([report, analysisCenter, visibleCategories, showNormal, showSparse, showCritical, focusRecommendationId, simulation, simulationPicking, selectedServiceArea, routePreview], async () => {
    clearHover()
    if (selectedServiceArea.value && !isServiceAreaVisible(selectedServiceArea.value, visibleCategories.value, visibility())) {
      selectedServiceArea.value = null
    }
    const recommendation = focusedRecommendation()
    if (recommendation && !recommendation.target_region_ids.includes(selectedServiceArea.value?.properties.grid_id || '')) {
      selectedServiceArea.value = serviceAreaById(recommendation.target_region_ids[0])
    }
    await nextTick()
    realMapReady.value ? renderBaiduMap() : drawMap()
  })
  // 报告或分析中心变化后，旧路线不再对应新结果，自动清除
  watch([report, analysisCenter], () => { routePreview.value = null })
  onMounted(async () => {
    window.addEventListener('resize', resize)
    window.addEventListener('life-circle:theme', redrawForTheme)
    await loadBaiduMap()
    drawMap()
  })
  onBeforeUnmount(() => {
    window.removeEventListener('resize', resize)
    window.removeEventListener('life-circle:theme', redrawForTheme)
  })

  function redrawForTheme() {
    realMapReady.value ? renderBaiduMap() : drawMap()
  }

  return {
    mapCanvas,
    mapContainer,
    realMapReady,
    mapLoadComplete,
    selectedServiceArea,
    hoverTarget,
    routePreview,
    setRoutePreview: (preview: MapRoutePreview | null) => { routePreview.value = preview },
    retainHover,
    clearHover,
    visibleServiceAreas,
    selectServiceArea: (feature: ServiceAreaFeature) => { selectedServiceArea.value = feature },
    handleCanvasClick,
    handleCanvasMouseMove,
    handleCanvasMouseLeave,
    closeServiceAreaEvidence: () => { selectedServiceArea.value = null },
    drawMap,
    renderBaiduMap,
  }
}
