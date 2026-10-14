<template>
  <section class="completion-workbench" aria-label="AI核验与规划工作台">
    <nav class="completion-nav" aria-label="AI工作台功能"><button v-for="item in sections" :key="item.id" type="button" :aria-pressed="section === item.id" @click="section = item.id">{{ item.label }}</button></nav>
    <p v-if="error" role="alert" class="completion-error">{{ error }}</p>
    <p v-if="notice" role="status" class="completion-note">{{ notice }}</p>
    <p v-if="busy" role="status" class="completion-note">正在核验并保存结果…</p>
    <template v-if="section === 'review'">
      <div class="completion-toolbar"><button type="button" :disabled="busy" @click="loadGovernance">刷新目录</button><button type="button" :disabled="busy" @click="reviewSemantics">生成语义审核建议</button></div>
      <p class="completion-note">审核只更新版本化目录。正式重算会生成一份新报告。</p>
      <p v-if="governance">目录版本 {{ governance.catalog_version }} · {{ governance.catalog.records.length }} 条设施 · {{ governance.catalog.source_records?.length ?? 0 }} 条原始记录</p>
      <div class="completion-fields"><label>复核人<input v-model="reviewer" maxlength="100" /></label><label>复核依据<textarea v-model="reason" maxlength="1000" rows="2" placeholder="记录核验来源、现场证据或驳回原因" /></label></div>
      <article v-for="review in governance?.reviews || []" :key="review.review_id" class="completion-result">
        <strong>审核批次 {{ review.review_id }}</strong><p>{{ review.disclosure }}</p>
        <div v-for="proposal in review.category_proposals" :key="proposal.record_id" class="review-row">
          <strong>{{ recordName(review, proposal.record_id) }}</strong><span>{{ label(proposal.original_category) }} → {{ label(proposal.proposed_category) }}</span><small>{{ observationStatus(proposal.status || 'pending_human_review') }} {{ proposal.reviewer }} {{ proposal.reason }}</small>
          <select v-model="corrections[proposal.record_id]" :disabled="!proposalPending(proposal.status)" :aria-label="`修正${recordName(review, proposal.record_id)}类别`"><option value="">选择修正类别</option><option v-for="category in ALL_CATEGORIES" :key="category" :value="category">{{ label(category) }}</option></select>
          <div class="completion-toolbar"><button type="button" :disabled="!canReview || !proposalPending(proposal.status) || !proposal.proposed_category" @click="decideCategory(review.review_id, proposal.record_id, 'accept')">接纳</button><button type="button" :disabled="!canReview || !proposalPending(proposal.status)" @click="decideCategory(review.review_id, proposal.record_id, 'reject')">驳回</button><button type="button" :disabled="!canReview || !proposalPending(proposal.status) || !corrections[proposal.record_id]" @click="decideCategory(review.review_id, proposal.record_id, 'correct')">修正后接纳</button></div>
        </div>
        <div v-for="proposal in review.entity_proposals" :key="`${proposal.left_id}:${proposal.right_id}`" class="review-row">
          <strong>{{ recordName(review, proposal.left_id) }} / {{ recordName(review, proposal.right_id) }}</strong><span>{{ relationLabel(proposal.relation) }} · {{ Math.round(proposal.distance_m) }}米</span><small>{{ observationStatus(proposal.status || 'pending_human_review') }} {{ proposal.reviewer }} {{ proposal.reason }}</small>
          <select v-model="entityCorrections[`${proposal.left_id}:${proposal.right_id}`]" :disabled="!proposalPending(proposal.status)" aria-label="修正实体关系"><option value="">选择实体关系</option><option value="same_entity">同一实体</option><option value="different_entity">不同实体</option><option value="department">科室关系</option><option value="entrance">入口关系</option></select>
          <div class="completion-toolbar"><button type="button" :disabled="!canReview || !proposalPending(proposal.status) || proposal.relation === 'uncertain'" @click="decideEntity(review.review_id, proposal.left_id, proposal.right_id, 'accept')">接纳关系</button><button type="button" :disabled="!canReview || !proposalPending(proposal.status)" @click="decideEntity(review.review_id, proposal.left_id, proposal.right_id, 'reject')">驳回</button><button type="button" :disabled="!canReview || !proposalPending(proposal.status) || !entityCorrections[`${proposal.left_id}:${proposal.right_id}`]" @click="decideEntity(review.review_id, proposal.left_id, proposal.right_id, 'correct')">修正关系</button></div>
        </div>
      </article>
      <button class="completion-primary" type="button" :disabled="busy || !governance" @click="recompute">按当前审核目录正式重算</button>
      <details v-if="governance?.audit.length"><summary>审核记录（{{ governance.audit.length }}）</summary><p v-for="(item,index) in governance.audit" :key="item.id || index">{{ item.reviewer }} · {{ item.decision }} · {{ item.reason }} · {{ item.created_at }}</p></details>
    </template>
    <template v-if="section === 'observations'">
      <p class="completion-note">留言和图片识别形成待核验观察，复核前不改变设施事实。</p>
      <form class="completion-fields" @submit.prevent="saveObservation"><label>现场观察<textarea v-model="observationText" rows="3" maxlength="3000" placeholder="例如：这家药店已关闭，入口改到了南侧" /></label><label>现场图片<input type="file" accept="image/png,image/jpeg,image/webp" @change="readObservationImage" /></label><small v-if="imageName">{{ imageName }}</small><div class="completion-inline"><label>经度（BD-09）<input v-model.number="observationLng" type="number" step="any" /></label><label>纬度（BD-09）<input v-model.number="observationLat" type="number" step="any" /></label></div><button type="submit" :disabled="busy || (!observationText.trim() && !imageBase64)">提交待核验观察</button></form>
      <div class="completion-fields"><label>复核人<input v-model="reviewer" /></label><label>复核依据<textarea v-model="reason" rows="2" maxlength="1000" /></label></div>
      <div class="completion-toolbar"><button type="button" :disabled="busy" @click="loadGovernance">刷新待复核观察</button></div>
      <article v-for="item in governance?.observations || []" :key="item.id" class="completion-result">
        <strong>{{ item.text || '图片观察' }}</strong><p>{{ observationStatus(item.status) }}</p><p v-if="item.ocr_text">识别文本：{{ item.ocr_text }}</p><small>{{ item.disclosure }}</small>
        <a v-if="item.image_url" :href="observationImageUrl(item)" target="_blank" rel="noopener noreferrer"><img class="observation-image" :src="observationImageUrl(item)" alt="居民提交的现场观察原图，待复核" loading="lazy" /></a>
        <template v-if="isPending(item.status)">
          <label>核验事件类型<select v-model="observationKinds[item.id]"><option value="closure">设施关闭</option><option value="entrance_change">入口变更</option><option value="barrier">步行通路受阻</option><option value="facility_missing">补录设施</option><option value="other">其他观察</option></select></label>
          <label>关联设施<select v-model="observationFacilityIds[item.id]"><option value="">选择现有设施</option><option v-for="facility in governance?.catalog.records || []" :key="facility.id" :value="facility.id">{{ facility.name || facility.id }}</option></select></label>
          <label>核验设施名称<input v-model="observationCorrections[item.id]" placeholder="新增或修正设施时填写" /></label><label>核验类别<select v-model="observationCategories[item.id]"><option value="">选择类别</option><option v-for="category in ALL_CATEGORIES" :key="category" :value="category">{{ label(category) }}</option></select></label>
          <div class="completion-inline"><label>核验经度<input v-model.number="observationLongitudes[item.id]" type="number" step="any" /></label><label>核验纬度<input v-model.number="observationLatitudes[item.id]" type="number" step="any" /></label></div>
          <div v-if="observationKinds[item.id] === 'barrier'" class="completion-inline"><label>通路第一网格<input v-model="observationFirstGrids[item.id]" placeholder="网格ID" /></label><label>通路第二网格<input v-model="observationSecondGrids[item.id]" placeholder="网格ID" /></label></div>
          <small v-if="!observationCanApply(item)">接纳前请补齐该事件的关联设施、位置或通路网格及复核依据。</small>
          <div class="completion-toolbar"><button type="button" :disabled="!observationCanApply(item)" @click="reviewObservation(item, 'accept')">核验接纳</button><button type="button" :disabled="!canReview" @click="reviewObservation(item, 'reject')">驳回观察</button><button type="button" :disabled="!observationCanApply(item)" @click="reviewObservation(item, 'correct')">修正后接纳</button></div>
        </template>
      </article>
    </template>
    <template v-if="section === 'sampling'">
      <p class="completion-note">真实补测用于学习时间场。观测、估计与未决区域单独展示，预测不参与正式评分。</p>
      <form class="completion-fields" @submit.prevent="sample"><div class="completion-inline"><label>路线对预算<input v-model.number="routeBudget" type="number" min="2" max="200" required /></label><label>采样网格边长<input v-model.number="gridSize" type="number" min="3" max="15" required /></label></div><label>采样策略<select v-model="samplingStrategy"><option value="active">高不确定性主动补测</option><option value="uniform">均匀采样对照</option><option value="radial">径向采样对照</option><option value="rule_densification">规则加密对照</option><option value="idw">IDW插值对照</option></select></label><small>最多 {{ routeBudget }} 条路线对；真实模式会使用地图配额。</small><button type="submit" :disabled="busy || !samplingParametersValid">执行主动补测</button></form>
      <article v-if="sampling" class="completion-result"><strong>{{ sampling.status }}</strong><p>实际外部路线 {{ sampling.external_route_pairs_used }} 对 · 观测 {{ sampling.layers.observed.features.length }} · 估计 {{ sampling.layers.estimated.features.length }} · 未决 {{ sampling.layers.unresolved.features.length }}</p><p>{{ sampling.disclosure }}</p><p v-if="sampling.evaluation">独立评估样本 {{ sampling.evaluation.evaluated_count ?? '未知' }} · MAE {{ sampling.evaluation.mae_minutes ?? '待独立验证' }}</p><button type="button" @click="emit('sampling', sampling.layers)">在地图查看时间场</button><details><summary>时间场证据</summary><p v-for="(item,index) in sampling.layers.time_field.features" :key="index">{{ item.properties.point_id }} · {{ item.properties.source }} · {{ item.properties.mean_minutes ?? '未知' }}分钟 · 标准差 {{ item.properties.std_minutes ?? '未知' }}</p></details></article>
      <p class="completion-note">青绿网格外沿仅表示中心点已观测可达，不认证整个网格。</p>
      <details class="completion-result"><summary>地图原生等时圈能力核验</summary><button type="button" :disabled="busy" @click="loadNativeCapability">读取能力状态</button><template v-if="nativeCapability"><p>配置{{ nativeCapability.configured ? '已启用' : '未启用' }} · 账户{{ nativeCapability.account_verified ? '已实测' : '待实测' }} · 计费规则{{ nativeCapability.pricing_verified ? '已核验' : '待核验' }}</p><p>{{ nativeCapability.message || nativeCapability.disclosure }} {{ nativeCapability.error_code }}</p><label>步行策略<select v-model="nativeStrategy"><option value="foot_fastest">步行最快</option><option value="foot_shortest">步行最短</option></select></label><small>按当前中心与{{ report.parameters.minutes || 15 }}分钟实测；已启用时会发送一次地图请求。</small><button type="button" :disabled="busy || !nativeCapability.configured" @click="probeNative">实测当前中心能力</button><p v-if="nativeCapability.status">{{ nativeCapability.status === 'available' ? '本次成功返回原生等时圈' : nativeCapability.status === 'disabled' ? '能力未启用，未发送请求' : '本次能力不可用' }} · {{ nativeCapability.request_sent ? '已发送请求' : '未发送请求' }}</p></template></details>
    </template>
    <template v-if="section === 'planning'">
      <p class="completion-note">候选须提供可核验来源。预算、容量和用地缺少可信数据时，求解会要求补齐。</p>
      <form class="completion-fields" @submit.prevent="saveCandidate"><div class="completion-inline"><label>候选编号<input v-model="candidate.id" required maxlength="100" /></label><label>设施类别<select v-model="candidate.category"><option v-for="category in ALL_CATEGORIES" :key="category" :value="category">{{ label(category) }}</option></select></label></div><div class="completion-inline"><label>经度（BD-09）<input v-model.number="candidate.lng" type="number" step="any" required /></label><label>纬度（BD-09）<input v-model.number="candidate.lat" type="number" step="any" required /></label></div><div class="completion-inline"><label>成本（元）<input v-model.number="candidate.cost" type="number" min="0" /></label><label>容量<input v-model.number="candidate.capacity" type="number" min="0" /></label><label>服务人口<input v-model.number="candidate.population" type="number" min="0" /></label></div><label>数据来源<input v-model="candidate.source" required maxlength="500" placeholder="地块台账、现场核验编号或授权数据来源" /></label><label class="completion-checkbox"><input v-model="candidate.land_allowed" type="checkbox" />已核验允许建设</label><label class="completion-checkbox"><input v-model="candidate.verified" type="checkbox" required />已核验上述输入与来源</label><button type="submit" :disabled="busy || !candidate.verified">登记可信候选</button></form>
      <div class="completion-toolbar"><button type="button" :disabled="busy" @click="loadCandidates">刷新候选</button></div>
      <details><summary>可信网格人口台账</summary><p class="completion-note">人口收益按确认覆盖网格的并集去重，候选的服务人口不相加。请提供网格ID、人口、来源并标记已核验。</p><label>人口台账（JSON数组）<textarea v-model="demandJson" rows="4" maxlength="50000" placeholder='[{"grid_id":"r1c1","population":100,"source":"社区人口台账","verified":true}]' /></label><div class="completion-toolbar"><button type="button" :disabled="busy" @click="loadDemand">读取人口台账</button><button type="button" :disabled="busy || !demandJson.trim()" @click="saveDemand">保存已核验人口台账</button></div><small v-if="planningDemand.length">已核验{{ planningDemand.length }}个人口网格</small></details>
      <div v-for="item in planningCandidates" :key="item.id" class="review-row"><label class="completion-checkbox"><input v-model="selectedCandidateIds" type="checkbox" :value="item.id" />{{ item.id }} · {{ label(item.category) }}</label><small>{{ item.source }} · 成本 {{ item.cost ?? '未知' }} · 容量 {{ item.capacity ?? '未知' }}</small><div class="completion-inline"><label class="completion-checkbox"><input v-model="requiredIds" type="checkbox" :value="item.id" />必须选择</label><label class="completion-checkbox"><input v-model="forbiddenIds" type="checkbox" :value="item.id" />禁止选择</label></div></div>
      <form class="completion-fields" @submit.prevent="optimize"><div class="completion-inline"><label>总数量上限<input v-model.number="maxFacilities" type="number" min="1" max="20" required /></label><label>预算（元）<input v-model.number="budget" type="number" min="0" /></label><label>最低总容量<input v-model.number="minimumCapacity" type="number" min="0" /></label><label>最低受益人口<input v-model.number="minimumPopulation" type="number" min="0" /></label></div><label class="completion-checkbox"><input v-model="allowedLandOnly" type="checkbox" />仅使用已核验可建设地块</label><details><summary>各类别数量硬约束</summary><div v-for="category in planningCategories" :key="category" class="completion-inline"><span>{{ label(category) }}</span><label>至少<input v-model.number="categoryMinimums[category]" type="number" min="0" /></label><label>至多<input v-model.number="categoryMaximums[category]" type="number" min="0" /></label></div></details><button class="completion-primary" type="submit" :disabled="busy || !selectedCandidateIds.length">求解并整体复算组合</button></form>
      <article v-if="optimization" class="completion-result"><strong>{{ optimization.status }} · {{ optimization.selected_candidate_ids.join('、') || '未选择设施' }}</strong><p>核验覆盖 {{ optimization.covered_grid_count ?? '未知' }} 个网格 · 成本 {{ optimization.total_cost ?? '未知' }}</p><p>{{ optimization.disclosure }}</p><div v-if="optimization.combination"><p>综合评分：{{ snapshotScore(optimization.combination.before) }} → {{ snapshotScore(optimization.combination.after) }}（变化 {{ snapshotScore(optimization.combination.delta) }}）</p><p>重点盲区：{{ optimization.combination.before.critical_zone_count ?? '未知' }} → {{ optimization.combination.after.critical_zone_count ?? '未知' }}</p><button type="button" @click="emit('combination', optimization.combination)">查看组合情景地图</button></div><details v-if="optimization.pareto_solutions.length" open><summary>帕累托方案比较</summary><table><thead><tr><th>候选</th><th>覆盖</th><th>成本</th><th>情景</th></tr></thead><tbody><tr v-for="(item,index) in optimization.pareto_solutions" :key="index"><td>{{ item.candidate_ids.join('、') }}</td><td>{{ item.covered_grid_count ?? '未知' }}</td><td>{{ item.total_cost ?? '未知' }}</td><td><button type="button" :disabled="busy" @click="showCombination(item.candidate_ids)">复算查看</button></td></tr></tbody></table></details></article>
    </template>
    <template v-if="section === 'report'">
      <form class="completion-fields" @submit.prevent="audienceReport"><label>报告受众<select v-model="audience"><option value="resident">居民</option><option value="community">社区工作人员</option><option value="planner">规划师</option></select></label><label>关注问题<textarea v-model="audienceQuery" maxlength="1000" rows="2" placeholder="例如：如何优先改善老年人的买菜便利性？" /></label><button type="submit" :disabled="busy">生成有依据的角色报告</button></form>
      <article v-if="groundedReport" class="completion-result"><section v-for="group in reportGroups" :key="group.key"><strong>{{ group.label }}</strong><p v-for="(item,index) in groundedReport[group.key]" :key="index">{{ evidenceText(item) }}</p><small v-if="!groundedReport[group.key].length">暂无可核验内容</small></section><details><summary>规范依据与引用（{{ groundedReport.norms.length }}）</summary><p v-for="(item,index) in groundedReport.norms" :key="item.id || index">{{ item.title }} {{ item.text }} {{ item.source }}</p><p v-for="(item,index) in groundedReport.citations" :key="index">{{ evidenceText(item) }}</p></details><p>{{ groundedReport.disclosure }}</p></article>
    </template>
    <p v-if="section === 'planning' && optimization" class="completion-note">去重确认受益人口：{{ optimization.confirmed_population ?? '未知，需可信网格人口台账' }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ALL_CATEGORIES, API_BASE_URL, FACILITY_LABELS } from '../constants/facilities'
