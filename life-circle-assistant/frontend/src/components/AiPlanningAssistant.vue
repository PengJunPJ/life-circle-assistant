<template>
  <section class="ai-assistant" aria-labelledby="ai-assistant-title">
    <div class="section-title"><span id="ai-assistant-title">可解释 AI 规划助手</span><small>{{ modeLabel }}</small></div>
    <p class="ai-boundary">查询设施、核验网格证据、计算新增设施效果；原始体检报告保持不变。</p>
    <div class="ai-actions">
      <button type="button" :disabled="busy" @click="run({ intent: 'summary' })">体检摘要</button>
      <button type="button" :disabled="busy" @click="ask('查询各类设施和重点服务盲区，建议优先关注什么？')">查询服务短板</button>
      <button type="button" :disabled="busy" @click="ask(simulationQuestion)">候选设施模拟</button>
      <button type="button" :disabled="busy" @click="ask(comparisonQuestion, true)">比较方案</button>
      <button type="button" :disabled="busy" @click="run({ intent: 'brief' })">汇报摘要</button>
    </div>
    <p v-if="gridId" class="ai-context">当前网格：{{ gridId }}</p>
    <p v-if="simulationLocation?.selectionMethod === 'map'" class="ai-context">模拟位置：已采用你在地图上的选点</p>
    <div class="ai-question"><input v-model="question" maxlength="1000" aria-label="向规划助手提问" placeholder="例如：比较补足菜市场服务的方案" @keydown.enter.prevent="ask(question)" /><button type="button" :disabled="busy || !question.trim()" @click="ask(question)">提问</button></div>
    <div class="comparison-goal"><label for="planning-comparison-goal">比较目标</label><select id="planning-comparison-goal" v-model="comparisonGoal" :disabled="busy"><option value="reduce_critical_zones">减少重点盲区</option><option value="increase_coverage">扩大分类覆盖</option><option value="improve_overall_score">提高综合指数</option></select></div>
    <button v-if="previousTurnId" type="button" class="ai-new-topic" :disabled="busy" @click="newTopic">开始新话题</button>
    <div v-if="loading" class="ai-state" role="status">正在查询证据或计算模拟结果，请稍候…</div>
    <div v-else-if="error" class="ai-state error" role="alert">{{ error }}</div>
    <div v-else-if="result" class="ai-result" :class="{ degraded: isDegraded }" aria-live="polite">
      <div class="ai-mode">
        <span>生成方式</span>
        <strong>{{ result.model }}</strong>
        <span v-if="isDegraded" class="ai-degraded-badge">已降级</span>
        <small>{{ intentLabel(result.intent) }} · {{ result.prompt_version }}</small>
      </div>
      <p v-if="planningResult" class="ai-context">你的问题：{{ planningResult.question }}</p>
      <p class="ai-summary">{{ result.summary }}</p>
      <PlanningToolResults v-if="planningResult?.tool_calls.length" :calls="planningResult.tool_calls" />
      <PlanningComparison v-if="planningResult?.comparisons?.length" :comparison="planningResult.comparisons.at(-1)!" @show-simulation="showComparisonOption" />
      <button v-if="planningResult?.simulations.length && !planningResult.comparisons?.length && !isComparisonAttempt" type="button" class="ai-show-simulation" :disabled="busy" @click="showSimulation">在地图查看本次模拟</button>
      <div v-if="result.recommendations.length" class="ai-recommendations"><div v-for="item in result.recommendations" :key="item.title" class="ai-recommendation"><div><strong>{{ item.title }}</strong><span :class="`ai-priority ${item.priority}`">{{ priorityLabel(item.priority) }}</span></div><p>{{ item.text }}</p></div></div>
      <details class="ai-evidence"><summary>查看证据引用（{{ result.evidence_refs.length }}）</summary><ul><li v-for="ref in result.evidence_refs" :key="`${ref.type}-${ref.id}`"><strong>{{ ref.label }}</strong><span>{{ ref.detail }}</span><small>{{ ref.type }} · {{ ref.id }}</small></li></ul></details>
      <div class="ai-notices">
        <p class="ai-quality"><strong>数据质量：</strong>{{ result.data_quality_notice }}</p>
        <p class="ai-boundary-inline"><strong>边界说明：</strong>{{ result.boundary_notice }}</p>
      </div>
      <small class="ai-generated">生成于 {{ formatDate(result.generated_at) }}</small>
    </div>
    <div v-else class="ai-empty">例如：“查一下菜市场盲区，再模拟新增一个菜市场”。也可以选择地图网格后提问，并继续追问上一轮结果。</div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { fetchReportInterpretations, interpretReport, planReport } from '../services/analysisApi'
