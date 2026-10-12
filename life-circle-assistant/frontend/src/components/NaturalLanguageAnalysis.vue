<template>
  <section class="panel-section natural-analysis" aria-labelledby="natural-analysis-title">
    <div class="natural-heading">
      <strong id="natural-analysis-title">用一句话发起体检</strong>
      <button v-if="draft" type="button" :disabled="busy || disabled" @click="reset">重新开始</button>
    </div>
    <p class="natural-note">描述地点、步行时间和关注设施，确认参数后开始。点击“重新开始”可返回手工体检。</p>
    <div v-if="conversation.length" class="natural-conversation" role="log" aria-label="体检对话" aria-live="polite">
      <p v-for="(turn, index) in conversation" :key="index" :class="turn.role">
        <b>{{ turn.role === 'user' ? '你' : '助手' }}</b>{{ turn.text }}
      </p>
    </div>
    <label class="sr-only" for="analysis-message">体检需求或补充信息</label>
    <textarea id="analysis-message" v-model="message" rows="3" maxlength="1000" :disabled="busy || disabled"
      placeholder="例如：体检红山街道海韵东路，步行15分钟，关注买菜和买药"
      @keydown.ctrl.enter.prevent="send" @keydown.meta.enter.prevent="send" />
    <div class="natural-input-actions">
      <button type="button" :disabled="busy || disabled" @click="message = '当前选点，步行15分钟，关注买菜和买药'">试试当前选点</button>
      <button class="natural-send" type="button" :disabled="busy || disabled || !message.trim()" @click="send">
        {{ busy ? '正在整理…' : draft ? '补充 / 修改' : '整理需求' }}
      </button>
    </div>
    <p v-if="error" class="location-error" role="alert">{{ error }}</p>
    <div v-if="draft" class="natural-preview">
      <p class="natural-parser" role="status">{{ parserLabel }}</p>
      <label for="intent-address">{{ draft.use_current_center ? '使用当前选点' : '社区或地址' }}</label>
      <div v-if="!draft.use_current_center" class="natural-address-row">
        <input id="intent-address" :value="draft.address" maxlength="200" :disabled="busy || disabled" placeholder="补充社区或地址"
          @input="editAddress(($event.target as HTMLInputElement).value)" @keydown.enter="resolveAddress" />
        <button type="button" :disabled="busy || disabled || !draft.address.trim()" @click="resolveAddress">确认位置</button>
      </div>
      <div v-if="candidates.length > 1" class="candidate-list" aria-label="对话地址候选">
        <button v-for="candidate in candidates" :key="`${candidate.lng}-${candidate.lat}-${candidate.address}`" type="button"
          :disabled="busy || disabled" :aria-pressed="selected?.lng === candidate.lng && selected?.lat === candidate.lat && selected?.address === candidate.address"
          @click="chooseCandidate(candidate)">
          <span><strong>{{ candidate.address }}</strong><small>BD-09 · {{ candidate.lng.toFixed(6) }}, {{ candidate.lat.toFixed(6) }}</small></span>
        </button>
      </div>
      <p v-if="selected" class="natural-location">{{ selected.address }}<small>BD-09 · {{ selected.lng.toFixed(6) }}, {{ selected.lat.toFixed(6) }}</small></p>
      <p v-else class="natural-note">{{ candidates.length > 1 ? '找到多个候选，请选择一个位置。' : '位置尚未确认；请补充地址或重试位置查询。' }}</p>
      <p v-if="centerStale" class="location-error">当前选点已改变，请重新发送“当前选点”确认位置。</p>
      <div class="natural-options">
        <label>步行时间
          <select :value="draft.minutes ?? ''" :disabled="busy || disabled" aria-label="对话步行时间" @change="editMinutes($event)">
            <option disabled value="">请选择</option>
            <option v-for="time in [10, 15, 20]" :key="time" :value="time">{{ time }}分钟</option>
          </select>
        </label>
        <label>分析精度
          <select v-model="draft.mode" :disabled="busy || disabled" aria-label="对话分析精度" @change="markEdited('mode')">
            <option value="demo">快速分析</option><option value="analysis">正式分析</option>
          </select>
        </label>
      </div>
      <fieldset :disabled="busy || disabled" class="natural-categories">
        <legend>关注设施（可修改）</legend>
        <label v-for="(label, category) in FACILITY_LABELS" :key="category">
          <input v-model="draft.categories" type="checkbox" :value="category" @change="markEdited('categories')" />{{ label }}
        </label>
      </fieldset>
      <p v-if="defaultsLabel" class="natural-note">未提及的参数采用默认值：{{ defaultsLabel }}，可修改。</p>
      <p v-if="!draft.categories.length" class="location-error">请至少选择一类设施。</p>
      <p class="natural-note">{{ realApiConfigured ? '确认后调用真实地图服务测算。' : '当前使用本地快照，仅支持内置样例周边，不代表最新真实测算。' }}</p>
      <button class="primary-action" type="button" :disabled="!canConfirm" @click="confirm">确认并开始{{ realApiConfigured ? '真实分析' : '快照体检' }}</button>
      <p v-if="message.trim()" class="natural-note">有尚未发送的描述，请先整理需求再确认。</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { FACILITY_LABELS } from '../constants/facilities'