import { decideObservation, decideSemanticReview, fetchGovernance, fetchNativeIsochroneCapability, fetchPlanningCandidates, fetchPlanningDemand, generateAudienceReport, optimizePlanning, probeNativeIsochrone, recomputeCatalog, recomputeCombination, registerPlanningCandidates, registerPlanningDemand, runActiveSampling, runSemanticReview, submitObservation } from '../services/completionApi'
import type { ActiveSampling, Audience, AudienceReport, Combination, CombinationSnapshot, Governance, NativeIsochroneCapability, PlanningDemand, PlanningOptimization, ResidentObservation, SamplingLayers, SamplingStrategy, TrustedCandidate } from '../types/completion'
import type { Report } from '../types/report'
import type { SemanticReview } from '../types/aiExtensions'

const props = defineProps<{ report: Report; governanceRevision?: number }>()
const emit = defineEmits<{ 'new-report': [report: Report]; sampling: [layers: SamplingLayers]; combination: [value: Combination] }>()
const sections = [{ id: 'review', label: '语义复核' }, { id: 'observations', label: '现场观察' }, { id: 'sampling', label: '主动补测' }, { id: 'planning', label: '组合规划' }, { id: 'report', label: '角色报告' }] as const
const section = ref<typeof sections[number]['id']>('review')
const governance = ref<Governance | null>(null)
const busy = ref(false), error = ref(''), notice = ref(''), reviewer = ref(''), reason = ref('')
const corrections = ref<Record<string, string>>({}), entityCorrections = ref<Record<string, string>>({})
const observationCorrections = ref<Record<string, string>>({}), observationCategories = ref<Record<string, string>>({})
const observationKinds = ref<Record<string, string>>({}), observationFacilityIds = ref<Record<string, string>>({}), observationFirstGrids = ref<Record<string, string>>({}), observationSecondGrids = ref<Record<string, string>>({})
const observationLongitudes = ref<Record<string, number | ''>>({}), observationLatitudes = ref<Record<string, number | ''>>({})
const observationText = ref(''), imageBase64 = ref(''), imageMime = ref(''), imageName = ref('')
const observationLng = ref<number | ''>(props.report.center.lng), observationLat = ref<number | ''>(props.report.center.lat)
const sampling = ref<ActiveSampling | null>(null), routeBudget = ref(30), gridSize = ref(7)
const samplingStrategy = ref<SamplingStrategy>('active'), nativeCapability = ref<NativeIsochroneCapability | null>(null), nativeStrategy = ref<'foot_fastest' | 'foot_shortest'>('foot_fastest')
const candidate = ref({ id: '', category: props.report.parameters.categories[0] || 'pharmacy', lng: props.report.center.lng, lat: props.report.center.lat, source: '', verified: false, land_allowed: false, cost: '' as number | '', capacity: '' as number | '', population: '' as number | '' })
const planningCandidates = ref<TrustedCandidate[]>([]), selectedCandidateIds = ref<string[]>([]), requiredIds = ref<string[]>([]), forbiddenIds = ref<string[]>([])
const maxFacilities = ref(2), budget = ref<number | ''>(''), minimumCapacity = ref<number | ''>(''), minimumPopulation = ref<number | ''>(''), allowedLandOnly = ref(false)
const demandJson = ref(''), planningDemand = ref<PlanningDemand[]>([])
const categoryMinimums = ref<Record<string, number>>({}), categoryMaximums = ref<Record<string, number>>({})
const optimization = ref<PlanningOptimization | null>(null), audience = ref<Audience>('resident'), audienceQuery = ref(''), groundedReport = ref<AudienceReport | null>(null)
const planningCategories = computed(() => [...new Set(planningCandidates.value.filter(item => selectedCandidateIds.value.includes(item.id)).map(item => item.category))])
const canReview = computed(() => !busy.value && Boolean(governance.value) && Boolean(reviewer.value.trim()) && Boolean(reason.value.trim()))
const samplingParametersValid = computed(() => Number.isInteger(routeBudget.value) && routeBudget.value >= 2 && routeBudget.value <= 200 && Number.isInteger(gridSize.value) && gridSize.value >= 3 && gridSize.value <= 15)
const reportGroups = [{ key: 'observations', label: '已核验观察' }, { key: 'possible_causes', label: '可能原因' }, { key: 'measures', label: '建议措施' }, { key: 'verification_conditions', label: '待核验条件' }] as const
const label = (category: string | null) => category ? FACILITY_LABELS[category] || category : '未确定'
const recordName = (review: SemanticReview, id: string) => review.records.find(item => item.id === id)?.name || id
const relationLabel = (relation: string) => ({ same_entity: '同一实体', different_entity: '不同实体', department: '科室关系', entrance: '入口关系', uncertain: '关系未确定' })[relation] || relation
const observationStatus = (status: string) => ({ pending: '待核验', pending_review: '待核验', pending_human_review: '待核验', accepted: '已接纳', rejected: '已驳回', corrected: '修正后接纳' })[status] || status
const isPending = (status: string) => status.startsWith('pending')
const proposalPending = (status?: string) => !status || isPending(status)
function observationCanApply(item: ResidentObservation): boolean {
  if (!canReview.value) return false
  const kind = observationKinds.value[item.id]
  const locationKnown = typeof observationLongitudes.value[item.id] === 'number' && typeof observationLatitudes.value[item.id] === 'number'
  if (kind === 'closure') return Boolean(observationFacilityIds.value[item.id])
  if (kind === 'entrance_change') return Boolean(observationFacilityIds.value[item.id]) && locationKnown
  if (kind === 'facility_missing') return Boolean(observationCorrections.value[item.id]?.trim()) && Boolean(observationCategories.value[item.id]) && locationKnown
  if (kind === 'barrier') return Boolean(observationFirstGrids.value[item.id]?.trim()) && Boolean(observationSecondGrids.value[item.id]?.trim()) && observationFirstGrids.value[item.id] !== observationSecondGrids.value[item.id]
  return true
}
const snapshotScore = (value: CombinationSnapshot) => value.overall_score ?? value.score ?? '未知'
const observationImageUrl = (item: ResidentObservation) => `${API_BASE_URL}/api/reports/${encodeURIComponent(props.report.report_id)}/observations/${encodeURIComponent(item.id)}/image`
function evidenceText(value: unknown): string { if (typeof value === 'string') return value; if (value && typeof value === 'object') { const item = value as Record<string, unknown>; return String(item.text ?? item.statement ?? item.description ?? item.detail ?? JSON.stringify(value)) } return String(value ?? '') }
async function execute(operation: (id: string) => Promise<void>) {
  if (busy.value) return
  const id = props.report.report_id
  busy.value = true; error.value = ''; notice.value = ''
  try { await operation(id) } catch (cause) { if (props.report.report_id === id) error.value = cause instanceof Error ? cause.message : '操作失败' } finally { busy.value = false }
}
async function updateGovernance(id: string) { const result = await fetchGovernance(id); if (props.report.report_id === id && (!governance.value || result.catalog_version >= governance.value.catalog_version)) { governance.value = result; for (const item of result.observations) { observationKinds.value[item.id] ??= item.kind || 'other'; observationFacilityIds.value[item.id] ??= item.facility_id || ''; observationLongitudes.value[item.id] ??= item.lng ?? item.location?.lng ?? ''; observationLatitudes.value[item.id] ??= item.lat ?? item.location?.lat ?? '' } } }
const loadGovernance = () => execute(updateGovernance)
const reviewSemantics = () => execute(async id => { await runSemanticReview(id); await updateGovernance(id) })
const decideCategory = (reviewId: string, recordId: string, decision: 'accept' | 'reject' | 'correct') => execute(async id => { await decideSemanticReview(id, { review_id: reviewId, kind: 'category', record_id: recordId, decision, ...(decision === 'correct' ? { category: corrections.value[recordId] } : {}), reviewer: reviewer.value.trim(), reason: reason.value.trim(), expected_version: governance.value!.catalog_version }); await updateGovernance(id) })
const decideEntity = (reviewId: string, left: string, right: string, decision: 'accept' | 'reject' | 'correct') => execute(async id => { await decideSemanticReview(id, { review_id: reviewId, kind: 'entity', left_id: left, right_id: right, decision, ...(decision === 'correct' ? { relation: entityCorrections.value[`${left}:${right}`] } : {}), reviewer: reviewer.value.trim(), reason: reason.value.trim(), expected_version: governance.value!.catalog_version }); await updateGovernance(id) })
const recompute = () => execute(async id => { const result = await recomputeCatalog(id); if (props.report.report_id === id) emit('new-report', result.report) })
async function readObservationImage(event: Event) {
  const reportId = props.report.report_id
  const file = (event.target as HTMLInputElement).files?.[0]
  imageBase64.value = ''; imageName.value = ''; error.value = ''
  if (!file) return
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 4 * 1024 * 1024) { error.value = '请选择4MB以内的PNG、JPEG或WebP图片'; return }
  const result = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = () => reject(new Error('图片读取失败')); reader.readAsDataURL(file) }).catch(cause => { error.value = cause.message; return '' })
  if (result && props.report.report_id === reportId) { imageBase64.value = result.split(',')[1]; imageMime.value = file.type; imageName.value = file.name }
}
const saveObservation = () => execute(async id => { await submitObservation(id, { text: observationText.value.trim(), ...(imageBase64.value ? { image_base64: imageBase64.value, mime_type: imageMime.value } : {}), ...(typeof observationLng.value === 'number' ? { lng: observationLng.value } : {}), ...(typeof observationLat.value === 'number' ? { lat: observationLat.value } : {}) }); if (props.report.report_id === id) { observationText.value = ''; imageBase64.value = ''; imageName.value = ''; notice.value = '观察已提交，等待复核。' } await updateGovernance(id) })
const reviewObservation = (item: ResidentObservation, decision: 'accept' | 'reject' | 'correct') => execute(async id => { const lng = observationLongitudes.value[item.id], lat = observationLatitudes.value[item.id]; await decideObservation(id, item.id, { decision, reviewer: reviewer.value.trim(), reason: reason.value.trim(), expected_version: governance.value!.catalog_version, kind: observationKinds.value[item.id], facility_id: observationFacilityIds.value[item.id] || undefined, first_grid_id: observationFirstGrids.value[item.id] || undefined, second_grid_id: observationSecondGrids.value[item.id] || undefined, category: observationCategories.value[item.id] || undefined, name: observationCorrections.value[item.id] || undefined, ...(typeof lng === 'number' ? { lng } : {}), ...(typeof lat === 'number' ? { lat } : {}) }); await updateGovernance(id) })
const sample = () => { if (samplingParametersValid.value) return execute(async id => { const result = await runActiveSampling(id, routeBudget.value, gridSize.value, samplingStrategy.value); if (props.report.report_id === id) { sampling.value = result; emit('sampling', result.layers) } }) }
const loadNativeCapability = () => execute(async id => { const result = await fetchNativeIsochroneCapability(); if (props.report.report_id === id) nativeCapability.value = result })
const probeNative = () => execute(async id => {
  if (!nativeCapability.value?.configured) return
  const result = await probeNativeIsochrone(props.report.center.lng, props.report.center.lat, props.report.parameters.minutes || 15, nativeStrategy.value)
  if (props.report.report_id !== id) return
  nativeCapability.value = result
  if (result.status === 'available' && result.geometry) {
    const empty = { type: 'FeatureCollection' as const, features: [] }
    const layers: SamplingLayers = { ...(sampling.value?.layers || { observed: empty, estimated: empty, unresolved: empty, time_field: empty }), native_boundary: { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: result.geometry, properties: { coordinate_system: 'BD-09', source: result.source, point_id: 'native', affects_official_score: false } }] } }
    emit('sampling', layers)
  }
})
async function updateCandidates(id: string) { const result = await fetchPlanningCandidates(id); if (props.report.report_id === id) { planningCandidates.value = result.items; if (!selectedCandidateIds.value.length) selectedCandidateIds.value = result.items.map(item => item.id) } }
const loadCandidates = () => execute(updateCandidates)
const loadDemand = () => execute(async id => { const result = await fetchPlanningDemand(id); if (props.report.report_id === id) { planningDemand.value = result.items; demandJson.value = JSON.stringify(result.items, null, 2) } })
const saveDemand = () => execute(async id => {
  let items: unknown
  try { items = JSON.parse(demandJson.value) } catch { throw new Error('人口台账必须是合法JSON数组') }
  if (!Array.isArray(items) || !items.length || items.some(item => !item || typeof item !== 'object' || typeof item.grid_id !== 'string' || !item.grid_id.trim() || typeof item.population !== 'number' || !Number.isFinite(item.population) || item.population < 0 || typeof item.source !== 'string' || !item.source.trim() || item.verified !== true)) throw new Error('每条人口台账须填写网格ID、非负人口、可核验来源及verified=true')
  const result = await registerPlanningDemand(id, items as PlanningDemand[])
  if (props.report.report_id === id) { planningDemand.value = result.items; notice.value = '已核验人口台账已保存。' }
})
const saveCandidate = () => execute(async id => { const value = candidate.value; const item: TrustedCandidate = { id: value.id.trim(), category: value.category, lng: value.lng, lat: value.lat, source: value.source.trim(), verified: value.verified, land_allowed: value.land_allowed, ...(typeof value.cost === 'number' ? { cost: value.cost } : {}), ...(typeof value.capacity === 'number' ? { capacity: value.capacity } : {}), ...(typeof value.population === 'number' ? { population: value.population } : {}) }; await registerPlanningCandidates(id, [item]); await updateCandidates(id); if (props.report.report_id === id) { selectedCandidateIds.value = [...new Set([...selectedCandidateIds.value, item.id])]; notice.value = '可信候选已登记。' } })
const optimize = () => execute(async id => { const limits = Object.fromEntries(planningCategories.value.filter(category => categoryMinimums.value[category] !== undefined || categoryMaximums.value[category] !== undefined).map(category => [category, { min: categoryMinimums.value[category] ?? 0, max: categoryMaximums.value[category] ?? maxFacilities.value }])); const result = await optimizePlanning(id, { candidate_ids: selectedCandidateIds.value, max_facilities: maxFacilities.value, category_limits: limits, required_ids: requiredIds.value, forbidden_ids: forbiddenIds.value, ...(typeof budget.value === 'number' ? { budget: budget.value } : {}), ...(typeof minimumCapacity.value === 'number' ? { minimum_capacity: minimumCapacity.value } : {}), ...(typeof minimumPopulation.value === 'number' ? { minimum_population: minimumPopulation.value } : {}), allowed_land_only: allowedLandOnly.value, method: 'auto' }); if (props.report.report_id === id) { optimization.value = result; if (result.combination) emit('combination', result.combination) } })
const showCombination = (ids: string[]) => execute(async id => { const result = await recomputeCombination(id, ids); if (props.report.report_id === id) emit('combination', result) })
const audienceReport = () => execute(async id => { const result = await generateAudienceReport(id, audience.value, audienceQuery.value); if (props.report.report_id === id) groundedReport.value = result })
watch(() => props.governanceRevision, () => { const id = props.report.report_id; void updateGovernance(id).catch(cause => { if (props.report.report_id === id) error.value = cause instanceof Error ? cause.message : '目录刷新失败' }) })
watch(() => props.report.report_id, () => { governance.value = null; sampling.value = null; nativeCapability.value = null; planningCandidates.value = []; selectedCandidateIds.value = []; requiredIds.value = []; forbiddenIds.value = []; optimization.value = null; groundedReport.value = null; error.value = ''; notice.value = ''; imageBase64.value = ''; imageName.value = ''; observationText.value = ''; observationLng.value = props.report.center.lng; observationLat.value = props.report.center.lat; demandJson.value = ''; planningDemand.value = []; minimumPopulation.value = ''; categoryMinimums.value = {}; categoryMaximums.value = {}; corrections.value = {}; entityCorrections.value = {} })
</script>

