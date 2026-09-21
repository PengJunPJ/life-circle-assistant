<template>
  <section class="quality-details" aria-labelledby="quality-details-title">
    <div class="quality-details-heading">
      <div>
        <strong id="quality-details-title">数据质量说明</strong>
        <span>{{ quality.summary }}</span>
      </div>
      <span :class="['quality-status', quality.overall_status]">{{ statusLabel }}</span>
    </div>

    <div class="quality-source-list">
      <article v-for="source in quality.sources" :key="`${source.kind}-${source.usage}`" class="quality-source">
        <div>
          <strong>{{ source.label }}</strong>
          <span>{{ source.usage }}</span>
        </div>
        <em :class="{ current: source.is_latest_real_measurement }">
          {{ source.is_latest_real_measurement ? '最新真实测算' : '非实时数据' }}
        </em>
      </article>
    </div>

    <div v-if="quality.partial_failures.length" class="quality-failures">
      <strong>部分失败（{{ quality.partial_failures.length }}）</strong>
      <ul>
        <li v-for="(failure, index) in quality.partial_failures" :key="`${failure.code}-${index}`">
          {{ failure.message }}
        </li>
      </ul>
    </div>

    <details v-if="quality.events.length" class="quality-events">
      <summary>查看质量事件（{{ quality.events.length }}）</summary>
      <ul>
        <li v-for="(event, index) in quality.events" :key="`${event.code}-${event.object_ref}-${index}`">
          <span :class="['event-level', event.severity]">{{ event.severity === 'info' ? '信息' : event.severity === 'warning' ? '注意' : '错误' }}</span>
          {{ event.message }}
        </li>
      </ul>
    </details>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { DataQuality } from '../types/quality'

const props = defineProps<{ quality: DataQuality }>()
const statusLabel = computed(() => ({ good: '数据完整', limited: '数据受限', partial: '部分结果' })[props.quality.overall_status])
</script>
