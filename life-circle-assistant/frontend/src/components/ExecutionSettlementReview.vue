<template>
  <details class="settlement-review">
    <summary>人工账单结算与历史</summary>
    <p>仅在执行结束后，录入已人工核验的提供方账单中本次执行全部费用。估算金额不能作为结算依据；复核人姓名仅作为审计记录，不代表身份认证。</p>
    <button type="button" :disabled="busy" @click="refresh">读取账本与结算历史</button>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p>
    <template v-if="ledger">
      <p>当前执行：{{ statusLabel }} · 结算版本 {{ ledger.cost.settlement_version ?? '未知' }}</p>
      <p v-if="ledger.cost.settlement_stale || ledger.cost.status === 'settlement_stale'" class="settlement-stale">旧结算已过时：执行恢复或用量变化后，原金额不代表本次执行全部费用，请重新核对账单。</p>
      <p v-else-if="ledger.cost.status === 'manually_reconciled'">已记录人工结算：{{ ledger.cost.settled_total }} CNY</p>
      <p v-else>当前只有估算，尚未记录人工结算。</p>
      <p v-if="!terminal">执行尚未结束，暂不能录入结算。</p>
      <p v-if="!ready">请重新读取账本并核对最新版本与用量后录入。</p>
      <p v-if="ready && !validRevision" role="alert">账本缺少有效结算版本或用量指纹，不能录入；请确认服务已升级并重新读取。</p>
      <form class="settlement-fields" @submit.prevent="save">
        <label>本次执行全部费用（人民币元）<input v-model="amount" type="text" inputmode="decimal" maxlength="16" autocomplete="off" placeholder="人工填写账单金额，可为0" :disabled="busy || !ready || !terminal" /></label>
        <p v-if="amount && !validAmount" role="alert">金额须为有限非负人民币数值，最多两位小数且不超过999999999999.99元。</p>
        <label>提供方账单编号或引用<input v-model="billReference" maxlength="500" :disabled="busy || !ready || !terminal" /></label>
        <label>结算复核人<input v-model="reviewer" maxlength="120" :disabled="busy || !ready || !terminal" /></label>
        <label>全部费用核验依据<textarea v-model="evidence" rows="3" maxlength="2000" placeholder="填写提供方账单、用量归属及全部费用核验依据；零金额也需要依据" :disabled="busy || !ready || !terminal" /></label>
        <label class="settlement-consent"><input v-model="confirmed" type="checkbox" :disabled="busy || !ready || !terminal" />已人工核验提供方账单，金额覆盖本次执行全部费用</label>
        <button type="submit" :disabled="busy || !canSubmit">记录人工结算</button>
      </form>
      <div class="settlement-history" aria-label="结算审计历史"><p v-if="!items.length">没有结算历史。</p><article v-for="item in items" :key="item.version"><strong>版本 {{ item.version }} · {{ item.amount_cny }} {{ item.currency }}</strong><p>{{ item.created_at }} · {{ item.reviewer }}</p><p>账单：{{ item.bill_reference }}</p><p>依据：{{ item.evidence }}</p><p>范围：本次执行全部费用</p><details><summary>核验时的用量指纹</summary><code>{{ item.usage_sha256 }}</code></details></article></div>
    </template>
  </details>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { fetchExecutionLedger, fetchExecutionSettlements, recordExecutionSettlement, type ExecutionSettlement } from '../services/executionApi'
