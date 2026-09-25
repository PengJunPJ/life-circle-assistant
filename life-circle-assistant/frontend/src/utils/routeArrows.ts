export type RouteArrow = { x: number; y: number; lng: number; lat: number; bearing: number }

/**
 * 沿折线按像素间距等距采样箭头点，bearing 为屏幕坐标下的朝向角（度，0=向右）。
 * 首枚箭头从半间距开始，避免贴着起/终点。
 */
export function computeRouteArrows(
  path: [number, number][],
  toPixel: (lng: number, lat: number) => { x: number; y: number },
  fromPixel: (x: number, y: number) => { lng: number; lat: number },
  spacing = 48,
): RouteArrow[] {
  const pixels = path.map(([lng, lat]) => ({ ...toPixel(lng, lat), lng, lat }))
  const arrows: RouteArrow[] = []
  let distToNext = spacing / 2
  for (let i = 1; i < pixels.length; i += 1) {
    const a = pixels[i - 1]
    const b = pixels[i]
    const segLen = Math.hypot(b.x - a.x, b.y - a.y)
    if (segLen <= 0) continue
    const bearing = (Math.atan2(b.y - a.y, b.x - a.x) * 180) / Math.PI
    let pos = 0
    while (pos + distToNext <= segLen) {
      pos += distToNext
      // 末点即终点，不压箭头，避免与终点标注重叠
      if (!(i === pixels.length - 1 && pos >= segLen - 1)) {
        const x = a.x + ((b.x - a.x) * pos) / segLen
        const y = a.y + ((b.y - a.y) * pos) / segLen
        const geo = fromPixel(x, y)
        arrows.push({ x, y, lng: geo.lng, lat: geo.lat, bearing })
      }
      distToNext = spacing
    }
    distToNext -= segLen - pos
  }
  return arrows
}
