<template>
  <section ref="workspaceElement" class="conversation-workspace" aria-label="对话工作台">
    <header class="conversation-heading">
      <button type="button" :aria-expanded="expanded" aria-controls="conversation-transcript" @click="expanded = !expanded"><span aria-hidden="true">◈</span><strong>对话工作台</strong><small>{{ restoring ? '恢复中' : ready ? '已保存' : '未连接' }}</small><span aria-hidden="true">{{ expanded ? '⌄' : '⌃' }}</span></button>
      <p class="conversation-context" :title="context">{{ context }}</p>
    </header>
    <div v-show="expanded" id="conversation-transcript" ref="transcript" class="conversation-transcript" role="log" aria-label="会话记录" aria-live="polite" :aria-busy="busy">
      <p v-if="!turns.length" class="conversation-empty">直接说出你想体检的位置，或询问当前地图和报告。</p>
      <article v-for="turn in turns" :key="turn.id" class="conversation-turn">
        <p class="conversation-user"><span>你</span>{{ turn.message }}</p>
        <p class="conversation-answer"><span>助手</span>{{ turn.answer }}</p>
        <details v-if="turn.evidence_refs?.length"><summary>查看计算依据（{{ turn.evidence_refs.length }}）</summary><ul><li v-for="ref in turn.evidence_refs" :key="`${ref.type}:${ref.id}`"><strong>{{ ref.label }}</strong> {{ ref.detail }}<small>{{ ref.id }}</small></li></ul></details>
        <details v-if="turn.planning?.tool_calls.length"><summary>工具执行记录（{{ turn.planning.tool_calls.length }}）</summary><PlanningToolResults :calls="turn.planning.tool_calls" /></details>
        <PlanningComparison v-for="comparison in turn.planning?.comparisons ?? []" :key="comparison.id" :comparison="comparison" @show-simulation="showSimulation(turn, $event)" />
        <ConversationExtensionResults :semantic-review="turn.semantic_review" :sampling-experiment="turn.sampling_experiment" :optimization="turn.optimization" :governance-state="turn.governance_state" :recomputation="turn.recomputation" :observation="turn.observation" :role-report="turn.role_report" @sampling="emit('sampling', $event)" @combination="emit('combination', $event)" />
        <div v-if="turn.planning?.simulations.length" class="conversation-inline-actions"><button v-for="simulation in turn.planning.simulations" :key="simulation.id" type="button" @click="emit('simulation', simulation)">在地图查看{{ simulation.category_label }}模拟</button></div>
        <div v-for="(action, index) in turn.actions" :key="index">
          <div v-if="action.type === 'show_history'" class="conversation-inline-actions"><button v-for="item in action.items" :key="item.report_id" type="button" @click="emit('open-report', item.report_id)">{{ item.center.address }} · {{ item.minutes }}分钟</button></div>
          <div v-if="action.type === 'show_address_candidates'" class="conversation-inline-actions"><button v-for="(item, candidateIndex) in action.items" :key="`${item.lng}:${item.lat}`" type="button" :disabled="busy || analyzing" @click="emit('send', `选择第${candidateIndex + 1}个地址`)">{{ candidateIndex + 1 }} · {{ item.name || item.address }}</button></div>
        </div>
      </article>
      <p v-if="busy" class="conversation-empty" role="status">正在核验当前上下文与证据…</p>
    </div>
    <div v-if="pending" class="conversation-confirmation" role="status"><p>{{ pending.label }}</p><small>本次上限：{{ pending.budget.max_route_pairs }}条路线 · {{ pending.budget.max_model_calls }}次模型调用</small><button type="button" :disabled="busy || analyzing" @click="emit('confirm')">确认执行</button></div>
    <p v-if="error" class="conversation-error" role="alert">{{ error }}<button v-if="canRetry" type="button" :disabled="busy" @click="emit('retry')">重试本条消息</button><button v-else-if="!ready" type="button" :disabled="restoring" @click="emit('reconnect')">重新连接</button></p>
    <div v-if="task" class="conversation-task" role="status"><span>{{ analyzing ? `${progressLabel || '正在体检'} · ${progress}%` : task.status === 'cancelled' ? '体检已取消' : task.status === 'failed' ? '体检失败' : '体检已完成' }}</span><button v-if="analyzing" type="button" :disabled="cancelling" @click="emit('cancel-task')">{{ cancelling ? '取消中' : '取消体检' }}</button><button v-else-if="task.status === 'cancelled'" type="button" @click="emit('retry-task')">重新体检</button></div>
    <ExecutionCheckpointReview v-if="task?.status === 'failed' && !analyzing" :key="task.id" :execution-id="task.id" allow-resume @resume="emit('retry-task')" />
    <form class="conversation-composer" @submit.prevent="submit">
      <textarea v-model="message" rows="2" maxlength="1000" aria-label="和生活圈助手对话" :disabled="!ready || busy" :placeholder="analyzing ? '体检进行中，可询问进度或说：取消体检' : '例如：只看1公里稀缺图层；定位东南角；预算10万元规划药店'" @keydown="handleKeydown" />
      <button type="submit" :disabled="!ready || busy || !message.trim()">{{ busy ? '处理中' : '发送' }}</button>
    </form>
  </section>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { ConversationTurn } from '../types/workspace'
