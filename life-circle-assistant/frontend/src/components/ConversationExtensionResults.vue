<template>
  <details v-if="governanceState" class="extension-result">
    <summary>设施目录审核 · 版本 {{ governanceState.catalog_version }}</summary>
    <p v-if="governanceState.catalog">设施 {{ governanceState.catalog.records.length }} 条</p>
    <p v-if="governanceState.requires_recompute">审核已保存，正式评分待使用当前目录重新体检。</p>
    <p v-if="governanceState.audit_event">{{ governanceState.audit_event.reviewer }} · {{ governanceState.audit_event.decision }} · {{ governanceState.audit_event.reason }}</p>
    <ul v-if="governanceState.observations?.length"><li v-for="item in governanceState.observations" :key="item.id">{{ item.text }} · {{ item.status }}</li></ul>
  </details>
  <details v-if="recomputation" class="extension-result"><summary>审核目录正式重算 · 版本 {{ recomputation.catalog_version }}</summary><p>已打开新报告 {{ recomputation.report_id }}。来源报告保留用于追溯。</p></details>
  <details v-if="observation" class="extension-result"><summary>居民观察 · 待核验</summary><p>{{ observation.text }}</p><p>{{ observation.disclosure || '人工复核前不改变设施事实与正式评分。' }}</p></details>
  <details v-if="roleReport" class="extension-result"><summary>有依据的角色报告</summary><section v-for="group in reportGroups" :key="group.key"><strong>{{ group.label }}</strong><p v-for="(item,index) in roleReport[group.key]" :key="index">{{ evidenceText(item) }}</p></section><p v-for="(item,index) in roleReport.norms" :key="index">{{ item.title }} {{ item.text }} {{ item.source }}</p><p>{{ roleReport.disclosure }}</p></details>
  <details v-if="semanticReview" class="extension-result">
    <summary>设施语义审核 · {{ semanticReview.record_count }}条设施 / {{ semanticReview.candidate_count }}对关系候选</summary>
    <p>{{ semanticReview.mode === 'llm_review' ? '模型审核建议' : semanticReview.mode === 'rules_degraded' ? '模型审核未通过，使用规则候选' : '规则候选' }} · 待人工审核</p>
    <p>{{ semanticReview.disclosure }}</p>
    <p v-if="semanticReview.candidates_truncated">关系候选已达到审核上限，部分候选未处理。</p>
    <ul aria-label="分类审核建议"><li v-for="proposal in semanticReview.category_proposals" :key="proposal.record_id">{{ facilityName(proposal.record_id) }}：{{ categoryLabel(proposal.original_category) }} → {{ proposal.proposed_category ? categoryLabel(proposal.proposed_category) : '待人工判定' }}<small v-if="proposal.candidate_categories.length">规则候选：{{ proposal.candidate_categories.map(categoryLabel).join('、') }}</small></li></ul>
    <ul v-if="semanticReview.entity_proposals.length" aria-label="设施关系审核建议"><li v-for="proposal in semanticReview.entity_proposals" :key="`${proposal.left_id}:${proposal.right_id}`">{{ facilityName(proposal.left_id) }} / {{ facilityName(proposal.right_id) }}：{{ relationLabel(proposal.relation) }} · {{ proposal.distance_m }}米</li></ul>
  </details>
  <details v-if="samplingExperiment" class="extension-result">
    <summary>采样对照实验 · {{ samplingStatus(samplingExperiment) }}</summary>
    <p v-if="samplingExperiment.evaluation">训练{{ samplingExperiment.training_ids?.length ?? 0 }}点 · 留出{{ samplingExperiment.validation_ids?.length ?? 0 }}点 · 有效评估{{ samplingExperiment.evaluation.evaluated_count }}点</p>
    <p v-if="samplingExperiment.evaluation">平均误差{{ metric(samplingExperiment.evaluation.mae_minutes) }}分钟；IDW基线{{ metric(samplingExperiment.baseline?.mae_minutes) }}分钟。误判可达{{ samplingExperiment.evaluation.false_reachable_count }}点，误判不可达{{ samplingExperiment.evaluation.false_unreachable_count }}点；未解决{{ samplingExperiment.evaluation.unresolved_count }}点。</p>
    <p>外部路线调用：{{ samplingExperiment.external_route_pairs_used }} · 未用于正式可达性或评分</p>
    <p>{{ samplingExperiment.disclosure }}</p>
    <button v-if="samplingExperiment.layers" type="button" @click="emit('sampling', samplingExperiment.layers)">在地图查看补测时间场</button>
  </details>
  <details v-if="optimization" class="extension-result">
    <summary>组合选址 · {{ optimization.selected_count }}个候选 / 确认可达{{ optimization.covered_grid_count }}个网格中心</summary>
    <p>{{ optimization.status === 'OPTIMAL' ? '输入有限候选与已确认覆盖集合内最优' : '贪心可行方案，未证明最优' }} · {{ optimization.candidate_count }}个输入候选</p>
    <p>路线未知{{ optimization.unknown_route_pairs }}对{{ optimization.coverage_evidence_status === 'partial_lower_bound' ? '，覆盖数量仅为已确认下界' : '' }}；建设成本{{ optimization.total_cost === null ? '未知' : optimization.total_cost }}</p>
    <ul aria-label="已选候选覆盖证据"><li v-for="id in optimization.selected_candidate_ids" :key="id">{{ id }}<small v-if="candidateEvidence(id)">{{ categoryLabel(candidateEvidence(id)!.category) }} · 确认{{ candidateEvidence(id)!.covered_grid_ids.length }}个网格中心 · 未知{{ candidateEvidence(id)!.unknown_grid_ids.length }}个 · 来源{{ candidateEvidence(id)!.sources.join('、') || '暂无' }}</small></li></ul>
    <p>{{ optimization.disclosure }}</p>
    <p>假设方案，未修改原报告或评分。</p>
    <template v-if="optimization.combination"><p>组合综合评分：{{ optimization.combination.before.overall_score ?? '未知' }} → {{ optimization.combination.after.overall_score ?? '未知' }}</p><button type="button" @click="emit('combination', optimization.combination)">在地图查看整体组合情景</button></template>
    <table v-if="optimization.pareto_solutions?.length"><thead><tr><th>候选组合</th><th>确认覆盖</th><th>成本</th></tr></thead><tbody><tr v-for="(item,index) in optimization.pareto_solutions" :key="index"><td>{{ item.candidate_ids.join('、') }}</td><td>{{ item.covered_grid_count ?? '未知' }}</td><td>{{ item.total_cost ?? '未知' }}</td></tr></tbody></table>
  </details>
