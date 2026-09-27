import { describe, expect, it } from 'vitest'

import { DEFAULT_CATEGORIES, categoryColor, categoryShort } from './facilities'

describe('民生设施展示配置', () => {
  it('包含核心与扩展民生设施', () => {
    expect(DEFAULT_CATEGORIES).toEqual([
      'market',
      'pharmacy',
      'school',
      'medical',
      'elderly',
      'park',
      'convenience',
    ])
  })

  it('为未知类别提供稳定的地图展示回退值', () => {
    expect(categoryColor('unknown')).toBe('#71838a')
    expect(categoryShort('unknown')).toBe('?')
  })
})
