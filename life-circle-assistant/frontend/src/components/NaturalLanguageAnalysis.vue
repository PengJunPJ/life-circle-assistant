<template>
  <section class="natural-analysis" aria-label="一句话填写体检参数">
    <label for="analysis-message">描述地点、步行时间和关注设施</label>
    <textarea id="analysis-message" v-model="message" rows="3" maxlength="1000" :disabled="busy || disabled"
      placeholder="例如：当前选点，20分钟，买菜和买药"
      @keydown.ctrl.enter.prevent="send" @keydown.meta.enter.prevent="send" />
    <div class="natural-input-actions">
      <button type="button" :disabled="busy || disabled" @click="message = '当前选点，20分钟，买菜和买药'">试试示例</button>
      <button class="natural-send" type="button" :disabled="busy || disabled || !message.trim()" @click="send">{{ busy ? '正在填写…' : '填入参数' }}</button>
    </div>
    <p v-if="error" class="location-error" role="alert">{{ error }}</p>
    <p v-else-if="parsed && !pending" class="natural-filled" role="status">✓ 已填入，可继续修改下方参数</p>
    <p v-else class="natural-note">{{ pending ? '描述尚未填入，请先点击“填入参数”。' : '未提及的设置沿用下方参数，填写后由你确认启动。' }}</p>
    <details v-if="parsed" class="natural-details"><summary>解析说明</summary><p>{{ parserLabel }} · {{ parsed.message }}</p></details>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { parseAnalysisIntent } from '../services/analysisApi'
import type { AnalysisIntent, IntentDraft } from '../types/analysisIntent'
const props = defineProps<{ previous: IntentDraft; disabled: boolean }>()
const emit = defineEmits<{ fill: [intent: AnalysisIntent]; 'update:blocked': [blocked: boolean]; 'update:busy': [busy: boolean] }>()
const message = ref('')
const appliedMessage = ref('')
const parsed = ref<AnalysisIntent | null>(null)
const busy = ref(false)
const error = ref('')
const pending = computed(() => Boolean(message.value.trim() && message.value.trim() !== appliedMessage.value))
watch(() => busy.value || pending.value || Boolean(error.value), value => emit('update:blocked', value), { immediate: true })
watch(busy, value => emit('update:busy', value))
const parserLabel = computed(() => parsed.value?.parser === 'llm' ? '智能解析' : parsed.value?.parser === 'rules_degraded' ? '规则解析（智能服务暂不可用）' : '规则解析')
async function send() {
  if (busy.value || props.disabled || !message.value.trim()) return
  busy.value = true
  error.value = ''
  const description = message.value.trim()
  try {
    // 每次解析都以当前公共表单为基础，保留用户在两次描述之间做的修改。
    const result = await parseAnalysisIntent(description, { ...props.previous, categories: [...props.previous.categories] })
    parsed.value = result
    appliedMessage.value = description
    emit('fill', result)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '需求填写失败，请重试。'
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.natural-analysis { --nl-ink: #294b4c; --nl-muted: #637572; --nl-input: #fff; --nl-border: #cddbd4; --nl-soft: #edf6f1; color: var(--nl-ink); }
.natural-analysis > label { display: block; margin: 0 0 8px; color: var(--nl-muted); font-size: 11px; }
.natural-analysis textarea { display: block; width: 100%; min-width: 0; min-height: 76px; max-height: 180px; padding: 9px; border: 1px solid var(--nl-border); border-radius: 6px; background: var(--nl-input); color: var(--nl-ink); font: inherit; font-size: 12px; line-height: 1.6; resize: vertical; }
.natural-analysis textarea:focus-visible { outline: 2px solid #3b9a7d; outline-offset: 2px; }
.natural-input-actions { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 8px; }
.natural-input-actions button { min-height: 30px; padding: 5px 9px; border-radius: 5px; font-size: 11px; color: var(--nl-ink); background: var(--nl-soft); }
.natural-input-actions .natural-send { background: #286b60; color: #fff; font-weight: 700; }
.natural-analysis button:disabled { opacity: .55; cursor: not-allowed; }
.natural-note, .natural-filled, .natural-details { margin: 8px 0 0; font-size: 10px; line-height: 1.6; color: var(--nl-muted); overflow-wrap: anywhere; }
.natural-filled { color: #287666; }
.natural-details summary { cursor: pointer; }
.natural-details p { margin: 5px 0 0; }
:global(html[data-theme='dark'] .natural-analysis) { --nl-ink: #e9f6f2; --nl-muted: #9db8b8; --nl-input: #14202c; --nl-border: #365453; --nl-soft: #203d42; }
:global(html[data-theme='dark'] .natural-filled) { color: #8ccdb7; }
</style>
