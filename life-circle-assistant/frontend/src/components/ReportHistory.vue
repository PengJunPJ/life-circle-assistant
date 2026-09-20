<template>
  <section class="history-section" aria-labelledby="history-title">
    <div class="section-title history-title">
      <span id="history-title">历史报告</span>
      <button :disabled="loading" @click="emit('refresh')">{{ loading ? '加载中…' : `刷新 · ${total}` }}</button>
    </div>
    <div v-if="loading && !items.length" class="history-state" aria-live="polite">正在加载历史报告…</div>
    <div v-else-if="error" class="history-state error" role="alert">
      <span>{{ error }}</span><button @click="emit('refresh')">重试</button>
    </div>
    <div v-else-if="!items.length" class="history-state">尚无历史报告，完成一次分析后会显示在这里。</div>
    <div v-else class="history-list">
      <article v-for="item in items" :key="item.report_id" class="history-item">
        <button class="history-open" :disabled="Boolean(openingReportId || rerunningReportId)" @click="emit('open', item.report_id)">
          <strong>{{ item.center.address }}</strong>
          <span>{{ formatTime(item.completed_at) }} · {{ item.minutes }} 分钟 · {{ item.mode === 'analysis' ? '分析模式' : '演示模式' }}</span>
        </button>
        <button
          class="history-rerun"
          :disabled="Boolean(openingReportId || rerunningReportId)"
          :aria-label="`使用 ${item.center.address} 的参数重新运行`"
          @click="emit('rerun', item.report_id)"
        >{{ rerunningReportId === item.report_id ? '运行中' : '重跑' }}</button>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { HistoryReportItem } from '../types/history'

defineProps<{
  items: HistoryReportItem[]
  total: number
  loading: boolean
  error: string
  openingReportId: string
  rerunningReportId: string
}>()

const emit = defineEmits<{
  refresh: []
  open: [reportId: string]
  rerun: [reportId: string]
}>()

function formatTime(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  }).format(new Date(value))
}
</script>
