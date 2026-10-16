// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AiCompletionWorkbench from './AiCompletionWorkbench.vue'
import * as api from '../services/completionApi'
import type { Report } from '../types/report'
import type { Governance, PlanningOptimization } from '../types/completion'

vi.mock('../services/completionApi', () => ({ decideObservation: vi.fn(), decideSemanticReview: vi.fn(), fetchGovernance: vi.fn(), fetchNativeIsochroneCapability: vi.fn(), probeNativeIsochrone: vi.fn(), fetchPlanningCandidates: vi.fn(), fetchPlanningDemand: vi.fn(), registerPlanningDemand: vi.fn(), generateAudienceReport: vi.fn(), optimizePlanning: vi.fn(), recomputeCatalog: vi.fn(), recomputeCombination: vi.fn(), registerPlanningCandidates: vi.fn(), runActiveSampling: vi.fn(), runSemanticReview: vi.fn(), submitObservation: vi.fn() }))
const report = { report_id: 'source-report', center: { lng: 113.5, lat: 23.1 }, parameters: { categories: ['pharmacy'] } } as Report
const review = { review_id: 'review-1', report_id: 'source-report', mode: 'rules', record_count: 1, candidate_count: 0, candidates_truncated: false, records: [{ id: 'poi-1', name: '待审核设施' }], category_proposals: [{ record_id: 'poi-1', original_category: 'market', proposed_category: 'pharmacy', candidate_categories: ['pharmacy'], confidence: null }], entity_proposals: [], diagnostics: [], apply_policy: 'human_review_only', affects_original_report: false, disclosure: '等待人工复核' } as const
const governance = { catalog_version: 3, catalog: { version: 3, records: [{ id: 'poi-1', name: '待审核设施' }], source_records: [{ id: 'raw-1' }] }, reviews: [review], observations: [], audit: [] } as unknown as Governance
const emptyLayers = { observed: { type: 'FeatureCollection' as const, features: [] }, estimated: { type: 'FeatureCollection' as const, features: [] }, unresolved: { type: 'FeatureCollection' as const, features: [] }, time_field: { type: 'FeatureCollection' as const, features: [] } }
const button = (wrapper: ReturnType<typeof mount>, text: string) => wrapper.findAll('button').find(item => item.text() === text)!
const field = (wrapper: ReturnType<typeof mount>, text: string) => wrapper.findAll('label').find(item => item.text().startsWith(text))!.find('input,textarea,select')