<style scoped>
.completion-workbench { font-size: 11px; line-height: 1.65; color: inherit; }
.completion-nav { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 12px; }
.completion-workbench button { padding: 6px 8px; color: inherit; border: 1px solid #cbdcd3; background: transparent; border-radius: 5px; font-size: 10px; }
.completion-nav button[aria-pressed="true"], .completion-workbench .completion-primary { color: #fff; background: #214c47; }
.completion-workbench button:disabled { opacity: .45; cursor: default; }
.completion-toolbar { display: flex; flex-wrap: wrap; gap: 5px; margin: 8px 0; }.completion-note { color: #6d8077; }.completion-error { color: #b45536; }
.completion-fields { display: grid; gap: 8px; margin: 12px 0; }.completion-workbench label { display: grid; gap: 3px; min-width: 0; }.completion-workbench input:not([type="checkbox"]), .completion-workbench textarea, .completion-workbench select { width: 100%; min-width: 0; padding: 6px; border: 1px solid #cbdcd3; border-radius: 4px; color: inherit; background: transparent; box-sizing: border-box; font: inherit; }.completion-workbench textarea { resize: vertical; }.completion-inline { display: flex; gap: 8px; align-items: end; }.completion-inline > * { flex: 1; min-width: 0; }.completion-workbench .completion-checkbox { display: flex; align-items: center; gap: 5px; }.completion-checkbox input { width: auto; }
.completion-result { padding: 10px 0; border-top: 1px solid #dce6e0; overflow-wrap: anywhere; }.review-row { display: grid; gap: 4px; padding: 9px 0; border-bottom: 1px solid #dce6e0; }.completion-result section { margin: 12px 0; }.completion-result p { white-space: pre-line; }.completion-workbench details { margin-top: 10px; }.completion-workbench summary { cursor: pointer; }.completion-workbench table { width: 100%; border-collapse: collapse; font-size: 10px; }.completion-workbench th, .completion-workbench td { text-align: left; padding: 5px 3px; border-bottom: 1px solid #dce6e0; }.completion-workbench small { color: #72877d; }
.observation-image { display: block; max-width: 100%; max-height: 180px; object-fit: contain; margin: 8px 0; border-radius: 5px; }
html[data-theme="dark"] .completion-workbench input, html[data-theme="dark"] .completion-workbench textarea, html[data-theme="dark"] .completion-workbench select { border-color: #41665e; background: #172c36; }html[data-theme="dark"] .completion-note, html[data-theme="dark"] .completion-workbench small { color: #9bbab1; }html[data-theme="dark"] .completion-error { color: #ffc192; }
@media(max-width:820px) { .completion-workbench input, .completion-workbench textarea, .completion-workbench select { font-size: 16px; }.completion-inline { flex-wrap: wrap; }.completion-inline > * { flex-basis: 42%; } }
</style>
