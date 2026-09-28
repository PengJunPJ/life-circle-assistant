<template>
  <section class="history-section" aria-labelledby="history-title">
    <div class="section-title history-title">
      <span id="history-title">历史报告</span>
      <button :disabled="loading" @click="emit('refresh')">{{ loading ? '加载中…' : `刷新 · ${total}` }}</button>
    </div>
    <div class="history-search">
      <input
        type="search"
        class="history-search-input"
        :value="query"
        placeholder="搜索地址关键词…"
        aria-label="搜索历史报告地址"
        @input="emit('search', ($event.target as HTMLInputElement).value)"
      />
      <button
        v-if="query"
        type="button"
        class="history-search-clear"
        aria-label="清除搜索关键词"
        @click="emit('search', '')"
      >×</button>
    </div>
    <div v-if="loading && !items.length" class="history-state" aria-live="polite">正在加载历史报告…</div>
    <div v-else-if="error" class="history-state error" role="alert">
      <span>{{ error }}</span><button @click="emit('refresh')">重试</button>
    </div>
    <div v-else-if="!items.length" class="history-state">
      {{ query ? `没有匹配「${query}」的历史报告` : '尚无历史报告，完成一次分析后会显示在这里。' }}
    </div>
    <div
      v-else
      ref="listRef"
      class="history-list"
      role="list"
      @scroll.passive="handleScroll"
    >
      <article v-for="item in items" :key="item.report_id" class="history-item" role="listitem">
        <button
          class="history-select"
          :class="{ active: selectedReportIds.includes(item.report_id) }"
          :aria-pressed="selectedReportIds.includes(item.report_id)"
          :aria-label="`${selectedReportIds.includes(item.report_id) ? '取消选择' : '选择'} ${item.center.address} 用于比较`"
          @click="emit('toggle-comparison', item.report_id)"
        >{{ selectedReportIds.includes(item.report_id) ? '✓' : '+' }}</button>
        <button class="history-open" :disabled="Boolean(openingReportId || rerunningReportId)" @click="emit('open', item.report_id)">
          <strong>{{ item.center.address }}</strong>
          <span>{{ formatTime(item.completed_at) }} · {{ item.minutes }} 分钟 · {{ item.mode === 'analysis' ? '正式分析' : '快速分析' }}</span>
        </button>
        <button
          class="history-rerun"
          :disabled="Boolean(openingReportId || rerunningReportId)"
          :aria-label="`使用 ${item.center.address} 的参数重新运行`"
          @click="emit('rerun', item.report_id)"
        >{{ rerunningReportId === item.report_id ? '运行中' : '重跑' }}</button>
      </article>
      <div v-if="loadingMore" class="history-load-state" aria-live="polite">加载更多…</div>
      <div v-else-if="hasMore" class="history-load-state muted">滚动加载更多</div>
      <div v-else class="history-load-state muted">已到底部 · 共 {{ total }} 条{{ query ? `（匹配「${query}」）` : '' }}</div>
    </div>
    <div v-if="items.length" class="history-compare-actions">
      <span>已选 {{ selectedReportIds.length }}/2</span>
      <button :disabled="comparisonLoading || selectedReportIds.length !== 2" @click="emit('compare')">
        {{ comparisonLoading ? '比较中…' : '比较已选报告' }}
      </button>
    </div>
    <p v-if="comparisonError" class="history-comparison-error" role="alert">{{ comparisonError }}</p>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { HistoryReportItem } from '../types/history'

defineProps<{
  items: HistoryReportItem[]
  total: number
  loading: boolean
  loadingMore: boolean
  hasMore: boolean
  query: string
  error: string
  openingReportId: string
  rerunningReportId: string
  selectedReportIds: string[]
  comparisonLoading: boolean
  comparisonError: string
}>()

const emit = defineEmits<{
  refresh: []
  open: [reportId: string]
  rerun: [reportId: string]
  'toggle-comparison': [reportId: string]
  compare: []
  search: [keyword: string]
  'load-more': []
}>()

const listRef = ref<HTMLElement | null>(null)
const SCROLL_THRESHOLD_PX = 24

function handleScroll(event: Event) {
  const el = event.target as HTMLElement | null
  if (!el) return
  if (el.scrollTop + el.clientHeight >= el.scrollHeight - SCROLL_THRESHOLD_PX) {
    emit('load-more')
  }
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  }).format(new Date(value))
}
</script>
