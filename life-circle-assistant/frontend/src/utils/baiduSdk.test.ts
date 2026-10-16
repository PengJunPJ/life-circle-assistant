// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { loadBaiduSdk } from './baiduSdk'

afterEach(() => { vi.useRealTimers(); document.head.innerHTML = ''; delete (window as any).BMap })

describe('百度 SDK 就绪判断', () => {
  it('已有 BMap 命名空间且脚本加载完成时，仍需等待官方回调', async () => {
    vi.useFakeTimers()
    ;(window as any).BMap = { Map: vi.fn() }
    const ready = loadBaiduSdk('test-key', 100)
    const rejected = expect(ready).rejects.toThrow('初始化超时')
    document.head.querySelector('script')!.dispatchEvent(new Event('load'))
    await vi.advanceTimersByTimeAsync(100)
    await rejected
  })
  it('官方回调确认可用后才完成加载', async () => {
    const ready = loadBaiduSdk('test-key')
    ;(window as any).BMap = { Map: vi.fn() }
    ;(window as any).__lifeCircleBaiduReady()
    await expect(ready).resolves.toBeUndefined()
  })
})
