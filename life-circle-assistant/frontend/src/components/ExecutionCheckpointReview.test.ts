// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ExecutionCheckpointReview from './ExecutionCheckpointReview.vue'
import * as api from '../services/executionApi'
vi.mock('../services/executionApi', () => ({ fetchUncertainCheckpoints: vi.fn(), authorizeCheckpointRetry: vi.fn() }))
const key = 'a'.repeat(64), key2 = 'b'.repeat(64)
const item = { call_key: key, operation: 'walking_matrix', updated_at: '2026-10-14T09:00:00' }
const button = (wrapper: ReturnType<typeof mount>, text: string) => wrapper.findAll('button').find(value => value.text() === text)!
beforeEach(() => { vi.clearAllMocks(); vi.mocked(api.fetchUncertainCheckpoints).mockResolvedValue({ items: [item] }) })

describe('中断调用人工计费核对', () => {
  it('打开组件不会重放或自动授权，人工检查前没有续算入口', async () => {
    const wrapper = mount(ExecutionCheckpointReview, { props: { executionId: 'original-task', allowResume: true } })
    expect(api.fetchUncertainCheckpoints).not.toHaveBeenCalled()
    expect(api.authorizeCheckpointRetry).not.toHaveBeenCalled()
    expect(wrapper.findAll('button')).toHaveLength(1)
    await button(wrapper, '检查未决调用').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain(key)
    expect(button(wrapper, '从原任务断点续算').attributes('disabled')).toBeDefined()
    expect(button(wrapper, '记录核对并授权本项重试').attributes('disabled')).toBeDefined()
  })
  it('逐项要求身份、证据和计费同意，授权后保持原任务且由用户显式续算', async () => {
    const wrapper = mount(ExecutionCheckpointReview, { props: { executionId: 'original-task', allowResume: true } })
    await button(wrapper, '检查未决调用').trigger('click'); await flushPromises()
    await wrapper.get('input:not([type="checkbox"])').setValue('复核员')
    await wrapper.get('textarea').setValue('提供方账单请求123：已确认需重试')
    expect(button(wrapper, '记录核对并授权本项重试').attributes('disabled')).toBeDefined()
    await wrapper.get('input[type="checkbox"]').setValue(true)
    vi.mocked(api.authorizeCheckpointRetry).mockResolvedValue({ status: 'retry_authorized', budget_reset: false, disclosure: '原预算不重置，可能再次计费' })
    vi.mocked(api.fetchUncertainCheckpoints).mockResolvedValue({ items: [] })
    await button(wrapper, '记录核对并授权本项重试').trigger('click'); await flushPromises()
    expect(api.authorizeCheckpointRetry).toHaveBeenCalledWith('original-task', key, '复核员', '提供方账单请求123：已确认需重试')
    expect(wrapper.text()).toContain('原预算不重置')
    expect(wrapper.emitted('resume')).toBeUndefined()
    await button(wrapper, '从原任务断点续算').trigger('click')
    expect(wrapper.emitted('resume')).toHaveLength(1)
  })
  it('一个调用获得授权后，另一个未决调用仍阻止续算且需要独立勾选', async () => {
    vi.mocked(api.fetchUncertainCheckpoints).mockResolvedValue({ items: [item, { ...item, call_key: key2 }] })
    const wrapper = mount(ExecutionCheckpointReview, { props: { executionId: 'original-task', allowResume: true } })
    await button(wrapper, '检查未决调用').trigger('click'); await flushPromises()
    await wrapper.get('input:not([type="checkbox"])').setValue('复核员'); await wrapper.get('textarea').setValue('核对提供方日志')
    await wrapper.findAll('input[type="checkbox"]')[0]!.setValue(true)
    vi.mocked(api.authorizeCheckpointRetry).mockResolvedValue({ status: 'retry_authorized', disclosure: '授权首项' })
    vi.mocked(api.fetchUncertainCheckpoints).mockResolvedValue({ items: [{ ...item, call_key: key2 }] })
    await button(wrapper, '记录核对并授权本项重试').trigger('click'); await flushPromises()
    expect(button(wrapper, '从原任务断点续算').attributes('disabled')).toBeDefined()
    expect(button(wrapper, '记录核对并授权本项重试').attributes('disabled')).toBeDefined()
    expect(wrapper.emitted('resume')).toBeUndefined()
  })
  it('版本冲突或提供方核对失败不解锁续算，切换执行清空所有同意', async () => {
    const wrapper = mount(ExecutionCheckpointReview, { props: { executionId: 'original-task', allowResume: true } })
    await button(wrapper, '检查未决调用').trigger('click'); await flushPromises()
    await wrapper.get('input:not([type="checkbox"])').setValue('复核员'); await wrapper.get('textarea').setValue('核对日志'); await wrapper.get('input[type="checkbox"]').setValue(true)
    vi.mocked(api.authorizeCheckpointRetry).mockRejectedValue(new Error('只允许核对未决检查点'))
    await button(wrapper, '记录核对并授权本项重试').trigger('click'); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toBe('只允许核对未决检查点')
    expect(button(wrapper, '从原任务断点续算').attributes('disabled')).toBeDefined()
    await wrapper.setProps({ executionId: 'another-task' })
    expect(wrapper.findAll('button')).toHaveLength(1)
    await button(wrapper, '检查未决调用').trigger('click'); await flushPromises()
    expect((wrapper.get('input:not([type="checkbox"])').element as HTMLInputElement).value).toBe('')
    expect((wrapper.get('input[type="checkbox"]').element as HTMLInputElement).checked).toBe(false)
  })
  it('迟到的旧执行检查结果不会覆盖新任务，也不会默认发起续算', async () => {
    let resolve!: (value: { items: typeof item[] }) => void
    vi.mocked(api.fetchUncertainCheckpoints).mockReturnValue(new Promise(value => { resolve = value }))
    const wrapper = mount(ExecutionCheckpointReview, { props: { executionId: 'old-task', allowResume: true } })
    await button(wrapper, '检查未决调用').trigger('click')
    await wrapper.setProps({ executionId: 'new-task' }); resolve({ items: [] }); await flushPromises()
    expect(wrapper.findAll('button')).toHaveLength(1)
    expect(wrapper.emitted('resume')).toBeUndefined()
  })
})