import type { ExecutionLedger } from '../types/report'
const props = defineProps<{ executionId: string }>()
const emit = defineEmits<{ ledger: [ledger: ExecutionLedger] }>()
const ledger = ref<ExecutionLedger | null>(null), items = ref<ExecutionSettlement[]>([]), busy = ref(false), ready = ref(false), error = ref(''), notice = ref('')
const amount = ref(''), billReference = ref(''), reviewer = ref(''), evidence = ref(''), confirmed = ref(false)
let generation = 0
const terminal = computed(() => ['completed', 'failed', 'cancelled', 'interrupted'].includes(ledger.value?.status || ''))
const statusLabels: Record<string, string> = { completed: '已完成', failed: '失败', cancelled: '已取消', interrupted: '已中断', running: '运行中', queued: '等待执行' }
const statusLabel = computed(() => statusLabels[ledger.value?.status || ''] || '尚未结束或状态未知')
const validAmount = computed(() => /^\d+(?:\.\d{1,2})?$/.test(amount.value.trim()) && Number.isFinite(Number(amount.value)) && Number(amount.value) >= 0 && Number(amount.value) <= 999999999999.99)
const validRevision = computed(() => Number.isInteger(ledger.value?.cost.settlement_version) && (ledger.value?.cost.settlement_version ?? -1) >= 0 && /^[0-9a-f]{64}$/.test(ledger.value?.cost.usage_sha256 || ''))
const canSubmit = computed(() => ready.value && terminal.value && validRevision.value && validAmount.value && !!billReference.value.trim() && !!reviewer.value.trim() && !!evidence.value.trim() && confirmed.value)
async function load(id: string, token: number) {
  const [latest, history] = await Promise.all([fetchExecutionLedger(id), fetchExecutionSettlements(id)])
  if (token !== generation || id !== props.executionId) return
  if (latest.id !== id) throw new Error('账本与当前执行不一致，请重新读取')
  ledger.value = latest; items.value = history.items; emit('ledger', latest)
  const historyVersion = history.items.reduce((version, item) => Math.max(version, item.version), 0)
  if (latest.cost.settlement_version !== historyVersion) throw new Error('结算历史与账本版本已变化，请重新读取并核验')
  ready.value = true
}
async function execute(operation: (id: string, token: number) => Promise<void>) {
  if (busy.value) return
  const id = props.executionId, token = generation
  busy.value = true; ready.value = false; error.value = ''; notice.value = ''
  try { await operation(id, token) } catch (cause) { if (token === generation && id === props.executionId) { error.value = cause instanceof Error ? cause.message : '账单核验失败，请重新读取账本'; ready.value = false } } finally { if (token === generation) { busy.value = false; confirmed.value = false } }
}
const refresh = () => execute(load)
const save = () => {
  if (busy.value || !canSubmit.value || !ledger.value) return
  const input = { amount_cny: amount.value.trim(), bill_reference: billReference.value.trim(), reviewer: reviewer.value.trim(), evidence: evidence.value.trim(), expected_version: ledger.value.cost.settlement_version!, expected_usage_sha256: ledger.value.cost.usage_sha256!, scope: 'execution_total' as const }
  return execute(async (id, token) => {
    await recordExecutionSettlement(id, input)
    if (token !== generation || id !== props.executionId) return
    amount.value = ''; billReference.value = ''; evidence.value = ''; confirmed.value = false
    try { await load(id, token) } catch (cause) { throw Object.assign(new Error(`结算已记录，但最新账本未能确认，请重新读取后再操作：${cause instanceof Error ? cause.message : '刷新失败'}`), { cause }) }
    if (token === generation && id === props.executionId) notice.value = '已记录人工结算，账本与历史已刷新。'
  })
}
watch([amount, billReference, reviewer, evidence], () => { confirmed.value = false })
watch(() => props.executionId, () => { generation += 1; ledger.value = null; items.value = []; busy.value = false; ready.value = false; error.value = ''; notice.value = ''; amount.value = ''; billReference.value = ''; reviewer.value = ''; evidence.value = ''; confirmed.value = false })
onBeforeUnmount(() => { generation += 1 })
</script>

<style scoped>
.settlement-review { margin-top: 12px; font-size: 11px; line-height: 1.65; overflow-wrap: anywhere; }.settlement-review summary { cursor: pointer; }.settlement-review button { margin: 5px 0; padding: 6px 8px; border: 1px solid #cbdcd3; border-radius: 5px; color: inherit; background: transparent; font: inherit; }.settlement-review button:disabled { opacity: .45; }.settlement-fields { display: grid; gap: 8px; margin: 12px 0; }.settlement-review label { display: grid; gap: 3px; }.settlement-review input:not([type="checkbox"]), .settlement-review textarea { width: 100%; box-sizing: border-box; border: 1px solid #cbdcd3; border-radius: 4px; padding: 6px; color: inherit; background: transparent; font: inherit; }.settlement-history article { padding: 9px 0; border-top: 1px solid #cbdcd3; }.settlement-review .settlement-consent { display: flex; align-items: flex-start; gap: 6px; }.settlement-review p[role="alert"], .settlement-stale { color: #b45536; }
</style>
