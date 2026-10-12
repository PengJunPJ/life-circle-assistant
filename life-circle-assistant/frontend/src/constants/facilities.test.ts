import { describe, expect, it } from 'vitest'

import { ALL_CATEGORIES, categoryColor, categoryShort } from './facilities'

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
})
