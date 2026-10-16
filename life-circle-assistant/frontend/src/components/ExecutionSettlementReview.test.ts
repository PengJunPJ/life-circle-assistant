// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ExecutionSettlementReview from './ExecutionSettlementReview.vue'
import * as api from '../services/executionApi'
import type { ExecutionLedger } from '../types/report'
vi.mock('../services/executionApi', () => ({ fetchExecutionLedger: vi.fn(), fetchExecutionSettlements: vi.fn(), recordExecutionSettlement: vi.fn() }))
const fingerprint = 'a'.repeat(64), changedFingerprint = 'b'.repeat(64)
const ledger: ExecutionLedger = { id: 'execution-1', status: 'completed', budget: { route_pairs: 5000 }, usage: { route_pairs: 10 }, versions: { rules: 'v1' }, cost: { currency: 'CNY', estimated_total: 99, settled_total: null, status: 'estimate_only', settlement_version: 0, usage_sha256: fingerprint, settlement_stale: false } }
const settlement: api.ExecutionSettlement = { version: 1, amount_cny: 0, bill_reference: '账单123', reviewer: '复核员', evidence: '已核验免费额度及本次执行全部调用归属', usage_sha256: fingerprint, created_at: '2026-10-14T10:00:00', scope: 'execution_total', currency: 'CNY' }
const button = (wrapper: ReturnType<typeof mount>, text: string) => wrapper.findAll('button').find(value => value.text() === text)!
const field = (wrapper: ReturnType<typeof mount>, label: string) => wrapper.findAll('label').find(value => value.text() === label)!.get('input,textarea')
const mountReview = () => mount(ExecutionSettlementReview, { props: { executionId: ledger.id } })
const read = async (wrapper: ReturnType<typeof mount>) => { await button(wrapper, '读取账本与结算历史').trigger('click'); await flushPromises() }
const fill = async (wrapper: ReturnType<typeof mount>, amount = '0') => {
  await field(wrapper, '本次执行全部费用（人民币元）').setValue(amount)
  await field(wrapper, '提供方账单编号或引用').setValue(settlement.bill_reference)
  await field(wrapper, '结算复核人').setValue(settlement.reviewer)
  await field(wrapper, '全部费用核验依据').setValue(settlement.evidence)
  await wrapper.get('input[type="checkbox"]').setValue(true)
}
beforeEach(() => { vi.clearAllMocks(); vi.mocked(api.fetchExecutionLedger).mockResolvedValue(structuredClone(ledger)); vi.mocked(api.fetchExecutionSettlements).mockResolvedValue({ items: [] }) })
describe('执行全部费用人工账单结算', () => {
  it('不会自动取账单或用估算预填结算，要求用户明确读取和核验来源', async () => {
    const wrapper = mountReview()
    expect(api.fetchExecutionLedger).not.toHaveBeenCalled(); expect(api.recordExecutionSettlement).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('复核人姓名仅作为审计记录')
    await read(wrapper)
    expect((field(wrapper, '本次执行全部费用（人民币元）').element as HTMLInputElement).value).toBe('')
    expect(button(wrapper, '记录人工结算').attributes('disabled')).toBeDefined()
    await fill(wrapper)
    await field(wrapper, '全部费用核验依据').setValue('')
    await wrapper.get('input[type="checkbox"]').setValue(true)
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.recordExecutionSettlement).not.toHaveBeenCalled()
  })
  it('零金额具有账单依据和显式核验后合法，带原版本/用量指纹并刷新账本历史', async () => {
    const wrapper = mountReview(); await read(wrapper); await fill(wrapper)
    const settledLedger = { ...ledger, cost: { ...ledger.cost, status: 'manually_reconciled', settled_total: 0, settlement_version: 1 } }
    vi.mocked(api.recordExecutionSettlement).mockResolvedValue(settlement); vi.mocked(api.fetchExecutionLedger).mockResolvedValue(settledLedger); vi.mocked(api.fetchExecutionSettlements).mockResolvedValue({ items: [settlement] })
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.recordExecutionSettlement).toHaveBeenCalledWith(ledger.id, { amount_cny: '0', bill_reference: settlement.bill_reference, reviewer: settlement.reviewer, evidence: settlement.evidence, expected_version: 0, expected_usage_sha256: fingerprint, scope: 'execution_total' })
    expect(api.fetchExecutionLedger).toHaveBeenCalledTimes(2); expect(api.fetchExecutionSettlements).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('已记录人工结算：0 CNY'); expect(wrapper.get('[aria-label="结算审计历史"]').text()).toContain('账单123')
    expect(wrapper.emitted('ledger')?.at(-1)).toEqual([settledLedger])
    expect((field(wrapper, '本次执行全部费用（人民币元）').element as HTMLInputElement).value).toBe('')
    expect((wrapper.get('input[type="checkbox"]').element as HTMLInputElement).checked).toBe(false)
  })
  it.each(['-1', 'NaN', 'Infinity', '1e3', '0.001', '1000000000000.00'])('拒绝不合法金额%s，直接提交事件也不能调用结算API', async value => {
    const wrapper = mountReview(); await read(wrapper); await fill(wrapper, value)
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(button(wrapper, '记录人工结算').attributes('disabled')).toBeDefined(); expect(api.recordExecutionSettlement).not.toHaveBeenCalled()
  })
  it.each(['running', 'queued', 'unknown'])('非终态%s禁止结算，即使字段齐全也不发送请求', async status => {
    vi.mocked(api.fetchExecutionLedger).mockResolvedValue({ ...ledger, status })
    const wrapper = mountReview(); await read(wrapper); await fill(wrapper)
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.text()).toContain('执行尚未结束'); expect(api.recordExecutionSettlement).not.toHaveBeenCalled()
  })
  it.each(['completed', 'failed', 'cancelled', 'interrupted'])('终态%s读取完整版本并经人工确认后可录入', async status => {
    vi.mocked(api.fetchExecutionLedger).mockResolvedValue({ ...ledger, status })
    const wrapper = mountReview(); await read(wrapper); await fill(wrapper, '12.34')
    expect(button(wrapper, '记录人工结算').attributes('disabled')).toBeUndefined()
  })
  it('版本或用量冲突后不能自动重试；重新读取账本且再次人工确认才解锁', async () => {
    const wrapper = mountReview(); await read(wrapper); await fill(wrapper)
    vi.mocked(api.recordExecutionSettlement).mockRejectedValue(new Error('执行用量已变化，请重新核对账单'))
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('用量已变化')
    await wrapper.get('form').trigger('submit'); expect(api.recordExecutionSettlement).toHaveBeenCalledTimes(1)
    vi.mocked(api.fetchExecutionLedger).mockResolvedValue({ ...ledger, cost: { ...ledger.cost, usage_sha256: changedFingerprint } })
    await read(wrapper)
    expect(button(wrapper, '记录人工结算').attributes('disabled')).toBeDefined()
    await wrapper.get('input[type="checkbox"]').setValue(true)
    expect(button(wrapper, '记录人工结算').attributes('disabled')).toBeUndefined()
  })
  it('恢复执行用量变化后保留审计历史，明确旧结算过时且不预填旧金额', async () => {
    vi.mocked(api.fetchExecutionLedger).mockResolvedValue({ ...ledger, cost: { ...ledger.cost, settled_total: null, status: 'settlement_stale', settlement_stale: true, settlement_version: 1, usage_sha256: changedFingerprint } })
    vi.mocked(api.fetchExecutionSettlements).mockResolvedValue({ items: [settlement] })
    const wrapper = mountReview(); await read(wrapper)
    expect(wrapper.get('.settlement-stale').text()).toContain('原金额不代表本次执行全部费用')
    expect(wrapper.get('[aria-label="结算审计历史"]').text()).toContain('版本 1 · 0 CNY')
    expect((field(wrapper, '本次执行全部费用（人民币元）').element as HTMLInputElement).value).toBe('')
    await fill(wrapper, '2.50'); vi.mocked(api.recordExecutionSettlement).mockRejectedValue(new Error('拒绝测试写入'))
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.recordExecutionSettlement).toHaveBeenCalledWith(ledger.id, expect.objectContaining({ amount_cny: '2.50', expected_version: 1, expected_usage_sha256: changedFingerprint }))
  })
  it('账本和历史并发读取出现版本不一致时禁止使用过期预期版本', async () => {
    vi.mocked(api.fetchExecutionSettlements).mockResolvedValue({ items: [settlement] })
    const wrapper = mountReview(); await read(wrapper); await fill(wrapper)
    expect(wrapper.get('[role="alert"]').text()).toContain('版本已变化')
    await wrapper.get('form').trigger('submit'); expect(api.recordExecutionSettlement).not.toHaveBeenCalled()
  })
  it('服务端已记录但随后刷新失败时明确披露，禁止直接重复提交', async () => {
    const wrapper = mountReview(); await read(wrapper); await fill(wrapper)
    vi.mocked(api.recordExecutionSettlement).mockResolvedValue(settlement)
    vi.mocked(api.fetchExecutionLedger).mockRejectedValue(new Error('账本暂不可读'))
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('结算已记录，但最新账本未能确认')
    await wrapper.get('form').trigger('submit')
    expect(api.recordExecutionSettlement).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).not.toContain('账本与历史已刷新')
  })
  it('切换执行后迟到的旧账本不会覆盖新任务，全部人工字段和确认清空', async () => {
    let resolve!: (value: ExecutionLedger) => void
    vi.mocked(api.fetchExecutionLedger).mockReturnValue(new Promise(value => { resolve = value }))
    const wrapper = mountReview(); await button(wrapper, '读取账本与结算历史').trigger('click')
    await wrapper.setProps({ executionId: 'another-execution' }); resolve(ledger); await flushPromises()
    expect(wrapper.find('form').exists()).toBe(false); expect(wrapper.emitted('ledger')).toBeUndefined()
    vi.mocked(api.fetchExecutionLedger).mockResolvedValue({ ...ledger, id: 'another-execution' }); await read(wrapper)
    expect((field(wrapper, '提供方账单编号或引用').element as HTMLInputElement).value).toBe('')
    expect((wrapper.get('input[type="checkbox"]').element as HTMLInputElement).checked).toBe(false)
  })
})
