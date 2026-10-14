import { afterEach, describe, expect, it, vi } from 'vitest'
import { authorizeCheckpointRetry, fetchExecutionLedger, fetchExecutionSettlements, fetchUncertainCheckpoints, recordExecutionSettlement } from './executionApi'
afterEach(() => vi.unstubAllGlobals())
describe('执行核对协议', () => {
  it('未决检查只读，人工授权带完整证据且不申请重置预算', async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'retry_authorized', disclosure: '可能再次计费' }) }); vi.stubGlobal('fetch', fetch)
    await fetchUncertainCheckpoints('task/id')
    expect(fetch).toHaveBeenLastCalledWith(expect.stringContaining('/api/executions/task%2Fid/uncertain-checkpoints'), undefined)
    await authorizeCheckpointRetry('task/id', 'a'.repeat(64), '复核人', '账单请求123')
    const [url, request] = fetch.mock.calls[1]!
    expect(url).toContain('/api/executions/task%2Fid/reconcile')
    expect(request.method).toBe('POST')
    expect(JSON.parse(request.body)).toEqual({ call_key: 'a'.repeat(64), reviewer: '复核人', evidence: '账单请求123' })
  })
  it('服务端拒绝时保留核对原因，不能伪造授权成功', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, json: async () => ({ detail: '已完成调用不得重放' }) }))
    await expect(authorizeCheckpointRetry('task', 'a'.repeat(64), '复核人', '依据')).rejects.toThrow('已完成调用不得重放')
  })
  it('账本和结算历史只读，人工结算保留人民币小数字符串及并发校验字段', async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items: [] }) }); vi.stubGlobal('fetch', fetch)
    await fetchExecutionLedger('task/id')
    expect(fetch).toHaveBeenLastCalledWith(expect.stringContaining('/api/executions/task%2Fid'), undefined)
    await fetchExecutionSettlements('task/id')
    expect(fetch).toHaveBeenLastCalledWith(expect.stringContaining('/api/executions/task%2Fid/settlements'), undefined)
    const input = { amount_cny: '0.00', bill_reference: '账单123', reviewer: '复核员', evidence: '已核验本次执行全部费用', expected_version: 0, expected_usage_sha256: 'a'.repeat(64), scope: 'execution_total' as const }
    await recordExecutionSettlement('task/id', input)
    const [url, request] = fetch.mock.calls[2]!
    expect(url).toContain('/api/executions/task%2Fid/settlements'); expect(request.method).toBe('POST'); expect(JSON.parse(request.body)).toEqual(input)
  })
})