import { parseAnalysisIntent, searchAddressCandidates } from '../services/analysisApi'
import type { AnalysisIntent, ConfirmedAnalysisIntent, IntentDraft } from '../types/analysisIntent'
import type { AnalysisCenter, LocationCandidate } from '../types/location'
import type { AnalysisMinutes } from '../types/report'

const props = defineProps<{ center: AnalysisCenter; disabled: boolean; realApiConfigured: boolean }>()
const emit = defineEmits<{ confirm: [intent: ConfirmedAnalysisIntent]; 'update:active': [active: boolean] }>()
const message = ref('')
const conversation = ref<{ role: 'user' | 'assistant'; text: string }[]>([])
const draft = ref<IntentDraft | null>(null)
watch(() => Boolean(draft.value), active => emit('update:active', active), { immediate: true })
const parsed = ref<AnalysisIntent | null>(null)
const candidates = ref<LocationCandidate[]>([])
const selected = ref<AnalysisCenter | null>(null)
const busy = ref(false)
const error = ref('')
const fingerprint = (center: AnalysisCenter) => `${center.lng}|${center.lat}|${center.address}|${center.supportStatus}`
const centerStale = computed(() => Boolean(draft.value?.use_current_center && selected.value && fingerprint(selected.value) !== fingerprint(props.center)))
const canConfirm = computed(() => Boolean(
  draft.value?.minutes && draft.value.categories.length && selected.value?.supportStatus === 'supported'
  && !centerStale.value && !busy.value && !props.disabled && !message.value.trim() && !error.value,
))
const parserLabel = computed(() => parsed.value?.parser === 'llm'
  ? `模型解析 · ${parsed.value.model}`
  : parsed.value?.parser === 'rules_degraded' ? '规则解析 · 模型不可用或结果未通过校验' : '规则解析 · 模型未启用')
const defaultsLabel = computed(() => {
  if (!draft.value) return ''
  const labels = { minutes: '15分钟', mode: '快速分析', categories: '全部七类设施' }
  return draft.value.defaulted_fields.map(key => labels[key]).join('、')
})

function addTurn(role: 'user' | 'assistant', text: string) {
  conversation.value = [...conversation.value, { role, text }].slice(-8)
}

async function resolveLocation() {
  selected.value = null
  candidates.value = []
  if (!draft.value) return
  if (draft.value.use_current_center) {
    if (props.center.supportStatus !== 'supported') throw new Error('当前选点尚未确认或不在支持范围内，请先在地图上选择有效位置。')
    selected.value = { ...props.center }
  } else if (draft.value.address.trim()) {
    candidates.value = await searchAddressCandidates(draft.value.address.trim())
    if (!candidates.value.length) throw new Error('没有找到地址候选，请补充更完整的社区或地址。')
    if (candidates.value.length === 1) chooseCandidate(candidates.value[0]!)
  }
}

async function send() {
  if (busy.value || props.disabled || !message.value.trim()) return
  busy.value = true
  error.value = ''
  selected.value = null
  candidates.value = []
  const text = message.value.trim()
  try {
    const result = await parseAnalysisIntent(text, draft.value ?? undefined)
    parsed.value = result
    draft.value = result.draft
    message.value = ''
    addTurn('user', text)
    addTurn('assistant', result.message)
    await resolveLocation()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '需求整理失败，请重试。'
  } finally {
    busy.value = false
  }
}

