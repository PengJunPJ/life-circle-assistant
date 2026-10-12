// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AiPlanningAssistant from './AiPlanningAssistant.vue'
import { fetchReportInterpretations, interpretReport, planReport } from '../services/analysisApi'
import type { PlanningResponse } from '../types/planning'
import type { Report } from '../types/report'
import type { SimulationResult } from '../types/simulation'

vi.mock('../services/analysisApi', () => ({ fetchReportInterpretations: vi.fn(), interpretReport: vi.fn(), planReport: vi.fn() }))
const report = { report_id: 'report-one', parameters: { categories: ['market'] } } as Report
const simulation = {
  id: 'sim-one', report_id: report.report_id, category: 'market', category_label: '菜市场',
  selection_method: 'map', candidate_id: null, hypothetical_facility: { lng: 113.5, lat: 23.1 },
} as SimulationResult
function response(patch: Partial<PlanningResponse> = {}): PlanningResponse {
  return {
    id: 'turn-one', report_id: report.report_id, question: '查询菜市场', intent: 'ask',
    mode: 'llm_tools', model: '测试工具模型', prompt_version: 'tool-planner-v1',
    summary: '先核验服务盲区，再评估候选点。', recommendations: [], evidence_refs: [],
    data_quality_notice: '当前报告快照', boundary_notice: '假设模拟不修改报告', generated_at: '2026-10-12T00:00:00Z',
    tool_calls: [{ id: 'tool-one', name: 'query_facilities', label: '设施查询', arguments: { category: 'market' },
      status: 'completed', duration_ms: 8, result: { summary: '匹配2处设施', source: 'report_snapshot', items: [
        { id: 'market-one', name: '测试菜市场', walk_minutes: 9, source: 'local_snapshot' },
      ] } }], simulations: [], ...patch,
  }
}
function setup(extra = {}) { return mount(AiPlanningAssistant, { props: { report, ...extra } }) }
async function ask(wrapper: ReturnType<typeof setup>, value = '查询菜市场') {
  await wrapper.get('input').setValue(value)
  await wrapper.get('.ai-question button').trigger('click')
  await flushPromises()
}

