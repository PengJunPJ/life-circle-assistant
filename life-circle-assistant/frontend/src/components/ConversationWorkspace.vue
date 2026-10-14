<template>
  <section v-if="assistantVisible" ref="workspaceElement" class="conversation-workspace" :class="{ dragging }" :style="{ transform: `translate3d(${position.x}px, ${position.y}px, 0)` }" aria-label="对话工作台">
    <header class="conversation-heading">
      <div class="conversation-heading-row" @pointerdown="startDrag">
        <button type="button" :aria-expanded="expanded" aria-controls="conversation-transcript" @click="toggleExpanded"><span class="conversation-ai-mark" aria-hidden="true">AI</span><span class="conversation-title"><strong>AI 规划助手</strong><small>自然语言操作地图与报告</small></span><em class="conversation-state">{{ restoring ? '恢复中' : ready ? '已连接' : '未连接' }}</em><span class="conversation-toggle" aria-hidden="true">{{ expanded ? '⌄' : '⌃' }}</span></button>
        <button class="conversation-hide" type="button" aria-label="隐藏AI规划助手" title="隐藏AI规划助手" @pointerdown.stop @click.stop="hideAssistant">×</button>
      </div>
      <p class="conversation-context" :title="context">{{ context }}</p>
      <div class="conversation-quick-actions" role="group" aria-label="AI快捷操作">
        <button v-for="prompt in quickPrompts" :key="prompt.label" type="button" :disabled="!ready || busy" @click="sendQuickPrompt(prompt.message)">{{ prompt.label }}</button>
      </div>
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
  <button v-else ref="launcherElement" class="conversation-launcher" type="button" aria-label="显示AI规划助手" title="显示AI规划助手" @click="showAssistant"><img class="conversation-launcher-icon" src="/ai-planning-assistant.png" alt="" aria-hidden="true" draggable="false" /></button>
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
const assistantVisible = ref(true)
const dragging = ref(false)
const dragMoved = ref(false)
const position = ref({ x: 0, y: 0 })
const workspaceElement = ref<HTMLElement | null>(null)
const launcherElement = ref<HTMLButtonElement | null>(null)
const transcript = ref<HTMLElement | null>(null)
const quickPrompts = [
  { label: '开始体检', message: '开始体检当前社区' },
  { label: '找步行盲区', message: '找出当前15分钟步行盲区' },
  { label: '做组合选址', message: '根据当前盲区做组合设施选址' },
]
let resizeObserver: ResizeObserver | undefined
let dragPointerId: number | null = null
let dragOrigin: { x: number; y: number; position: { x: number; y: number } } | null = null
function measureWorkspace() {
  const element = workspaceElement.value
  if (element) emit('resize', element.getBoundingClientRect().height)
}

function observeWorkspace() {
  resizeObserver?.disconnect()
  if (typeof ResizeObserver === 'undefined' || !workspaceElement.value) return
  resizeObserver = new ResizeObserver(entries => { const entry = entries[0]; if (entry) emit('resize', entry.target.getBoundingClientRect().height) })
  resizeObserver.observe(workspaceElement.value)
}

onMounted(observeWorkspace)
onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  stopDrag()
})

function clampPosition(x: number, y: number) {
  const element = workspaceElement.value
  if (!element) return { x, y }
  const rect = element.getBoundingClientRect()
  const baseLeft = rect.left - position.value.x
  const baseTop = rect.top - position.value.y
  const minX = 8 - baseLeft
  const maxX = Math.max(minX, window.innerWidth - rect.width - 8 - baseLeft)
  const minY = 8 - baseTop
  const maxY = Math.max(minY, window.innerHeight - rect.height - 8 - baseTop)
  return { x: Math.min(maxX, Math.max(minX, x)), y: Math.min(maxY, Math.max(minY, y)) }
}

function startDrag(event: PointerEvent) {
  if (event.button !== 0 || !workspaceElement.value) return
  dragPointerId = event.pointerId
  dragOrigin = { x: event.clientX, y: event.clientY, position: { ...position.value } }
  dragMoved.value = false
  dragging.value = true
  window.addEventListener('pointermove', handlePointerMove)
  window.addEventListener('pointerup', stopDrag)
  window.addEventListener('pointercancel', stopDrag)
}

function handlePointerMove(event: PointerEvent) {
  if (!dragOrigin || event.pointerId !== dragPointerId) return
  const dx = event.clientX - dragOrigin.x
  const dy = event.clientY - dragOrigin.y
  if (Math.abs(dx) > 4 || Math.abs(dy) > 4) dragMoved.value = true
  if (!dragMoved.value) return
  event.preventDefault()
  position.value = clampPosition(dragOrigin.position.x + dx, dragOrigin.position.y + dy)
}