async function resolveAddress() {
  if (busy.value || props.disabled || !draft.value?.address.trim()) return
  busy.value = true
  error.value = ''
  try { await resolveLocation() }
  catch (reason) { error.value = reason instanceof Error ? reason.message : '位置查询失败，请重试。' }
  finally { busy.value = false }
}

function editAddress(value: string) {
  if (!draft.value) return
  draft.value.address = value
  draft.value.use_current_center = false
  selected.value = null
  candidates.value = []
  error.value = ''
}

function chooseCandidate(candidate: LocationCandidate) {
  selected.value = { ...candidate, selectionMethod: 'address', supportStatus: 'supported' }
  error.value = ''
}

function markEdited(field: IntentDraft['defaulted_fields'][number]) {
  if (draft.value) draft.value.defaulted_fields = draft.value.defaulted_fields.filter(key => key !== field)
}

function editMinutes(event: Event) {
  if (!draft.value) return
  draft.value.minutes = Number((event.target as HTMLSelectElement).value) as AnalysisMinutes
  markEdited('minutes')
}

function confirm() {
  if (!canConfirm.value || !draft.value?.minutes || !selected.value) return
  emit('confirm', { center: { ...selected.value }, minutes: draft.value.minutes, mode: draft.value.mode, categories: [...draft.value.categories] })
}

function reset() {
  draft.value = null
  parsed.value = null
  selected.value = null
  candidates.value = []
  conversation.value = []
  message.value = ''
  error.value = ''
}
</script>

<style scoped>
.natural-analysis { --nl-ink: #294b4c; --nl-muted: #637572; --nl-input: #fff; --nl-border: #cddbd4; --nl-soft: #edf6f1; color: var(--nl-ink); }
.natural-heading, .natural-input-actions { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.natural-heading strong { font-size: 13px; }
.natural-heading button, .natural-input-actions button, .natural-address-row button { font-size: 11px; color: var(--nl-ink); background: var(--nl-soft); border-radius: 4px; padding: 6px; }
.natural-note, .natural-parser { font-size: 11px; line-height: 1.65; color: var(--nl-muted); margin: 8px 0; overflow-wrap: anywhere; }
.natural-analysis textarea, .natural-analysis select, .natural-address-row input { font: inherit; font-size: 12px; color: var(--nl-ink); background: var(--nl-input); border: 1px solid var(--nl-border); border-radius: 5px; padding: 8px; width: 100%; min-width: 0; }
.natural-analysis textarea { display: block; resize: vertical; line-height: 1.7; min-height: 80px; }
.natural-analysis textarea:focus-visible, .natural-analysis select:focus-visible { outline: 2px solid #3b9a7d; outline-offset: 2px; }
.natural-analysis button:disabled { opacity: .55; cursor: not-allowed; }
.natural-input-actions { margin-top: 8px; }
.natural-input-actions .natural-send { background: #286b60; color: #fff; }
.natural-conversation { max-height: 180px; overflow: auto; margin-bottom: 10px; }
.natural-conversation p { font-size: 11px; line-height: 1.7; margin: 6px 0; padding: 7px; border-radius: 4px; overflow-wrap: anywhere; }
.natural-conversation .assistant { background: var(--nl-soft); }
.natural-conversation b { margin-right: 6px; }
.natural-preview { border-top: 1px solid var(--nl-border); margin-top: 12px; padding-top: 4px; }
.natural-address-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 6px; }
.natural-location { font-size: 12px; line-height: 1.65; overflow-wrap: anywhere; padding-left: 8px; border-left: 2px solid #3b9a7d; }
.natural-location small { display: block; font-size: 10px; color: var(--nl-muted); }
.natural-options { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.natural-options select { margin-top: 6px; }
.natural-categories { padding: 0; border: 0; margin: 0; display: flex; flex-wrap: wrap; gap: 8px 12px; }
.natural-categories legend { font-size: 11px; color: var(--nl-muted); padding: 0 0 8px; }
.natural-categories label { display: inline-flex; align-items: center; gap: 5px; margin: 0; font-size: 11px; }
.natural-categories input { accent-color: #286b60; }
:global(html[data-theme='dark'] .natural-analysis) { --nl-ink: #e9f6f2; --nl-muted: #9db8b8; --nl-input: #14202c; --nl-border: #365453; --nl-soft: #203d42; }
</style>