import { FACILITY_LABELS } from '../constants/facilities'
import type { AiInterpretation, AiInterpretationIntent, Report } from '../types/report'
import type { PlanningResponse } from '../types/planning'
import type { PlanningComparison as PlanningComparisonData } from '../types/planning'
import type { SimulationLocation, SimulationResult } from '../types/simulation'
import PlanningToolResults from './PlanningToolResults.vue'
import PlanningComparison from './PlanningComparison.vue'
const props = defineProps<{ report: Report; simulationLocation?: SimulationLocation | null; simulationCategory?: string; gridId?: string | null; disabled?: boolean }>()
const emit = defineEmits<{ 'simulation-result': [result: SimulationResult]; busy: [value: boolean] }>()
const result = ref<AiInterpretation | null>(null)
const loading = ref(false)
const error = ref('')
const question = ref('')
const previousTurnId = ref<string | undefined>()
const comparisonGoal = ref<PlanningComparisonData['goal']>('reduce_critical_zones')
const busy = computed(() => loading.value || props.disabled)
const planningResult = computed(() => result.value && 'tool_calls' in result.value ? result.value as PlanningResponse : null)
const isComparisonAttempt = computed(() => planningResult.value?.tool_calls.some(call => call.name === 'compare_planning_options') || false)
const isDegraded = computed(() => result.value?.mode.endsWith('_degraded'))
const modeLabel = computed(() => ({ llm_tools: '大模型 · 工具调用', tool_rules: '规则工具 · 模型未启用', tool_rules_degraded: '规则工具 · 已降级', llm_structured: '大模型增强' } as Record<string, string>)[result.value?.mode || ''] || result.value?.model || '规划问答')
const simulationQuestion = computed(() => `模拟新增一个${FACILITY_LABELS[props.simulationCategory || props.report.parameters.categories[0] || 'market']}，${props.simulationLocation?.selectionMethod === 'map' ? '使用我已选择的地图点' : '使用报告中的优先候选点'}，计算改善效果。`)
const comparisonQuestion = computed(() => `比较当前报告中可行的独立新增设施方案，优先${({ reduce_critical_zones: '减少重点盲区', increase_coverage: '扩大分类覆盖面积', improve_overall_score: '提高综合指数' } as Record<PlanningComparisonData['goal'], string>)[comparisonGoal.value]}。`)
let version = 0
let controller: AbortController | undefined
watch(() => props.report.report_id, async () => {
  const current = ++version
  controller?.abort()
  result.value = null; error.value = ''; question.value = ''; previousTurnId.value = undefined; loading.value = false
  emit('busy', false)
  try {
    const items = (await fetchReportInterpretations(props.report.report_id)).items
    if (current !== version) return
    result.value = items[0] || null
    previousTurnId.value = items.find(item => item.prompt_version === 'tool-planner-v1')?.id
  } catch { /* 历史解读不存在时保持空状态 */ }
}, { immediate: true })
async function run(params: { intent: AiInterpretationIntent; grid_id?: string; category?: string; simulation_id?: string; question?: string }) {
  if (busy.value) return
  const current = ++version
  loading.value = true; error.value = ''; emit('busy', true)
  try {
    const response = await interpretReport(props.report.report_id, params)
    if (current === version) result.value = response
  } catch (err) { if (current === version) error.value = err instanceof Error ? err.message : 'AI 解读生成失败' }
  finally { if (current === version) { loading.value = false; emit('busy', false) } }
}
async function ask(value: string, compare = false) {
  if (!value.trim() || busy.value) return
  const current = ++version
  const reportId = props.report.report_id
  controller = new AbortController()
  loading.value = true; error.value = ''; emit('busy', true)
  try {
    const response = await planReport(reportId, {
      message: value.trim(), previous_turn_id: previousTurnId.value, grid_id: props.gridId || undefined,
      selected_location: props.simulationLocation?.selectionMethod === 'map' ? { lng: props.simulationLocation.lng, lat: props.simulationLocation.lat } : undefined,
      comparison_goal: compare ? comparisonGoal.value : undefined,
    }, controller.signal)
    if (current !== version) return
    result.value = response; previousTurnId.value = response.id; question.value = ''
    if (!response.comparisons?.length && !response.tool_calls.some(call => call.name === 'compare_planning_options')) {
      const simulation = response.simulations.at(-1)
      if (simulation?.report_id === reportId) emit('simulation-result', simulation)
    }
  } catch (err) { if (current === version) error.value = err instanceof Error ? err.message : '规划工具执行失败' }
  finally { if (current === version) { loading.value = false; emit('busy', false) } }
}
function newTopic() { previousTurnId.value = undefined; result.value = null; question.value = ''; error.value = '' }
function showSimulation() {
  const simulation = planningResult.value?.simulations.at(-1)
  if (simulation?.report_id === props.report.report_id) emit('simulation-result', simulation)
}
function showComparisonOption(optionId: string) {
  const simulation = planningResult.value?.simulations.find(item => item.id === optionId)
  if (simulation?.report_id === props.report.report_id) emit('simulation-result', simulation)
}
onBeforeUnmount(() => { version++; controller?.abort(); emit('busy', false) })
function priorityLabel(value: string) { return ({ high: '优先', medium: '建议关注', low: '持续观察' } as Record<string, string>)[value] || value }
function intentLabel(value: AiInterpretationIntent) {
  return ({
    summary: '体检摘要',
    area_explanation: '服务区域解释',
    ask: '规划问答',
    priority: '类别优先级',
    simulation: '候选设施模拟',
    brief: '汇报摘要',
  } as Record<AiInterpretationIntent, string>)[value] || value
}
function formatDate(value: string) { return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value)) }
defineExpose({ run })
</script>

