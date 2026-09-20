import { nextTick, onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { FACILITY_LABELS, categoryColor, categoryShort } from '../constants/facilities'
import { drawCanvasAnalysisCenter, renderBaiduAnalysisCenter } from '../mapLayers/analysisCenterLayer'
import { fetchMapConfig } from '../services/analysisApi'
import type { AnalysisCenter } from '../types/location'
import type { Report, ServiceAreaFeature } from '../types/report'
import { isServiceAreaVisible, pointInPolygon } from '../utils/serviceAreaLayers'

type MapRendererOptions = {
  report: Ref<Report | null>
  analysisCenter: Ref<AnalysisCenter>
  visibleCategories: Ref<string[]>
  showNormal: Ref<boolean>
  showSparse: Ref<boolean>
  showCritical: Ref<boolean>
  onSelectCenter: (lng: number, lat: number) => void
}

export function useMapRenderer({ report, analysisCenter, visibleCategories, showNormal, showSparse, showCritical, onSelectCenter }: MapRendererOptions) {
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

    const drawPolygon = (coordinates: number[][], fill: string, stroke: string) => {
      ctx.beginPath()
      coordinates.forEach(([lng, lat], index) => {
        const point = project(lng, lat, w, h)
        index ? ctx.lineTo(point.x, point.y) : ctx.moveTo(point.x, point.y)
      })
      ctx.closePath(); ctx.fillStyle = fill; ctx.fill(); ctx.strokeStyle = stroke; ctx.lineWidth = 2; ctx.stroke()
    }
    const currentReport = report.value
    if (currentReport) {
      drawPolygon(currentReport.isochrone.geometry.coordinates[0], 'rgba(61, 155, 139, .22)', '#237866')
      visibleServiceAreas().forEach((zone) => {
        const style = serviceAreaStyle(zone)
        drawPolygon(zone.geometry.coordinates[0], style.fill, style.stroke)
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

  function serviceAreaStyle(feature: ServiceAreaFeature) {
    if (feature.properties.kind === 'critical') return { fill: 'rgba(199, 92, 67, .28)', stroke: '#b74a35' }
    if (feature.properties.kind === 'sparse') return { fill: 'rgba(216, 166, 78, .27)', stroke: '#c18b31' }
    return { fill: 'rgba(79, 157, 127, .08)', stroke: '#6eac94' }
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
      baiduMap.addEventListener('click', (event: any) => onSelectCenter(event.point.lng, event.point.lat))
      baiduClickBound = true
    }
    const center = new BMap.Point(analysisCenter.value.lng, analysisCenter.value.lat)
    baiduMap.centerAndZoom(center, 16)
    baiduMap.clearOverlays()
    const currentReport = report.value
    if (currentReport) {
      const polygon = currentReport.isochrone.geometry.coordinates[0].map(([lng, lat]) => new BMap.Point(lng, lat))
      baiduMap.addOverlay(new BMap.Polygon(polygon, { strokeColor: '#237866', strokeWeight: 4, strokeOpacity: .95, strokeStyle: 'dashed', fillColor: '#3d9b8b', fillOpacity: .2 }))
      visibleServiceAreas().forEach((zone) => {
        const points = zone.geometry.coordinates[0].map(([lng, lat]) => new BMap.Point(lng, lat))
        const style = serviceAreaStyle(zone)
        const areaPolygon = new BMap.Polygon(points, { strokeColor: style.stroke, strokeWeight: 2, strokeOpacity: .9, fillColor: zone.properties.color, fillOpacity: zone.properties.kind === 'normal' ? .08 : .25 })
        areaPolygon.addEventListener('click', (event: any) => {
          selectedServiceArea.value = zone
          event?.domEvent?.stopPropagation?.()
        })
        baiduMap.addOverlay(areaPolygon)
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
    }
    renderBaiduAnalysisCenter(baiduMap, BMap, analysisCenter.value, currentReport?.isochrone.properties.minutes || 15)
  }

  function handleCanvasClick(event: MouseEvent) {
    const canvas = mapCanvas.value
    if (!canvas || realMapReady.value) return
    const rect = canvas.getBoundingClientRect()
    const canvasPoint = { x: event.clientX - rect.left, y: event.clientY - rect.top }
    const hit = [...visibleServiceAreas()].reverse().find((feature) => {
      const polygon = feature.geometry.coordinates[0].map(([lng, lat]) => project(lng, lat, rect.width, rect.height))
      return pointInPolygon(canvasPoint, polygon)
    })
    if (hit) {
      selectedServiceArea.value = hit
      return
    }
    selectedServiceArea.value = null
    const location = unproject(canvasPoint.x, canvasPoint.y, rect.width, rect.height)
    onSelectCenter(location.lng, location.lat)
  }

  function resize() {
    if (realMapReady.value && baiduMap) baiduMap.checkResize()
    else drawMap()
  }

  watch([report, analysisCenter, visibleCategories, showNormal, showSparse, showCritical], async () => {
    if (selectedServiceArea.value && !isServiceAreaVisible(selectedServiceArea.value, visibleCategories.value, visibility())) {
      selectedServiceArea.value = null
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
