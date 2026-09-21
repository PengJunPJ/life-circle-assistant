import { describe, expect, it } from 'vitest'
import { getDownloadFilename } from './report'

describe('报告导出文件名', () => {
  it('优先读取 UTF-8 中文文件名', () => {
    const header = "attachment; filename=\"report.json\"; filename*=UTF-8''%E7%94%9F%E6%B4%BB%E5%9C%88%E4%BD%93%E6%A3%80.json"
    expect(getDownloadFilename(header, 'fallback.json')).toBe('生活圈体检.json')
  })

  it('缺少或损坏响应头时使用安全回退名', () => {
    expect(getDownloadFilename(null, 'report.csv')).toBe('report.csv')
    expect(getDownloadFilename("attachment; filename*=UTF-8''%E0%A4%A", 'report.csv')).toBe('report.csv')
  })
})