function stopDrag(event?: PointerEvent) {
  if (event && dragPointerId !== null && event.pointerId !== dragPointerId) return
  window.removeEventListener('pointermove', handlePointerMove)
  window.removeEventListener('pointerup', stopDrag)
  window.removeEventListener('pointercancel', stopDrag)
  dragPointerId = null
  dragOrigin = null
  dragging.value = false
}

function toggleExpanded() {
  if (dragMoved.value) {
    dragMoved.value = false
    return
  }
  expanded.value = !expanded.value
}

async function hideAssistant() {
  assistantVisible.value = false
  await nextTick()
  launcherElement.value?.focus()
}

async function showAssistant() {
  assistantVisible.value = true
  await nextTick()
  measureWorkspace()
}

watch(assistantVisible, async visible => {
  if (!visible) {
    resizeObserver?.disconnect()
    emit('resize', 0)
    return
  }
  await nextTick()
  observeWorkspace()
  measureWorkspace()
})
function showSimulation(turn: ConversationTurn, id: string) {
  const simulation = turn.planning?.simulations.find(item => item.id === id)
  if (simulation) emit('simulation', simulation)
}
function submit() {
  if (!props.ready || props.busy || !message.value.trim()) return
  emit('send', message.value.trim())
  expanded.value = true
}
function sendQuickPrompt(prompt: string) {
  if (!props.ready || props.busy) return
  emit('send', prompt)
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
.conversation-workspace { position: absolute; z-index: 7; right: 16px; bottom: 20px; width: var(--conversation-width); min-width: 0; max-width: none; margin: 0; border: 1px solid #a9cfc0; border-top: 3px solid #2f8f80; border-radius: 10px; background: rgba(249,252,248,.98); box-shadow: 0 10px 28px rgba(24,52,49,.2); color: #24483f; }
.conversation-workspace.dragging { user-select: none; }
.conversation-heading { padding: 8px 12px 6px; }
.conversation-heading-row { display: flex; align-items: center; gap: 5px; touch-action: none; cursor: grab; }
.conversation-heading-row:active, .conversation-workspace.dragging .conversation-heading-row { cursor: grabbing; }
.conversation-heading-row > button:first-child { display: flex; align-items: center; gap: 7px; flex: 1; min-width: 0; padding: 0; background: transparent; color: inherit; text-align: left; }
.conversation-hide { flex: 0 0 24px; width: 24px; height: 24px; border-radius: 50%; background: transparent; color: #668078; font-size: 17px; line-height: 1; }
.conversation-hide:hover { background: #e8f0eb; color: #24483f; }
.conversation-ai-mark { display: grid; place-items: center; flex: 0 0 28px; width: 28px; height: 22px; border-radius: 5px; background: #183d45; color: #d8f5e8; font-size: 9px; font-weight: 800; letter-spacing: .05em; }
.conversation-title { display: grid; gap: 2px; min-width: 0; }.conversation-heading strong { font-size: 12px; }.conversation-heading small { color: #668078; font-size: 9px; }.conversation-state { margin-left: auto; padding: 3px 7px; border-radius: 10px; background: #e4f2eb; color: #367b68; font-size: 9px; font-style: normal; white-space: nowrap; }.conversation-toggle { color: #5e7b72; font-size: 15px; line-height: 1; }
.conversation-context { margin: 5px 0 0; font-size: 10px; color: #667c73; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.conversation-quick-actions { display: flex; gap: 6px; margin-top: 7px; overflow-x: auto; scrollbar-width: none; }.conversation-quick-actions::-webkit-scrollbar { display: none; }.conversation-quick-actions button { flex: 0 0 auto; min-height: 25px; padding: 3px 8px; border: 1px solid #c6ddd2; border-radius: 13px; background: #f1f8f4; color: #397568; font-size: 9px; white-space: nowrap; }.conversation-quick-actions button:hover:not(:disabled) { border-color: #69a995; background: #e3f2ea; }.conversation-quick-actions button:disabled { cursor: default; opacity: .52; }
.conversation-transcript { max-height: min(320px, 35dvh); overflow-y: auto; overscroll-behavior: contain; padding: 0 12px; font-size: 11px; line-height: 1.7; scrollbar-width: thin; }
.conversation-empty { color: #73877f; font-size: 11px; }.conversation-turn { padding: 9px 0; border-top: 1px solid #dce6e0; overflow-wrap: anywhere; }
.conversation-turn p { margin: 3px 0 7px; white-space: pre-line; }.conversation-turn p > span { display: block; font-size: 9px; opacity: .6; }.conversation-user { color: #637f75; }.conversation-answer { color: #24483f; }
.conversation-turn details { margin-top: 6px; }.conversation-turn summary { cursor: pointer; font-size: 10px; }.conversation-turn ul { padding-left: 16px; }.conversation-turn li small { display: block; opacity: .6; font-size: 9px; }
.conversation-confirmation { display: flex; flex-wrap: wrap; align-items: center; gap: 7px; padding: 9px 12px; border-top: 1px solid #dce6e0; background: #f4efe2; font-size: 11px; }.conversation-confirmation p { width: 100%; margin: 0; }.conversation-confirmation small { flex: 1; font-size: 9px; }
.conversation-confirmation button, .conversation-inline-actions button, .conversation-error button, .conversation-task button { padding: 5px 7px; border: 1px solid #cbdcd3; border-radius: 5px; color: inherit; background: transparent; font-size: 10px; }
.conversation-inline-actions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 7px; }.conversation-error { margin: 5px 12px; color: #af5737; font-size: 11px; line-height: 1.6; overflow-wrap: anywhere; }.conversation-error button { margin-left: 6px; }
.conversation-task { display: flex; justify-content: space-between; align-items: center; gap: 6px; padding: 4px 12px; font-size: 10px; }
.conversation-composer { display: flex; align-items: stretch; gap: 8px; padding: 6px 10px 10px; }.conversation-composer textarea { min-width: 0; flex: 1; resize: vertical; max-height: 120px; min-height: 42px; padding: 8px; border: 1px solid #cbdcd3; border-radius: 6px; background: #fff; color: inherit; font: 11px/1.6 inherit; }.conversation-composer textarea:focus-visible { outline: 2px solid #2e8f80; outline-offset: 1px; }.conversation-composer > button { flex: 0 0 48px; border-radius: 6px; background: #183d45; color: #fff; font-size: 11px; }.conversation-workspace button:disabled { opacity: .5; cursor: default; }
html[data-theme="dark"] .conversation-workspace { border-color: rgba(126,214,199,.3); border-top-color: #2ee6c5; background: rgba(24,40,56,.98); color: #cfe7e1; }html[data-theme="dark"] .conversation-ai-mark { background: #2ee6c5; color: #04211c; }html[data-theme="dark"] .conversation-heading small { color: #9db8b8; }html[data-theme="dark"] .conversation-state { background: rgba(46,230,197,.14); color: #7ff0da; }html[data-theme="dark"] .conversation-toggle { color: #9db8b8; }html[data-theme="dark"] .conversation-quick-actions button { border-color: rgba(126,214,199,.28); background: rgba(46,230,197,.08); color: #a4e6d6; }html[data-theme="dark"] .conversation-quick-actions button:hover:not(:disabled) { background: rgba(46,230,197,.16); }html[data-theme="dark"] .conversation-context, html[data-theme="dark"] .conversation-empty, html[data-theme="dark"] .conversation-user { color: #9db8b8; }html[data-theme="dark"] .conversation-answer { color: #e1f0eb; }html[data-theme="dark"] .conversation-turn { border-color: rgba(126,214,199,.18); }html[data-theme="dark"] .conversation-composer textarea { border-color: rgba(126,214,199,.24); background: #101d2a; }html[data-theme="dark"] .conversation-composer > button { background: #2ee6c5; color: #04211c; }html[data-theme="dark"] .conversation-confirmation { background: #3a3527; }html[data-theme="dark"] .conversation-error { color: #ffcf8a; }
html[data-theme="dark"] .conversation-hide { color: #9db8b8; }html[data-theme="dark"] .conversation-hide:hover { background: rgba(46,230,197,.12); color: #e1f0eb; }
.conversation-launcher { --conversation-launcher-lift: 42px; position: absolute; z-index: 7; right: 16px; bottom: calc(20px + var(--conversation-launcher-lift)); width: 48px; height: 48px; display: grid; place-items: center; padding: 0; overflow: visible; border: 0; border-radius: 0; background: transparent; color: inherit; box-shadow: none; }
.conversation-launcher:hover { background: transparent; }
.conversation-launcher-icon { width: 42px; height: 42px; object-fit: contain; pointer-events: none; animation: assistant-breathe 3.4s ease-in-out infinite; }
.conversation-launcher:hover .conversation-launcher-icon { filter: drop-shadow(0 3px 5px rgba(40, 178, 196, .22)); }
html[data-theme="dark"] .conversation-launcher { background: transparent; color: inherit; box-shadow: none; }html[data-theme="dark"] .conversation-launcher:hover { background: transparent; }
@keyframes assistant-breathe { 0%, 100% { transform: translateY(0) scale(1); } 50% { transform: translateY(-2px) scale(1.035); } }
@media (prefers-reduced-motion: reduce) { .conversation-launcher-icon { animation: none; } }
@media (max-width: 820px) { .conversation-workspace { left: 8px; right: 8px; bottom: 76px; width: auto; z-index: 3; }.conversation-launcher { right: 12px; bottom: calc(76px + var(--conversation-launcher-lift)); z-index: 4; }.conversation-heading { padding-top: 8px; }.conversation-transcript { max-height: min(240px, 30dvh); }.conversation-composer textarea { font-size: 16px; line-height: 1.35; min-height: 45px; }.conversation-context { max-width: 100%; }.conversation-confirmation small { min-width: 150px; } }
</style>
