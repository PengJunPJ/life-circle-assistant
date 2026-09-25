import { describe, expect, it } from 'vitest'
import { computeRouteArrows } from './routeArrows'

describe('步行路线方向箭头采样', () => {
  const toPixel = (lng: number, lat: number) => ({ x: lng * 10, y: lat * 10 })
  const fromPixel = (x: number, y: number) => ({ lng: x / 10, lat: y / 10 })

  it('沿直线等距采样且不在终点压箭头', () => {
    const path: [number, number][] = [[0, 0], [0, 10]]
    const arrows = computeRouteArrows(path, toPixel, fromPixel, 40)
    // 像素总长 100：半间距 20 起采，60 再一枚；100 为终点被跳过
    expect(arrows.map((a) => a.y)).toEqual([20, 60])
    expect(arrows.every((a) => a.bearing === 90)).toBe(true)
  })

  it('折线跨段累计间距并保持各段朝向', () => {
    const path: [number, number][] = [[0, 0], [0, 5], [5, 5]]
    const arrows = computeRouteArrows(path, toPixel, fromPixel, 30)
    expect(arrows.length).toBeGreaterThan(0)
    const bearings = arrows.map((a) => Math.round(a.bearing))
    expect(bearings.some((b) => b === 90)).toBe(true)
    expect(bearings.some((b) => b === 0)).toBe(true)
  })
})