import type { AnalysisTask } from '../types/report'
import type { SimulationResult } from '../types/simulation'
import type { Combination, SamplingLayers } from '../types/completion'
import PlanningToolResults from './PlanningToolResults.vue'
import PlanningComparison from './PlanningComparison.vue'
import ConversationExtensionResults from './ConversationExtensionResults.vue'
import ExecutionCheckpointReview from './ExecutionCheckpointReview.vue'

const props = defineProps<{
  context: string; turns: ConversationTurn[]; ready: boolean; busy: boolean; restoring: boolean; error: string; canRetry: boolean
  pending: ConversationTurn['pending'] | null; task: AnalysisTask | null; analyzing: boolean; progress: number; progressLabel: string; cancelling: boolean
}>()
const emit = defineEmits<{ send: [message: string]; confirm: []; retry: []; reconnect: []; 'cancel-task': []; 'retry-task': []; 'open-report': [id: string]; simulation: [result: SimulationResult]; sampling: [layers: SamplingLayers]; combination: [value: Combination]; resize: [height: number] }>()
const message = ref('')
const expanded = ref(false)
const workspaceElement = ref<HTMLElement | null>(null)
const transcript = ref<HTMLElement | null>(null)
let resizeObserver: ResizeObserver | undefined
onMounted(() => {
  if (typeof ResizeObserver === 'undefined' || !workspaceElement.value) return
  resizeObserver = new ResizeObserver(entries => { const entry = entries[0]; if (entry) emit('resize', entry.target.getBoundingClientRect().height) })
  resizeObserver.observe(workspaceElement.value)
})
onBeforeUnmount(() => resizeObserver?.disconnect())
function showSimulation(turn: ConversationTurn, id: string) {
  const simulation = turn.planning?.simulations.find(item => item.id === id)
  if (simulation) emit('simulation', simulation)
}
function submit() {
  if (!props.ready || props.busy || !message.value.trim()) return
  emit('send', message.value.trim())
  expanded.value = true
}
function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); submit() }
}
watch(() => props.turns.length, async () => {
  message.value = ''
  await nextTick()
  if (transcript.value) transcript.value.scrollTop = transcript.value.scrollHeight
})
</script>