describe('工具规划助手', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.mocked(fetchReportInterpretations).mockResolvedValue({ items: [] })
    vi.mocked(planReport).mockResolvedValue(response())
  })

  it('问答走工具接口并展示实际结果、参数和来源', async () => {
    const wrapper = setup()
    await ask(wrapper)
    expect(planReport).toHaveBeenCalledWith(report.report_id, expect.objectContaining({ message: '查询菜市场' }), expect.any(AbortSignal))
    expect(interpretReport).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('大模型 · 工具调用')
    expect(wrapper.text()).toContain('匹配2处设施')
    expect(wrapper.text()).toContain('测试菜市场')
    expect(wrapper.text()).toContain('当前报告快照')
    expect(wrapper.text()).toContain('调用参数')
    expect(wrapper.text()).toContain('已执行')
  })

  it('追问携带服务端轮次和当前地图选点及网格', async () => {
    const wrapper = setup({ gridId: 'market-r1c1', simulationLocation: { lng: 113.5, lat: 23.1, selectionMethod: 'map' } })
    await ask(wrapper)
    await ask(wrapper, '它能改善多少？')
    expect(planReport).toHaveBeenLastCalledWith(report.report_id, {
      message: '它能改善多少？', previous_turn_id: 'turn-one', grid_id: 'market-r1c1', selected_location: { lng: 113.5, lat: 23.1 },
    }, expect.any(AbortSignal))
    expect(wrapper.text()).toContain('已采用你在地图上的选点')
    await wrapper.get('.ai-new-topic').trigger('click')
    await ask(wrapper, '查询小学')
    expect(vi.mocked(planReport).mock.lastCall?.[1].previous_turn_id).toBeUndefined()
  })

  it('完成的模拟发给地图，快捷模拟也走工具接口', async () => {
    vi.mocked(planReport).mockResolvedValue(response({ simulations: [simulation] }))
    const wrapper = setup()
    await flushPromises()
    await wrapper.findAll('.ai-actions button')[2]!.trigger('click')
    await flushPromises()
    expect(vi.mocked(planReport).mock.lastCall?.[1].message).toContain('模拟新增一个菜市场')
    expect(wrapper.emitted('simulation-result')?.[0]).toEqual([simulation])
    expect(wrapper.text()).toContain('在地图查看本次模拟')
  })

  it('失败工具显示失败而不会发出模拟成功事件', async () => {
    vi.mocked(planReport).mockResolvedValue(response({ mode: 'tool_rules_degraded', tool_calls: [
      { id: 'failed', name: 'simulate_facility', label: '规划模拟', arguments: { category: 'market' }, status: 'failed', duration_ms: 1, error: '候选点不存在' },
    ] }))
    const wrapper = setup()
    await ask(wrapper)
    expect(wrapper.text()).toContain('已降级')
    expect(wrapper.get('.planning-tools').text()).toContain('失败')
    expect(wrapper.get('.planning-tools').text()).not.toContain('已执行')
    expect(wrapper.text()).toContain('候选点不存在')
    expect(wrapper.emitted('simulation-result')).toBeUndefined()
  })

  it('加载中和手动模拟忙碌时回车不会重复调用', async () => {
    let resolve!: (result: PlanningResponse) => void
    vi.mocked(planReport).mockImplementation(() => new Promise(done => { resolve = done }))
    const wrapper = setup()
    await ask(wrapper)
    await wrapper.get('input').setValue('再查一次')
    await wrapper.get('input').trigger('keydown.enter')
    expect(planReport).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('正在查询证据或计算模拟结果')
    resolve(response())
    await flushPromises()
    await wrapper.setProps({ disabled: true })
    await wrapper.get('input').setValue('不能重复')
    await wrapper.get('input').trigger('keydown.enter')
    expect(planReport).toHaveBeenCalledTimes(1)
  })

  it('切换报告取消旧请求并丢弃旧模拟，追问上下文清空', async () => {
    let resolve!: (result: PlanningResponse) => void
    vi.mocked(planReport).mockImplementationOnce(() => new Promise(done => { resolve = done }))
    const wrapper = setup()
    await ask(wrapper)
    const oldSignal = vi.mocked(planReport).mock.lastCall?.[2]
    await wrapper.setProps({ report: { ...report, report_id: 'report-two' } })
    resolve(response({ simulations: [simulation] }))
    await flushPromises()
    expect(oldSignal?.aborted).toBe(true)
    expect(wrapper.emitted('simulation-result')).toBeUndefined()
    expect(wrapper.find('.ai-result').exists()).toBe(false)
    await ask(wrapper)
    expect(vi.mocked(planReport).mock.lastCall?.[0]).toBe('report-two')
    expect(vi.mocked(planReport).mock.lastCall?.[1].previous_turn_id).toBeUndefined()
  })

  it('历史问答可恢复工具记录和服务端上下文', async () => {
    vi.mocked(fetchReportInterpretations).mockResolvedValue({ items: [response({ mode: 'tool_rules' })] })
    const wrapper = setup()
    await flushPromises()
    expect(wrapper.text()).toContain('规则工具 · 模型未启用')
    expect(wrapper.text()).toContain('匹配2处设施')
    await ask(wrapper, '继续')
    expect(vi.mocked(planReport).mock.lastCall?.[1].previous_turn_id).toBe('turn-one')
  })

  it('历史请求晚于新问答完成时不能覆盖新结果', async () => {
    let resolve!: (result: { items: PlanningResponse[] }) => void
    vi.mocked(fetchReportInterpretations).mockImplementation(() => new Promise(done => { resolve = done }))
    const wrapper = setup()
    await ask(wrapper)
    resolve({ items: [response({ id: 'old', summary: '旧记录' })] })
    await flushPromises()
    expect(wrapper.text()).not.toContain('旧记录')
    expect(wrapper.text()).toContain('先核验服务盲区')
  })
})