</template>

<script setup lang="ts">
import { FACILITY_LABELS } from '../constants/facilities'
import type { CoverageOptimization, SamplingExperiment, SemanticReview } from '../types/aiExtensions'
import type { AudienceReport, Combination, ResidentObservation, SamplingLayers } from '../types/completion'
import type { ConversationTurn } from '../types/workspace'
const props = defineProps<{ semanticReview?: SemanticReview; samplingExperiment?: SamplingExperiment; optimization?: CoverageOptimization; governanceState?: ConversationTurn['governance_state']; recomputation?: ConversationTurn['recomputation']; observation?: ResidentObservation; roleReport?: AudienceReport }>()
const emit = defineEmits<{ sampling: [layers: SamplingLayers]; combination: [value: Combination] }>()
const samplingStatusLabel: Record<SamplingExperiment['status'], string> = {
  experimental: '测量完成，独立验证不足',
  insufficient_recorded_samples: '可复用路线样本不足',
  insufficient_evaluation_budget: '实验预算或规模不满足',
}
const samplingStatus = (experiment: SamplingExperiment) => experiment.status === 'experimental' && (experiment.evaluation?.evaluated_count ?? 0) > 0 ? '已完成留出验证' : samplingStatusLabel[experiment.status]
const categoryLabel = (category: string | null) => category ? FACILITY_LABELS[category] || category : '未分类'
const facilityName = (id: string) => props.semanticReview?.records.find(item => item.id === id)?.name || id
const candidateEvidence = (id: string) => props.optimization?.candidate_evidence?.find(item => item.candidate_id === id)
const metric = (value?: number | null) => value === undefined || value === null ? '未知' : value.toFixed(2)
const reportGroups = [{ key: 'observations', label: '已核验观察' }, { key: 'possible_causes', label: '可能原因' }, { key: 'measures', label: '建议措施' }, { key: 'verification_conditions', label: '待核验条件' }] as const
function evidenceText(value: unknown): string { if (typeof value === 'string') return value; if (value && typeof value === 'object') { const item = value as Record<string, unknown>; return String(item.text ?? item.statement ?? item.description ?? item.detail ?? JSON.stringify(value)) } return String(value ?? '') }
const relationLabel = (relation: string) => ({ same_entity: '疑似同一实体，待审核', different_entity: '不同实体建议', department: '科室关系建议', entrance: '入口关系建议', uncertain: '关系未确定' }[relation] || relation)
</script>

<style scoped>
.extension-result { margin-top: 7px; font-size: 10px; line-height: 1.65; overflow-wrap: anywhere; }
.extension-result summary { cursor: pointer; }.extension-result p { margin: 5px 0; }.extension-result ul { padding-left: 16px; }.extension-result small { display: block; opacity: .75; }
.extension-result button { padding: 5px 7px; border: 1px solid #cbdcd3; border-radius: 5px; color: inherit; background: transparent; font: inherit; }.extension-result table { width: 100%; text-align: left; border-collapse: collapse; }.extension-result th,.extension-result td { padding: 4px; border-bottom: 1px solid #cbdcd3; }
</style>
