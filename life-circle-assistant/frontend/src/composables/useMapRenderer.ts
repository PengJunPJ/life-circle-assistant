import { nextTick, onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { FACILITY_LABELS, categoryColor, categoryShort } from '../constants/facilities'
import { drawCanvasAnalysisCenter, renderBaiduAnalysisCenter } from '../mapLayers/analysisCenterLayer'
import { fetchMapConfig } from '../services/analysisApi'
import type { AnalysisCenter } from '../types/location'
import type { Report, ServiceAreaFeature } from '../types/report'
import type { PlanningRecommendation } from '../types/recommendations'
import type { SimulationResult } from '../types/simulation'
import { isServiceAreaVisible, pointInPolygon } from '../utils/serviceAreaLayers'

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

  function project(lng: number, lat: number, width: number, height: number) {
    const center = analysisCenter.value
    return { x: width / 2 + (lng - center.lng) * 42000, y: height / 2 - (lat - center.lat) * 42000 }
  }

  function unproject(x: number, y: number, width: number, height: number) {
    return {
      lng: analysisCenter.value.lng + (x - width / 2) / 42000,
      lat: analysisCenter.value.lat - (y - height / 2) / 42000,
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

    const drawPolygon = (coordinates: number[][], fill: string, stroke: string, lineWidth = 2) => {
      ctx.beginPath()
      coordinates.forEach(([lng, lat], index) => {
        const point = project(lng, lat, w, h)
        index ? ctx.lineTo(point.x, point.y) : ctx.moveTo(point.x, point.y)
      })
      ctx.closePath(); ctx.fillStyle = fill; ctx.fill(); ctx.strokeStyle = stroke; ctx.lineWidth = lineWidth; ctx.stroke()
    }
    const currentReport = report.value
    if (currentReport) {
      drawPolygon(currentReport.isochrone.geometry.coordinates[0], 'rgba(61, 155, 139, .22)', '#237866')
      visibleServiceAreas().forEach((zone) => {
        const style = serviceAreaStyle(zone, isFocusedRegion(zone.properties.grid_id))
        drawPolygon(zone.geometry.coordinates[0], style.fill, style.stroke, style.strokeWeight)
      })
      simulationAreas().forEach((zone) => {
        drawPolygon(zone.geometry.coordinates[0], 'rgba(51, 126, 184, .18)', '#2f70a5', 3)
      })
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
    return { normal: showNormal.value, sparse: showSparse.value, critical: showCritical.value }
  }

  function visibleServiceAreas() {
    return (report.value?.service_areas.features || report.value?.zones.features || [])
      .filter((feature) => isServiceAreaVisible(feature, visibleCategories.value, visibility()))
  }

  function serviceAreaStyle(feature: ServiceAreaFeature, focused = false) {
    if (focused) return { fill: 'rgba(177, 65, 42, .42)', stroke: '#7f2f20', strokeWeight: 4 }
    if (feature.properties.kind === 'critical') return { fill: 'rgba(199, 92, 67, .28)', stroke: '#b74a35', strokeWeight: 2 }
    if (feature.properties.kind === 'sparse') return { fill: 'rgba(216, 166, 78, .27)', stroke: '#c18b31', strokeWeight: 2 }
    return { fill: 'rgba(79, 157, 127, .08)', stroke: '#6eac94', strokeWeight: 2 }
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
      baiduClickBound = true
    }
    const center = new BMap.Point(analysisCenter.value.lng, analysisCenter.value.lat)
    const focusedCandidate = focusedRecommendation()?.candidate_locations[0]
    const hypothetical = simulation.value?.hypothetical_facility
    const viewCenter = hypothetical
      ? new BMap.Point(hypothetical.lng, hypothetical.lat)
      : focusedCandidate ? new BMap.Point(focusedCandidate.lng, focusedCandidate.lat) : center
    baiduMap.centerAndZoom(viewCenter, hypothetical || focusedCandidate ? 17 : 16)
    baiduMap.clearOverlays()
    const currentReport = report.value
    if (currentReport) {
      const polygon = currentReport.isochrone.geometry.coordinates[0].map(([lng, lat]) => new BMap.Point(lng, lat))
      baiduMap.addOverlay(new BMap.Polygon(polygon, { strokeColor: '#237866', strokeWeight: 4, strokeOpacity: .95, strokeStyle: 'dashed', fillColor: '#3d9b8b', fillOpacity: .2 }))
      visibleServiceAreas().forEach((zone) => {
        const points = zone.geometry.coordinates[0].map(([lng, lat]) => new BMap.Point(lng, lat))
        const focused = isFocusedRegion(zone.properties.grid_id)
        const style = serviceAreaStyle(zone, focused)
        const areaPolygon = new BMap.Polygon(points, { strokeColor: style.stroke, strokeWeight: style.strokeWeight, strokeOpacity: 1, fillColor: focused ? '#b1412a' : zone.properties.color, fillOpacity: focused ? .42 : zone.properties.kind === 'normal' ? .08 : .25 })
        areaPolygon.addEventListener('click', (event: any) => {
          selectedServiceArea.value = zone
          event?.domEvent?.stopPropagation?.()
        })
        baiduMap.addOverlay(areaPolygon)
      })
      simulationAreas().forEach((zone) => {
        const points = zone.geometry.coordinates[0].map(([lng, lat]) => new BMap.Point(lng, lat))
        baiduMap.addOverlay(new BMap.Polygon(points, { strokeColor: '#2f70a5', strokeWeight: 3, strokeOpacity: 1, fillColor: '#6aa2cc', fillOpacity: .18 }))
      })
      currentReport.pois.filter((poi) => visibleCategories.value.includes(poi.category)).forEach((poi) => {
        const point = new BMap.Point(poi.lng, poi.lat)
        const marker = new BMap.Marker(point)
        marker.setTitle(`${poi.name} · ${FACILITY_LABELS[poi.category] || poi.category}`)
        baiduMap.addOverlay(marker)
        const label = new BMap.Label(`<span class="facility-map-label facility-${poi.category}"><b>${categoryShort(poi.category)}</b><span>${poi.name}</span></span>`, { position: point, offset: new BMap.Size(-15, -15) })
        label.setStyle({ border: '0', background: 'transparent', padding: '0', whiteSpace: 'nowrap', zIndex: '20' })
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

  watch([report, analysisCenter, visibleCategories, showNormal, showSparse, showCritical, focusRecommendationId, simulation, simulationPicking], async () => {
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
  onMounted(async () => {
    window.addEventListener('resize', resize)
    await loadBaiduMap()
    drawMap()
  })
  onBeforeUnmount(() => {
    window.removeEventListener('resize', resize)
  })

  return {
    mapCanvas,
    mapContainer,
    realMapReady,
    mapLoadComplete,
    selectedServiceArea,
    handleCanvasClick,
    closeServiceAreaEvidence: () => { selectedServiceArea.value = null },
    drawMap,
    renderBaiduMap,
  }
}
