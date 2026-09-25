<template>
  <Transition name="map-hover-card">
    <div
      v-if="target"
      ref="cardRef"
      class="map-hover-card"
      :class="[`st-${status}`, { below: below }]"
      :style="cardStyle"
      role="tooltip"
      :aria-label="`${target.poi.name} 步行 ${target.poi.walk_minutes ?? '无'} 分钟`"
      @mouseenter="emit('retain')"
      @mouseleave="emit('release')"
    >
      <div class="hc-head">
        <span class="hc-chip" :style="{ background: categoryColor(target.poi.category) }" aria-hidden="true">{{ categoryShort(target.poi.category) }}</span>
        <span class="hc-cat">{{ FACILITY_LABELS[target.poi.category] || target.poi.category }}</span>
      </div>
      <span class="hc-name">{{ target.poi.name }}</span>
      <div class="hc-hero">
        <span class="num">{{ target.poi.walk_minutes ?? '—' }}</span>
        <span class="unit">分钟步行</span>
        <span class="hc-badge">{{ badgeText }}</span>
      </div>
      <div class="hc-sub">
        <div class="hc-row"><span class="k">步行距离</span><span class="v">{{ distanceText }}</span></div>
        <div class="hc-row"><span class="k">语义类型</span><span class="v">{{ semanticText }}</span></div>
      </div>
      <div class="hc-foot"><span class="hc-dot" aria-hidden="true"></span>数据来源：{{ sourceText }}<template v-if="confidenceText"> · 置信度 {{ confidenceText }}</template></div>
      <button
        class="hc-route-btn"
        type="button"
        :disabled="!routeAvailable || routeLoading"
        :title="routeAvailable ? '在地图上显示起点到该设施的步行路线' : '当前为快照/降级模式，无真实步行路径'"
        @click.stop="routeActive ? emit('hide-route') : emit('show-route', target.poi)"
      >{{ routeLoading ? '路线请求中…' : routeActive ? '隐藏步行路线' : '显示步行路线' }}</button>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { FACILITY_LABELS, categoryColor, categoryShort } from '../constants/facilities'
import type { MapHoverTarget } from '../composables/useMapRenderer'
import type { Poi } from '../types/report'

const props = defineProps<{ target: MapHoverTarget | null; minutes: number; routeAvailable: boolean; routeLoading: boolean; routeActive: boolean }>()
const emit = defineEmits<{ 'show-route': [poi: Poi]; 'hide-route': []; retain: []; release: [] }>()

const cardRef = ref<HTMLElement | null>(null)
const left = ref(0)
const top = ref(0)
const below = ref(false)
const pointerX = ref(116)

const cardStyle = computed(() => ({
  left: `${left.value}px`,
  top: `${top.value}px`,
  '--pointer-x': `${pointerX.value}px`,
}))

const status = computed<'ok' | 'warn' | 'bad' | 'none'>(() => {
  const minutes = props.target?.poi.walk_minutes
  if (minutes === null || minutes === undefined) return 'none'
  if (minutes <= props.minutes * 0.8) return 'ok'
  if (minutes <= props.minutes) return 'warn'
  return 'bad'
})

const badgeText = computed(() => {
  switch (status.value) {
    case 'ok': return `${props.minutes}分钟内`
    case 'warn': return '接近上限'
    case 'bad': return `超出${props.minutes}分钟`
    default: return '无步行数据'
  }
})

const distanceText = computed(() => {
  const meters = props.target?.poi.walk_distance_m
  return meters === null || meters === undefined ? '无有效结果' : `${meters} 米`
})

const semanticText = computed(() => props.target?.poi.semantic_type_label || props.target?.poi.semantic_type || '—')

const sourceText = computed(() => {
  const labels: Record<string, string> = {
    real_api: '真实 API', cache: '有效缓存', local_snapshot: '本地快照',
    interpolation: '空间插值', degraded_estimate: '降级估算',
  }
  const raw = props.target?.poi.source || props.target?.poi.calculation_method || ''
  return labels[raw] || raw || '—'
})

const confidenceText = computed(() => {
  const confidence = props.target?.poi.normalization?.confidence
  return confidence ? { high: '高', medium: '中', low: '低' }[confidence] : ''
})

function place() {
  const card = cardRef.value
  const stage = card?.parentElement
  if (!card || !stage || !props.target) return
  const width = card.offsetWidth
  const height = card.offsetHeight
  const stageWidth = stage.clientWidth
  const stageHeight = stage.clientHeight
  let hudLeft = 0
  let hudRight = 0
  const workspace = stage.closest('.workspace')
  if (workspace && !window.matchMedia('(max-width: 820px)').matches) {
    const computedStyle = getComputedStyle(workspace)
    hudLeft = parseFloat(computedStyle.getPropertyValue('--hud-left')) || 0
    hudRight = parseFloat(computedStyle.getPropertyValue('--hud-right')) || 0
  }
  const margin = 8
  const gap = 16
  const anchorX = props.target.x
  const anchorY = props.target.y
  const minX = hudLeft + margin
  const maxX = stageWidth - hudRight - margin
  // 水平方向以锚点居中，再夹进两侧面板之间的可见带
  let nextLeft = anchorX - width / 2
  nextLeft = Math.min(Math.max(nextLeft, minX), Math.max(maxX - width, minX))
  // 默认显示在锚点正上方；上方空间不足才翻到下方
  let nextBelow = false
  let nextTop = anchorY - gap - height
  if (nextTop < margin) { nextTop = anchorY + gap; nextBelow = true }
  nextTop = Math.min(Math.max(nextTop, margin), Math.max(stageHeight - height - margin, margin))
  left.value = nextLeft
  top.value = nextTop
  below.value = nextBelow
  pointerX.value = Math.min(Math.max(anchorX - nextLeft, 12), width - 12)
}

watch(() => props.target, async (value) => {
  if (!value) return
  await nextTick()
  place()
}, { immediate: true })

function onResize() { place() }
window.addEventListener('resize', onResize)
onBeforeUnmount(() => window.removeEventListener('resize', onResize))
</script>
