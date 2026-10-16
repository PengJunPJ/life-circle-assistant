// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ConversationExtensionResults from './ConversationExtensionResults.vue'
import type { SamplingExperiment } from '../types/aiExtensions'

describe('对话增量结果的证据边界', () => {
  it('对话审核与目录重算展示版本和来源边界，复核依据不会变成HTML', () => {
    const wrapper = mount(ConversationExtensionResults, { props: {
      governanceState: { catalog_version: 4, requires_recompute: true, audit_event: { reviewer: '复核员', decision: 'accept', reason: '<script>1</script>' } },
      recomputation: { report_id: 'new-report', source_report_id: 'source-report', catalog_version: 4, affects_original_report: false },
      observation: { id: 'observation', text: '现场通路封闭', status: 'pending_human_review' },
    } })
    expect(wrapper.text()).toContain('版本 4'); expect(wrapper.text()).toContain('正式评分待使用当前目录重新体检')
    expect(wrapper.text()).toContain('已打开新报告 new-report'); expect(wrapper.text()).toContain('来源报告保留')
    expect(wrapper.text()).toContain('人工复核前不改变设施事实')
    expect(wrapper.text()).toContain('<script>1</script>'); expect(wrapper.find('script').exists()).toBe(false)
  })
  it('角色报告在对话中分层展示可核验事实、假设与措施', () => {
    const wrapper = mount(ConversationExtensionResults, { props: { roleReport: { observations: ['可核验事实'], possible_causes: ['<img src=x>'], measures: ['核验措施'], verification_conditions: ['需核验入口'], norms: [{ title: '生活圈条文', text: '条文', source: '规范台账' }], citations: [], disclosure: '仅按来源证据生成' } } })
    for (const label of ['已核验观察', '可能原因', '建议措施', '待核验条件', '规范台账']) expect(wrapper.text()).toContain(label)
    expect(wrapper.find('img').exists()).toBe(false)
  })
  it('语义候选始终保留人工审核与关系区分，模型失败明确降级', () => {
    const wrapper = mount(ConversationExtensionResults, { props: { semanticReview: {
      report_id: 'report', mode: 'rules_degraded', record_count: 2, candidate_count: 1, candidates_truncated: true,
      records: [{ id: 'first', name: '<img src=x onerror=alert(1)>' }, { id: 'second', name: '医院入口' }],
      category_proposals: [{ record_id: 'first', original_category: 'market', candidate_categories: ['medical'], proposed_category: null, confidence: null }],
      entity_proposals: [{ left_id: 'first', right_id: 'second', relation: 'entrance', distance_m: 12, confidence: null }],
      diagnostics: ['model_review_invalid_rule_candidates_used'], apply_policy: 'human_review_only', affects_original_report: false, disclosure: '仅供审核，未合并设施。',
    } } })
    expect(wrapper.text()).toContain('模型审核未通过，使用规则候选')
    expect(wrapper.text()).toContain('待人工判定')
    expect(wrapper.text()).toContain('入口关系建议')
    expect(wrapper.text()).toContain('部分候选未处理')
    expect(wrapper.find('img').exists()).toBe(false)
  })

  it('缺少评估误差显示未知，零误差保持为零，并披露正式分析未使用预测', () => {
    const wrapper = mount(ConversationExtensionResults, { props: { samplingExperiment: {
      report_id: 'report', status: 'experimental', training_ids: ['first'], validation_ids: ['second'],
      evaluation: { evaluated_count: 1, unknown_measurements: 0, false_reachable_count: 0, false_unreachable_count: 0, unresolved_count: 1, mae_minutes: null },
      baseline: { method: 'inverse_distance_weighting', mae_minutes: 0, false_reachable_count: 0, false_unreachable_count: 0 },
      enabled_for_official_analysis: false, external_route_pairs_used: 0, disclosure: '不确定性未经现场校准。',
    } } })
    expect(wrapper.find('summary').text()).toContain('已完成留出验证')
    expect(wrapper.text()).toContain('平均误差未知分钟；IDW基线0.00分钟')
    expect(wrapper.text()).toContain('外部路线调用：0')
    expect(wrapper.text()).toContain('未用于正式可达性或评分')
  })
  it('已完成测量但没有可信评估标签时，不宣称完成独立验证', () => {
    const wrapper = mount(ConversationExtensionResults, { props: { samplingExperiment: { report_id: 'report', status: 'experimental', evaluation: { evaluated_count: 0, unknown_measurements: 4, false_reachable_count: 0, false_unreachable_count: 0, unresolved_count: 5, mae_minutes: null }, enabled_for_official_analysis: false, external_route_pairs_used: 4, disclosure: '失败与估算未用作真实标签。' } } })
    expect(wrapper.find('summary').text()).toContain('独立验证不足')
    expect(wrapper.text()).not.toContain('已完成留出验证')
  })

  it.each([
    { status: 'insufficient_recorded_samples', label: '可复用路线样本不足' },
    { status: 'insufficient_evaluation_budget', label: '实验预算或规模不满足' },
  ] satisfies { status: SamplingExperiment['status']; label: string }[])('实验未完成时准确区分$status，不展示验证成果', ({ status, label }) => {
    const wrapper = mount(ConversationExtensionResults, { props: { samplingExperiment: {
      report_id: 'report', status, sample_count: 12,
      enabled_for_official_analysis: false, external_route_pairs_used: 0, disclosure: '未执行留出验证。',
    } } })
    expect(wrapper.find('summary').text()).toBe(`采样对照实验 · ${label}`)
    expect(wrapper.text()).not.toContain('已完成留出验证')
    expect(wrapper.text()).not.toContain('平均误差')
    expect(wrapper.text()).toContain('外部路线调用：0')
    expect(wrapper.text()).toContain('未用于正式可达性或评分')
  })

  it('有限候选内最优与路线未知的覆盖下界并存，不宣称全局选址收益', () => {
    const wrapper = mount(ConversationExtensionResults, { props: { optimization: {
      report_id: 'report', status: 'OPTIMAL', selected_candidate_ids: ['candidate'], selected_count: 1, candidate_count: 2,
      covered_grid_count: 3, unknown_route_pairs: 2, coverage_evidence_status: 'partial_lower_bound', total_cost: null,
      candidate_evidence: [{ candidate_id: 'candidate', category: 'market', covered_grid_ids: ['a', 'b', 'c'], unknown_grid_ids: ['d'], sources: ['local_snapshot'] }],
      affects_original_report: false, disclosure: '未计入人口、容量或土地合规。',
    } } })
    expect(wrapper.text()).toContain('输入有限候选与已确认覆盖集合内最优')
    expect(wrapper.text()).toContain('覆盖数量仅为已确认下界')
    expect(wrapper.text()).toContain('确认3个网格中心')
    expect(wrapper.text()).toContain('建设成本未知')
    expect(wrapper.text()).toContain('未修改原报告或评分')
  })
})
