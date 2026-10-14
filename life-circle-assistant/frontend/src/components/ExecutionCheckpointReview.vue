<template>
  <details class="checkpoint-review">
    <summary>未决调用与计费核对</summary>
    <p>检查执行 {{ executionId }} 的中断调用。先核对提供方账单和日志，再逐项授权重试；续算仍使用原预算，可能再次计费。</p>
    <button type="button" :disabled="busy" @click="refresh">检查未决调用</button>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p>
    <template v-if="loaded">
      <p v-if="!items.length">当前没有需要人工核对的未决调用。</p>
      <div v-if="items.length" class="checkpoint-fields"><label>计费复核人<input v-model="reviewer" maxlength="120" /></label><label>账单与日志核对依据<textarea v-model="evidence" rows="2" maxlength="2000" placeholder="填写提供方请求编号、日志或账单核对结果" /></label></div>
      <article v-for="item in items" :key="item.call_key"><strong>{{ item.operation }}</strong><p>{{ item.updated_at }}</p><code>{{ item.call_key }}</code><label class="checkpoint-consent"><input v-model="consents[item.call_key]" type="checkbox" />已核对本次调用，允许可能再次计费的重试</label><button type="button" :disabled="busy || !reviewer.trim() || !evidence.trim() || !consents[item.call_key]" @click="authorize(item.call_key)">记录核对并授权本项重试</button></article>
      <button v-if="allowResume" type="button" :disabled="busy || items.length > 0" @click="emit('resume')">从原任务断点续算</button>
    </template>
  </details>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { authorizeCheckpointRetry, fetchUncertainCheckpoints, type UncertainCheckpoint } from '../services/executionApi'
const props = defineProps<{ executionId: string; allowResume?: boolean }>()
const emit = defineEmits<{ resume: [] }>()
const items = ref<UncertainCheckpoint[]>([]), loaded = ref(false), busy = ref(false), error = ref(''), notice = ref(''), reviewer = ref(''), evidence = ref(''), consents = ref<Record<string, boolean>>({})
async function load(id: string) { const result = await fetchUncertainCheckpoints(id); if (id === props.executionId) { items.value = result.items; loaded.value = true } }
async function execute(operation: (id: string) => Promise<void>) {
  if (busy.value) return
  const id = props.executionId
  busy.value = true; error.value = ''; notice.value = ''
  try { await operation(id) } catch (cause) { if (id === props.executionId) error.value = cause instanceof Error ? cause.message : '核对失败' } finally { busy.value = false }
}
const refresh = () => execute(load)
const authorize = (key: string) => execute(async id => {
  if (!loaded.value || !items.value.some(item => item.call_key === key) || !consents.value[key] || !reviewer.value.trim() || !evidence.value.trim()) return
  const result = await authorizeCheckpointRetry(id, key, reviewer.value.trim(), evidence.value.trim())
  if (result.status !== 'retry_authorized') throw new Error('调用尚未获得重试授权')
  await load(id)
  if (id === props.executionId) { notice.value = result.disclosure; consents.value[key] = false }
})
watch(() => props.executionId, () => { items.value = []; loaded.value = false; error.value = ''; notice.value = ''; reviewer.value = ''; evidence.value = ''; consents.value = {} })
</script>

<style scoped>
.checkpoint-review { margin: 9px 12px; font-size: 10px; line-height: 1.65; overflow-wrap: anywhere; }.checkpoint-review summary { cursor: pointer; }.checkpoint-review button { margin: 5px 0; padding: 5px 7px; border: 1px solid #cbdcd3; border-radius: 5px; color: inherit; background: transparent; font: inherit; }.checkpoint-review button:disabled { opacity: .45; }.checkpoint-fields { display: grid; gap: 6px; }.checkpoint-review label { display: grid; gap: 3px; }.checkpoint-review input:not([type="checkbox"]), .checkpoint-review textarea { width: 100%; box-sizing: border-box; border: 1px solid #cbdcd3; border-radius: 4px; padding: 6px; color: inherit; background: transparent; font: inherit; }.checkpoint-review article { padding: 9px 0; border-top: 1px solid #cbdcd3; }.checkpoint-review .checkpoint-consent { display: flex; align-items: center; margin: 6px 0; }.checkpoint-review p[role="alert"] { color: #b45536; }
</style>