<style scoped>
.conversation-workspace { position: absolute; z-index: 7; bottom: 20px; left: var(--hud-left); right: var(--hud-right); min-width: 0; max-width: 780px; margin-inline: auto; border: 1px solid #cbdcd3; border-radius: 10px; background: rgba(249,252,248,.98); box-shadow: 0 8px 24px rgba(24,52,49,.18); color: #24483f; }
.conversation-heading { padding: 10px 12px 6px; }
.conversation-heading > button { display: flex; align-items: center; gap: 7px; width: 100%; padding: 0; background: transparent; color: inherit; text-align: left; }
.conversation-heading strong { font-size: 12px; }.conversation-heading small { margin-left: auto; font-size: 10px; opacity: .65; }
.conversation-context { margin: 5px 0 0; font-size: 10px; color: #667c73; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.conversation-transcript { max-height: min(320px, 35dvh); overflow-y: auto; overscroll-behavior: contain; padding: 0 12px; font-size: 11px; line-height: 1.7; scrollbar-width: thin; }
.conversation-empty { color: #73877f; font-size: 11px; }.conversation-turn { padding: 9px 0; border-top: 1px solid #dce6e0; overflow-wrap: anywhere; }
.conversation-turn p { margin: 3px 0 7px; white-space: pre-line; }.conversation-turn p > span { display: block; font-size: 9px; opacity: .6; }.conversation-user { color: #637f75; }.conversation-answer { color: #24483f; }
.conversation-turn details { margin-top: 6px; }.conversation-turn summary { cursor: pointer; font-size: 10px; }.conversation-turn ul { padding-left: 16px; }.conversation-turn li small { display: block; opacity: .6; font-size: 9px; }
.conversation-confirmation { display: flex; flex-wrap: wrap; align-items: center; gap: 7px; padding: 9px 12px; border-top: 1px solid #dce6e0; background: #f4efe2; font-size: 11px; }.conversation-confirmation p { width: 100%; margin: 0; }.conversation-confirmation small { flex: 1; font-size: 9px; }
.conversation-confirmation button, .conversation-inline-actions button, .conversation-error button, .conversation-task button { padding: 5px 7px; border: 1px solid #cbdcd3; border-radius: 5px; color: inherit; background: transparent; font-size: 10px; }
.conversation-inline-actions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 7px; }.conversation-error { margin: 5px 12px; color: #af5737; font-size: 11px; line-height: 1.6; overflow-wrap: anywhere; }.conversation-error button { margin-left: 6px; }
.conversation-task { display: flex; justify-content: space-between; align-items: center; gap: 6px; padding: 4px 12px; font-size: 10px; }
.conversation-composer { display: flex; align-items: stretch; gap: 8px; padding: 6px 10px 10px; }.conversation-composer textarea { min-width: 0; flex: 1; resize: vertical; max-height: 120px; min-height: 42px; padding: 8px; border: 1px solid #cbdcd3; border-radius: 6px; background: #fff; color: inherit; font: 11px/1.6 inherit; }.conversation-composer textarea:focus-visible { outline: 2px solid #2e8f80; outline-offset: 1px; }.conversation-composer > button { flex: 0 0 48px; border-radius: 6px; background: #183d45; color: #fff; font-size: 11px; }.conversation-workspace button:disabled { opacity: .5; cursor: default; }
html[data-theme="dark"] .conversation-workspace { border-color: rgba(126,214,199,.24); background: rgba(24,40,56,.98); color: #cfe7e1; }html[data-theme="dark"] .conversation-context, html[data-theme="dark"] .conversation-empty, html[data-theme="dark"] .conversation-user { color: #9db8b8; }html[data-theme="dark"] .conversation-answer { color: #e1f0eb; }html[data-theme="dark"] .conversation-turn { border-color: rgba(126,214,199,.18); }html[data-theme="dark"] .conversation-composer textarea { border-color: rgba(126,214,199,.24); background: #101d2a; }html[data-theme="dark"] .conversation-composer > button { background: #2ee6c5; color: #04211c; }html[data-theme="dark"] .conversation-confirmation { background: #3a3527; }html[data-theme="dark"] .conversation-error { color: #ffcf8a; }
@media (max-width: 820px) { .conversation-workspace { left: 8px; right: 8px; bottom: 76px; z-index: 3; }.conversation-heading { padding-top: 8px; }.conversation-transcript { max-height: min(240px, 30dvh); }.conversation-composer textarea { font-size: 16px; line-height: 1.35; min-height: 45px; }.conversation-context { max-width: 100%; }.conversation-confirmation small { min-width: 150px; } }
</style>
