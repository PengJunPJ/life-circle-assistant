<template>
  <section class="ai-assistant" aria-labelledby="ai-assistant-title">
    <div class="section-title"><span id="ai-assistant-title">可解释 AI 规划助手</span><small>{{ result?.model || '规则模板' }}</small></div>
    <p class="ai-boundary">基于当前体检报告生成解读；不会修改原始评分、路线和设施数据。</p>
    <div class="ai-actions">
      <button type="button" :disabled="loading" @click="run({ intent: 'summary' })">体检摘要</button>
      <button type="button" :disabled="loading" @click="run({ intent: 'priority' })">类别优先级</button>
      <button type="button" :disabled="loading" @click="run({ intent: 'simulation' })">候选设施模拟</button>
      <button type="button" :disabled="loading" @click="run({ intent: 'brief' })">汇报摘要</button>
    </div>
    <div class="ai-question"><input v-model="question" aria-label="向规划助手提问" placeholder="例如：为什么这里被判定为重点服务盲区？" @keydown.enter="ask(question)" /><button type="button" :disabled="loading || !question.trim()" @click="ask(question)">提问</button></div>
    <div v-if="loading" class="ai-state" role="status">正在整理本次报告的证据…</div>
    <div v-else-if="error" class="ai-state error" role="alert">{{ error }}</div>
    <div v-else-if="result" class="ai-result" aria-live="polite">
      <div class="ai-mode"><span>生成方式</span><strong>{{ result.model }}</strong><small>{{ intentLabel(result.intent) }} · {{ result.prompt_version }}</small></div>
      <p class="ai-summary">{{ result.summary }}</p>
      <div v-if="result.recommendations.length" class="ai-recommendations"><div v-for="item in result.recommendations" :key="item.title" class="ai-recommendation"><div><strong>{{ item.title }}</strong><span :class="`ai-priority ${item.priority}`">{{ priorityLabel(item.priority) }}</span></div><p>{{ item.text }}</p></div></div>
      <details class="ai-evidence"><summary>查看证据引用（{{ result.evidence_refs.length }}）</summary><ul><li v-for="ref in result.evidence_refs" :key="`${ref.type}-${ref.id}`"><strong>{{ ref.label }}</strong><span>{{ ref.detail }}</span><small>{{ ref.type }} · {{ ref.id }}</small></li></ul></details>
      <p class="ai-quality">{{ result.data_quality_notice }}</p><small class="ai-generated">生成于 {{ formatDate(result.generated_at) }}</small>
    </div>
    <div v-else class="ai-empty">完成分析后，可生成基于报告证据的摘要、类别优先级、模拟解读与汇报摘要。</div>
  </section>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { fetchReportInterpretations, interpretReport } from '../services/analysisApi'
import type { AiInterpretation, AiInterpretationIntent, Report } from '../types/report'
const props = defineProps<{ report: Report }>()
const result = ref<AiInterpretation | null>(null)
const loading = ref(false)
const error = ref('')
const question = ref('')
watch(() => props.report.report_id, async () => {
  result.value = null; error.value = ''; question.value = ''
  try { result.value = (await fetchReportInterpretations(props.report.report_id)).items[0] || null } catch { /* 历史解读不存在时保持空状态 */ }
}, { immediate: true })
async function run(params: { intent: AiInterpretationIntent; grid_id?: string; category?: string; simulation_id?: string; question?: string }) {
  loading.value = true; error.value = ''
  try { result.value = await interpretReport(props.report.report_id, params) }
  catch (err) { error.value = err instanceof Error ? err.message : 'AI 解读生成失败' }
  finally { loading.value = false }
}
function ask(value: string) { if (!value.trim()) return; return run({ intent: 'ask', question: value.trim() }) }
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
.ai-assistant { margin-top: 17px; padding-top: 16px; border-top: 1px solid #e2e9e4; }.ai-boundary { margin: 8px 0; color: #7f908b; font-size: 9px; line-height: 1.45; }.ai-actions { display: flex; flex-wrap: wrap; gap: 5px; }.ai-actions button, .ai-question button { padding: 6px 8px; border: 1px solid #c9ddd3; border-radius: 4px; background: #f1f8f4; color: #397568; font-size: 9px; }.ai-actions button:hover, .ai-question button:hover { background: #e2f1ea; }.ai-actions button:disabled, .ai-question button:disabled { opacity: .55; cursor: wait; }.ai-question { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 5px; margin-top: 7px; }.ai-question input { min-width: 0; height: 29px; padding: 0 7px; border: 1px solid #cedbd5; border-radius: 4px; color: #294b4c; font-size: 9px; }.ai-state, .ai-empty { margin-top: 9px; padding: 9px; border-radius: 4px; background: #f0f5f2; color: #72837e; font-size: 9px; line-height: 1.5; }.ai-state.error { background: #f7e8e3; color: #a1503d; }.ai-result { margin-top: 10px; padding: 10px; border: 1px solid #d6e4dc; border-left: 3px solid #4a9a82; border-radius: 4px; background: #fbfdfb; }.ai-mode { display: flex; align-items: baseline; gap: 7px; color: #72837e; font-size: 8px; }.ai-mode strong { color: #347563; font-size: 10px; }.ai-mode small { margin-left: auto; color: #9aa5a5; }.ai-summary { margin: 9px 0; color: #36564f; font-size: 11px; line-height: 1.55; }.ai-recommendation { padding: 8px 0; border-top: 1px solid #e6eee9; }.ai-recommendation > div { display: flex; align-items: center; justify-content: space-between; gap: 5px; }.ai-recommendation strong { color: #3c5b54; font-size: 10px; }.ai-recommendation p { margin: 4px 0 0; color: #788984; font-size: 9px; line-height: 1.5; }.ai-priority { padding: 2px 5px; border-radius: 8px; background: #e9f2ed; color: #40806d; font-size: 8px; }.ai-priority.high { background: #f6e0da; color: #a34e3b; }.ai-priority.medium { background: #f8edd7; color: #9a702d; }.ai-evidence { margin-top: 8px; color: #47766c; font-size: 9px; }.ai-evidence summary { cursor: pointer; font-weight: 700; }.ai-evidence ul { display: grid; gap: 5px; margin: 7px 0 0; padding-left: 15px; color: #6c7e78; }.ai-evidence li { line-height: 1.4; }.ai-evidence li strong, .ai-evidence li span, .ai-evidence li small { display: block; }.ai-evidence li strong { color: #41685f; }.ai-evidence li small { color: #9aa8a3; }.ai-quality { margin: 8px 0 0; color: #92723d; font-size: 8px; line-height: 1.45; }.ai-generated { display: block; margin-top: 6px; color: #a0ada8; font-size: 8px; }
</style>
