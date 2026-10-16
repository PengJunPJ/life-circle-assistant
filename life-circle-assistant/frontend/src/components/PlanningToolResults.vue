<template>
  <ol class="planning-tools" aria-label="实际工具执行记录">
    <li v-for="call in calls" :key="call.id" :class="{ failed: call.status === 'failed' }">
      <div class="tool-heading"><strong>{{ call.label }}</strong><span>{{ call.status === 'completed' ? '已执行' : '失败' }}</span><small>{{ call.duration_ms }} ms</small></div>
      <p v-if="call.error" role="alert">{{ call.error }}</p>
      <template v-if="call.result">
        <p>{{ call.result.summary }}</p>
        <ul v-if="call.result.items?.length" class="tool-items">
          <li v-for="(item, index) in call.result.items" :key="String(item.id || item.grid_id || index)">
            <strong>{{ item.name || item.label || item.grid_id }}</strong>
            <span v-if="item.basis">{{ item.basis }}</span>
            <span v-if="item.walk_minutes !== undefined">从分析中心步行：{{ item.walk_minutes === null ? '结果缺失' : `${item.walk_minutes} 分钟` }}</span>
            <small>{{ item.grid_id || item.id }}<template v-if="item.source"> · {{ item.source }}</template></small>
          </li>
        </ul>
        <p v-if="call.result.simulation?.data_quality.partial_failures.length" class="tool-warning">部分路线计算失败，请结合缺失证据核验改善量。</p>
        <small>数据来源：{{ sourceLabel(call.result.source) }}</small>
      </template>
      <details><summary>调用参数</summary><pre>{{ JSON.stringify(call.arguments, null, 2) }}</pre></details>
    </li>
  </ol>
</template>

<script setup lang="ts">
import type { PlanningToolCall } from '../types/planning'
defineProps<{ calls: PlanningToolCall[] }>()
function sourceLabel(source: string) {
  return ({ report_snapshot: '当前报告快照', real_api: '地图 API', local_snapshot: '本地数据快照', fixture: '模拟数据' } as Record<string, string>)[source] || source
}
</script>

<style scoped>
.planning-tools { margin: 12px 0; padding-left: 20px; color: #52756a; font-size: 10px; }
.planning-tools > li { padding: 9px 0; border-top: 1px solid #d6e4dc; overflow-wrap: anywhere; }
.tool-heading { display: flex; flex-wrap: wrap; align-items: baseline; gap: 7px; }
.tool-heading strong { color: #346b59; }
.tool-heading small { margin-left: auto; }
.planning-tools p { margin: 6px 0; line-height: 1.6; white-space: pre-line; }
.tool-items { display: grid; gap: 7px; padding-left: 12px; margin: 9px 0; }
.tool-items strong, .tool-items span, .tool-items small { display: block; line-height: 1.5; }
.tool-items small { opacity: .7; }
.planning-tools details { margin-top: 6px; }
.planning-tools summary { cursor: pointer; }
.planning-tools pre { max-width: 100%; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 9px; }
.planning-tools .failed, .tool-warning { color: #a15c38; }
html[data-theme="dark"] .planning-tools { color: #9db8b8; }
html[data-theme="dark"] .planning-tools > li { border-color: rgba(126,214,199,.18); }
html[data-theme="dark"] .tool-heading strong { color: #7ff0da; }
html[data-theme="dark"] .planning-tools .failed, html[data-theme="dark"] .tool-warning { color: #ffcf8a; }
</style>
