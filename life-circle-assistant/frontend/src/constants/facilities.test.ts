import { describe, expect, it } from 'vitest'

import { ALL_CATEGORIES, DEFAULT_CENTER, categoryColor, categoryShort } from './facilities'

describe('民生设施展示配置', () => {
  it('包含核心与扩展民生设施', () => {
    expect(ALL_CATEGORIES).toEqual([
      'medical',
      'school',
      'convenience',
      'elderly',
      'market',
      'pharmacy',
      'park',
    ])
  })

  it('为未知类别提供稳定的地图展示回退值', () => {
    expect(categoryColor('unknown')).toBe('#71838a')
    expect(categoryShort('unknown')).toBe('?')
  })

  it('使用沙涌长盛花园核查坐标作为默认分析中心', () => {
    expect(DEFAULT_CENTER).toEqual({
      lng: 113.53382359909054,
      lat: 23.08901171541019,
    })
  })
})