beforeEach(() => { vi.clearAllMocks(); vi.mocked(api.fetchGovernance).mockResolvedValue(governance); vi.mocked(api.fetchPlanningCandidates).mockResolvedValue({ items: [] }) })
describe('审核、测量与组合规划闭环', () => {
  it('对话审核更新后刷新目录，较早请求不会回写旧版本', async () => {
    const wrapper = mount(AiCompletionWorkbench, { props: { report, governanceRevision: 0 } })
    await button(wrapper, '刷新目录').trigger('click'); await flushPromises()
    vi.mocked(api.fetchGovernance).mockResolvedValue({ ...governance, catalog_version: 4 })
    await wrapper.setProps({ governanceRevision: 1 }); await flushPromises()
    expect(wrapper.text()).toContain('目录版本 4')
    vi.mocked(api.fetchGovernance).mockResolvedValue(governance)
    await wrapper.setProps({ governanceRevision: 2 }); await flushPromises()
    expect(wrapper.text()).toContain('目录版本 4')
    expect(wrapper.text()).not.toContain('目录版本 3')
  })
  it('观察原图使用当前报告下的受控入口，服务端文本URL不能注入任意资源', async () => {
    vi.mocked(api.fetchGovernance).mockResolvedValue({ ...governance, observations: [{ id: 'observation/id', text: '图片观察', status: 'pending_human_review', image_url: 'javascript:alert(1)', has_image: true }] })
    const wrapper = mount(AiCompletionWorkbench, { props: { report } })
    await button(wrapper, '现场观察').trigger('click'); await button(wrapper, '刷新待复核观察').trigger('click'); await flushPromises()
    expect(wrapper.get('img').attributes('src')).toMatch(/\/api\/reports\/source-report\/observations\/observation%2Fid\/image$/)
    expect(wrapper.get('a').attributes('href')).toBe(wrapper.get('img').attributes('src'))
    expect(wrapper.get('a').attributes('rel')).toBe('noopener noreferrer')
    expect(wrapper.html()).not.toContain('javascript:')
  })
  it('审核需要身份和依据，并携带目录版本；重算打开新报告而不修改来源', async () => {
    const wrapper = mount(AiCompletionWorkbench, { props: { report } })
    await button(wrapper, '刷新目录').trigger('click'); await flushPromises()
    expect(button(wrapper, '接纳').attributes('disabled')).toBeDefined()
    await wrapper.findAll('input')[0]!.setValue('规划复核员')
    await wrapper.get('textarea').setValue('现场核验编号2026-01')
    await button(wrapper, '接纳').trigger('click'); await flushPromises()
    expect(api.decideSemanticReview).toHaveBeenCalledWith('source-report', expect.objectContaining({ expected_version: 3, reviewer: '规划复核员', reason: '现场核验编号2026-01', kind: 'category', record_id: 'poi-1', decision: 'accept' }))
    const nextReport = { ...report, report_id: 'new-report' }
    vi.mocked(api.recomputeCatalog).mockResolvedValue({ report_id: 'new-report', report: nextReport, catalog_version: 4 })
    await button(wrapper, '按当前审核目录正式重算').trigger('click'); await flushPromises()
    expect(wrapper.emitted('new-report')).toEqual([[nextReport]])
    expect(report.report_id).toBe('source-report')
  })
  it('真实补测携带显式预算并展示未入正式评分的空间结果', async () => {
    vi.mocked(api.runActiveSampling).mockResolvedValue({ report_id: 'source-report', status: 'experimental', external_route_pairs_used: 8, layers: emptyLayers, disclosure: '预测不进入评分', enabled_for_official_analysis: false })
    const wrapper = mount(AiCompletionWorkbench, { props: { report } })
    await button(wrapper, '主动补测').trigger('click')
    const numbers = wrapper.findAll('input[type="number"]')
    await numbers[0]!.setValue(12); await numbers[1]!.setValue(5)
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.runActiveSampling).toHaveBeenCalledWith('source-report', 12, 5, 'active')
    expect(wrapper.emitted('sampling')).toEqual([[emptyLayers]])
    expect(wrapper.text()).toContain('实际外部路线 8 对')
    await numbers[0]!.setValue(201)
    expect(button(wrapper, '执行主动补测').attributes('disabled')).toBeDefined()
  })
  it('已处理提案显示复核状态并阻止重复审核', async () => {
    vi.mocked(api.fetchGovernance).mockResolvedValue({ ...governance, reviews: [{ ...governance.reviews[0]!, category_proposals: [{ ...governance.reviews[0]!.category_proposals[0]!, status: 'accepted', reviewer: '复核员', reason: '已核验台账' }] }] })
    const wrapper = mount(AiCompletionWorkbench, { props: { report } })
    await button(wrapper, '刷新目录').trigger('click'); await flushPromises()
    await field(wrapper, '复核人').setValue('另一位复核员'); await field(wrapper, '复核依据').setValue('再次核验')
    expect(wrapper.text()).toContain('已接纳 复核员 已核验台账')
    expect(button(wrapper, '接纳').attributes('disabled')).toBeDefined()
    expect(button(wrapper, '驳回').attributes('disabled')).toBeDefined()
    expect(api.decideSemanticReview).not.toHaveBeenCalled()
  })
  it('现场文本观察与通路阻断复核形成版本化证据，缺少不同网格不能接纳', async () => {
    const pending = { id: 'observation-1', text: '通道施工关闭', status: 'pending_human_review', kind: 'barrier' }
    vi.mocked(api.fetchGovernance).mockResolvedValue({ ...governance, observations: [pending] })
    const wrapper = mount(AiCompletionWorkbench, { props: { report } })
    await button(wrapper, '现场观察').trigger('click'); await field(wrapper, '现场观察').setValue('通道施工关闭')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.submitObservation).toHaveBeenCalledWith('source-report', { text: '通道施工关闭', lng: 113.5, lat: 23.1 })
    await field(wrapper, '复核人').setValue('社区核验员'); await field(wrapper, '复核依据').setValue('现场照片20261014')
    expect(button(wrapper, '核验接纳').attributes('disabled')).toBeDefined()
    await field(wrapper, '通路第一网格').setValue('pharmacy-r1c1'); await field(wrapper, '通路第二网格').setValue('pharmacy-r1c1')
    expect(button(wrapper, '核验接纳').attributes('disabled')).toBeDefined()
    await field(wrapper, '通路第二网格').setValue('pharmacy-r1c2'); await button(wrapper, '核验接纳').trigger('click'); await flushPromises()
    expect(api.decideObservation).toHaveBeenCalledWith('source-report', 'observation-1', expect.objectContaining({ decision: 'accept', expected_version: 3, reviewer: '社区核验员', kind: 'barrier', first_grid_id: 'pharmacy-r1c1', second_grid_id: 'pharmacy-r1c2' }))
  })
  it('图片观察拒绝非图片格式和超大文件，不把未识别附件送给模型', async () => {
    const wrapper = mount(AiCompletionWorkbench, { props: { report } })
    await button(wrapper, '现场观察').trigger('click')
    const upload = wrapper.get('input[type="file"]')
    Object.defineProperty(upload.element, 'files', { configurable: true, value: [new File(['hello'], 'proof.txt', { type: 'text/plain' })] })
    await upload.trigger('change'); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('4MB以内')
    const largeFile = new File(['image'], 'proof.png', { type: 'image/png' }); Object.defineProperty(largeFile, 'size', { value: 4 * 1024 * 1024 + 1 })
    Object.defineProperty(upload.element, 'files', { configurable: true, value: [largeFile] }); await upload.trigger('change'); await flushPromises()
    expect(button(wrapper, '提交待核验观察').attributes('disabled')).toBeDefined()
    expect(api.submitObservation).not.toHaveBeenCalled()
  })
  it('原生等时圈按能力门控，启用后显式实测并展示返回空间证据', async () => {
    vi.mocked(api.fetchNativeIsochroneCapability).mockResolvedValue({ configured: false, available: false, account_verified: false, pricing_verified: false })
    const wrapper = mount(AiCompletionWorkbench, { props: { report } })
    await button(wrapper, '主动补测').trigger('click'); await button(wrapper, '读取能力状态').trigger('click'); await flushPromises()
    expect(button(wrapper, '实测当前中心能力').attributes('disabled')).toBeDefined(); expect(api.probeNativeIsochrone).not.toHaveBeenCalled()
    vi.mocked(api.fetchNativeIsochroneCapability).mockResolvedValue({ configured: true, available: false, account_verified: false, pricing_verified: false })
    vi.mocked(api.probeNativeIsochrone).mockResolvedValue({ configured: true, available: true, account_verified: true, pricing_verified: false, status: 'available', request_sent: true, geometry: { type: 'Polygon', coordinates: [[[113.5, 23.1], [113.6, 23.1], [113.6, 23.2], [113.5, 23.1]]] }, source: 'real_api' })
    await button(wrapper, '读取能力状态').trigger('click'); await flushPromises(); await button(wrapper, '实测当前中心能力').trigger('click'); await flushPromises()
    expect(api.probeNativeIsochrone).toHaveBeenCalledWith(113.5, 23.1, 15, 'foot_fastest')
    expect(wrapper.emitted('sampling')?.[0]?.[0]).toEqual(expect.objectContaining({ native_boundary: expect.objectContaining({ features: [expect.objectContaining({ properties: expect.objectContaining({ affects_official_score: false, source: 'real_api' }) })] }) }))
    expect(wrapper.text()).toContain('本次成功返回原生等时圈')
  })
  it('可信候选选择、预算、类别上下限与必须/禁止约束进入同一求解请求', async () => {
    const candidates = [{ id: 'parcel-A', category: 'pharmacy', lng: 113.5, lat: 23.1, source: '地块台账1', verified: true, cost: 50000, capacity: 100 }]
    vi.mocked(api.fetchPlanningCandidates).mockResolvedValue({ items: candidates })
    const combination = { report_id: 'source-report', before: { overall_score: 30 }, after: { overall_score: 50 }, delta: { overall_score: 20 }, hypothetical_facilities: candidates }
    vi.mocked(api.optimizePlanning).mockResolvedValue({ status: 'OPTIMAL', selected_candidate_ids: ['parcel-A'], selected_candidates: candidates, combination, pareto_solutions: [{ candidate_ids: ['parcel-A'], covered_grid_count: 2, total_cost: 50000 }] } satisfies PlanningOptimization)
    const wrapper = mount(AiCompletionWorkbench, { props: { report } })
    await button(wrapper, '组合规划').trigger('click'); await button(wrapper, '刷新候选').trigger('click'); await flushPromises()
    const constraintForm = wrapper.findAll('form')[1]!
    const fields = constraintForm.findAll('input[type="number"]')
    await fields[0]!.setValue(3); await fields[1]!.setValue(100000); await fields[2]!.setValue(100); await fields[3]!.setValue(1000); await fields[4]!.setValue(1); await fields[5]!.setValue(2)
    const required = wrapper.findAll('label').find(item => item.text() === '必须选择')!.get('input')
    await required.setValue(true)
    await constraintForm.trigger('submit'); await flushPromises()
    expect(api.optimizePlanning).toHaveBeenCalledWith('source-report', { candidate_ids: ['parcel-A'], max_facilities: 3, budget: 100000, minimum_capacity: 100, minimum_population: 1000, category_limits: { pharmacy: { min: 1, max: 2 } }, required_ids: ['parcel-A'], forbidden_ids: [], allowed_land_only: false, method: 'auto' })
    expect(wrapper.emitted('combination')).toEqual([[combination]])
    expect(wrapper.text()).toContain('综合评分：30 → 50')
    expect(wrapper.text()).toContain('帕累托方案比较')
  })
  it('角色报告分层显示证据，模型文本不会成为HTML', async () => {
    vi.mocked(api.generateAudienceReport).mockResolvedValue({ observations: ['<script>alert(1)</script>'], possible_causes: ['可能存在入口差异'], measures: ['核验入口'], verification_conditions: ['待现场核验'], norms: [{ title: '生活圈规范', text: '条文摘录', source: '可信规范' }], citations: [], disclosure: '依据来源报告' })
    const wrapper = mount(AiCompletionWorkbench, { props: { report } })
    await button(wrapper, '角色报告').trigger('click'); await wrapper.get('select').setValue('planner'); await wrapper.get('textarea').setValue('关注买菜便利性'); await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.generateAudienceReport).toHaveBeenCalledWith('source-report', 'planner', '关注买菜便利性')
    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.text()).toContain('<script>alert(1)</script>')
    for (const title of ['已核验观察', '可能原因', '建议措施', '待核验条件']) expect(wrapper.text()).toContain(title)
  })
  it('人口收益只接收有来源和复核标记的网格台账，缺少来源不会进入求解资料', async () => {
    const wrapper = mount(AiCompletionWorkbench, { props: { report } })
    await button(wrapper, '组合规划').trigger('click')
    await field(wrapper, '人口台账').setValue('[{"grid_id":"r1c1","population":300,"verified":true}]')
    await button(wrapper, '保存已核验人口台账').trigger('click'); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('可核验来源'); expect(api.registerPlanningDemand).not.toHaveBeenCalled()
    const items = [{ grid_id: 'r1c1', population: 300, source: '人口台账20261014', verified: true as const }]
    vi.mocked(api.registerPlanningDemand).mockResolvedValue({ items })
    await field(wrapper, '人口台账').setValue(JSON.stringify(items)); await button(wrapper, '保存已核验人口台账').trigger('click'); await flushPromises()
    expect(api.registerPlanningDemand).toHaveBeenCalledWith('source-report', items)
    expect(wrapper.text()).toContain('已核验1个人口网格')
  })
})