<style scoped>
.ai-context { color: #70857c; font-size: 10px; line-height: 1.5; overflow-wrap: anywhere; }
.comparison-goal { display: flex; align-items: center; gap: 7px; margin-top: 7px; color: #70857c; font-size: 9px; }
.comparison-goal select { min-width: 0; padding: 4px 6px; border: 1px solid #cedbd5; border-radius: 4px; background: #fff; color: #36564f; font-size: 9px; }
.ai-new-topic, .ai-show-simulation { margin-top: 8px; padding: 6px 8px; border: 1px solid #c9ddd3; border-radius: 4px; background: #f1f8f4; color: #397568; font-size: 10px; }
.ai-new-topic:disabled, .ai-show-simulation:disabled { opacity: .55; }
html[data-theme="dark"] .ai-context { color: #9db8b8; }
html[data-theme="dark"] .ai-new-topic, html[data-theme="dark"] .ai-show-simulation { border-color: rgba(126,214,199,.24); background: rgba(46,230,197,.08); color: #7ff0da; }
.ai-assistant { margin-top: 17px; padding-top: 16px; border-top: 1px solid #e2e9e4; }.ai-boundary { margin: 8px 0; color: #7f908b; font-size: 9px; line-height: 1.45; }.ai-actions { display: flex; flex-wrap: wrap; gap: 5px; }.ai-actions button, .ai-question button { padding: 6px 8px; border: 1px solid #c9ddd3; border-radius: 4px; background: #f1f8f4; color: #397568; font-size: 9px; }.ai-actions button:hover, .ai-question button:hover { background: #e2f1ea; }.ai-actions button:disabled, .ai-question button:disabled { opacity: .55; cursor: wait; }.ai-question { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 5px; margin-top: 7px; }.ai-question input { min-width: 0; height: 29px; padding: 0 7px; border: 1px solid #cedbd5; border-radius: 4px; color: #294b4c; font-size: 9px; }.ai-state, .ai-empty { margin-top: 9px; padding: 9px; border-radius: 4px; background: #f0f5f2; color: #72837e; font-size: 9px; line-height: 1.5; }.ai-state.error { background: #f7e8e3; color: #a1503d; }.ai-result { margin-top: 10px; padding: 10px; border: 1px solid #d6e4dc; border-left: 3px solid #4a9a82; border-radius: 4px; background: #fbfdfb; }.ai-result.degraded { border-left-color: #d4a574; background: #fffcf8; }.ai-mode { display: flex; align-items: baseline; gap: 7px; color: #72837e; font-size: 8px; flex-wrap: wrap; }.ai-mode strong { color: #347563; font-size: 10px; }.ai-mode small { margin-left: auto; color: #9aa5a5; }.ai-degraded-badge { padding: 2px 6px; border-radius: 8px; background: #f8edd7; color: #9a702d; font-size: 8px; font-weight: 600; }.ai-summary { margin: 9px 0; color: #36564f; font-size: 11px; line-height: 1.55; }.ai-recommendation { padding: 8px 0; border-top: 1px solid #e6eee9; }.ai-recommendation > div { display: flex; align-items: center; justify-content: space-between; gap: 5px; }.ai-recommendation strong { color: #3c5b54; font-size: 10px; }.ai-recommendation p { margin: 4px 0 0; color: #788984; font-size: 9px; line-height: 1.5; }.ai-priority { padding: 2px 5px; border-radius: 8px; background: #e9f2ed; color: #40806d; font-size: 8px; }.ai-priority.high { background: #f6e0da; color: #a34e3b; }.ai-priority.medium { background: #f8edd7; color: #9a702d; }.ai-evidence { margin-top: 8px; color: #47766c; font-size: 9px; }.ai-evidence summary { cursor: pointer; font-weight: 700; }.ai-evidence ul { display: grid; gap: 5px; margin: 7px 0 0; padding-left: 15px; color: #6c7e78; }.ai-evidence li { line-height: 1.4; }.ai-evidence li strong, .ai-evidence li span, .ai-evidence li small { display: block; }.ai-evidence li strong { color: #41685f; }.ai-evidence li small { color: #9aa8a3; }.ai-notices { margin-top: 10px; padding-top: 8px; border-top: 1px dashed #d6e4dc; }.ai-quality { margin: 0 0 6px; color: #92723d; font-size: 8px; line-height: 1.45; }.ai-quality strong { color: #7a5f2e; }.ai-boundary-inline { margin: 0; color: #7f908b; font-size: 8px; line-height: 1.45; }.ai-boundary-inline strong { color: #5f706b; }.ai-generated { display: block; margin-top: 6px; color: #a0ada8; font-size: 8px; }
html[data-theme="dark"] .ai-assistant { border-top-color: rgba(126,214,199,.1); }
html[data-theme="dark"] .ai-boundary, html[data-theme="dark"] .ai-boundary-inline { color: #6f8b90; }
html[data-theme="dark"] .ai-boundary-inline strong { color: #9db8b8; }
html[data-theme="dark"] .ai-actions button, html[data-theme="dark"] .ai-question button { border-color: rgba(126,214,199,.24); background: rgba(46,230,197,.08); color: #7ff0da; }
html[data-theme="dark"] .ai-actions button:hover, html[data-theme="dark"] .ai-question button:hover { background: rgba(46,230,197,.16); }
html[data-theme="dark"] .ai-question input { border-color: rgba(126,214,199,.2); background: rgba(9,18,27,.7); color: #e9f6f2; }
html[data-theme="dark"] .comparison-goal { color: #9db8b8; }
html[data-theme="dark"] .comparison-goal select { border-color: rgba(126,214,199,.2); background: #10202e; color: #e9f6f2; }
html[data-theme="dark"] .ai-state, html[data-theme="dark"] .ai-empty { background: rgba(9,18,27,.6); color: #9db8b8; }
html[data-theme="dark"] .ai-state.error { background: rgba(255,107,87,.12); color: #ff9d8d; }
html[data-theme="dark"] .ai-result { border-color: rgba(126,214,199,.2); border-left-color: #2ee6c5; background: rgba(16,32,46,.6); }
html[data-theme="dark"] .ai-result.degraded { border-left-color: #ffb547; background: rgba(255,181,71,.06); }
html[data-theme="dark"] .ai-mode { color: #9db8b8; }
html[data-theme="dark"] .ai-mode strong { color: #2ee6c5; }
html[data-theme="dark"] .ai-mode small { color: #6f8b90; }
html[data-theme="dark"] .ai-degraded-badge { background: rgba(255,181,71,.16); color: #ffcf8a; }
html[data-theme="dark"] .ai-summary { color: #d7ece7; }
html[data-theme="dark"] .ai-recommendation { border-top-color: rgba(126,214,199,.1); }
html[data-theme="dark"] .ai-recommendation strong { color: #eaf6f3; }
html[data-theme="dark"] .ai-recommendation p { color: #9db8b8; }
html[data-theme="dark"] .ai-priority { background: rgba(52,224,180,.16); color: #7ff0da; }
html[data-theme="dark"] .ai-priority.high { background: rgba(255,107,87,.16); color: #ff9d8d; }
html[data-theme="dark"] .ai-priority.medium { background: rgba(255,181,71,.16); color: #ffcf8a; }
html[data-theme="dark"] .ai-evidence { color: #7ff0da; }
html[data-theme="dark"] .ai-evidence ul { color: #9db8b8; }
html[data-theme="dark"] .ai-evidence li strong { color: #cfe7e1; }
html[data-theme="dark"] .ai-evidence li small { color: #6f8b90; }
html[data-theme="dark"] .ai-notices { border-top-color: rgba(126,214,199,.2); }
html[data-theme="dark"] .ai-quality { color: #ffcf8a; }
html[data-theme="dark"] .ai-quality strong { color: #ffcf8a; }
html[data-theme="dark"] .ai-generated { color: #6f8b90; }
</style>
