<template>
  <div v-if="areas.length" ref="root" class="service-area-browser" @keydown.esc.stop.prevent="close(true)">
    <button ref="trigger" class="service-area-trigger" type="button" aria-controls="service-area-menu" :aria-expanded="open" @click="setOpen(!open)">
      <Location aria-hidden="true" />
      <strong>区域判定</strong>
      <span>{{ areas.length }} 个可见区域</span>
      <span class="service-area-trigger-action">{{ open ? '收起' : '查看' }}<ArrowUp v-if="open" aria-hidden="true" /><ArrowDown v-else aria-hidden="true" /></span>
    </button>
    <section v-if="open" id="service-area-menu" class="service-area-menu" aria-label="可查看判定依据的服务区域" aria-describedby="service-area-help">
      <header class="service-area-heading"><strong>区域判定</strong><button type="button" aria-label="关闭区域列表" @click="close(true)"><Close aria-hidden="true" /></button></header>
      <p id="service-area-help">每项对应地图上的一个分析网格，点击定位并查看判定依据。仅列出当前显示的区域。</p>
      <div class="service-area-summary" aria-label="当前可见区域分类统计">
        <span v-for="count in kindCounts" :key="count.kind" :class="count.kind">{{ count.label }} <b>{{ count.total }}</b></span>
      </div>
      <div class="service-area-groups">
        <section v-for="group in groups" :key="group.category" class="service-area-group" :aria-label="`${group.label}服务区域`">
          <h3><b :style="{ background: categoryColor(group.category) }" aria-hidden="true">{{ categoryShort(group.category) }}</b>{{ group.label }}<span>{{ group.areas.length }} 个区域</span></h3>
          <button v-for="area in group.areas" :key="area.properties.grid_id" class="service-area-row" type="button" :aria-pressed="selectedId === area.properties.grid_id" :aria-label="`${names.get(area.properties.grid_id)}，${area.properties.label}，定位并查看判定依据`" @click="select(area)">
            <span class="service-area-kind" :class="area.properties.kind" aria-hidden="true">{{ kindSymbols[area.properties.kind] }}</span>
            <span class="service-area-row-copy"><strong>{{ names.get(area.properties.grid_id) }}</strong><small>{{ area.properties.label }}</small></span>
            <span class="service-area-row-action">{{ selectedId === area.properties.grid_id ? '已选中' : '查看依据' }}<ArrowRight aria-hidden="true" /></span>
          </button>
        </section>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ArrowDown, ArrowRight, ArrowUp, Close, Location } from '@element-plus/icons-vue'
import { ALL_CATEGORIES, categoryColor, categoryShort } from '../constants/facilities'
import type { ServiceAreaFeature, ServiceAreaKind } from '../types/report'

const props = defineProps<{ areas: ServiceAreaFeature[]; names: Map<string, string>; selectedId: string | null }>()
const emit = defineEmits<{ select: [area: ServiceAreaFeature]; 'update:open': [value: boolean] }>()
const open = ref(false)
const root = ref<HTMLElement | null>(null)
const trigger = ref<HTMLButtonElement | null>(null)
const kinds: ServiceAreaKind[] = ['critical', 'sparse', 'normal', 'unknown']
const kindLabels = { critical: '重点盲区', sparse: '稀疏区', normal: '正常覆盖', unknown: '待确认' }
const kindSymbols = { critical: '!', sparse: '△', normal: '✓', unknown: '?' }
const kindCounts = computed(() => kinds.map(kind => ({ kind, label: kindLabels[kind], total: props.areas.filter(area => area.properties.kind === kind).length })).filter(count => count.total > 0))
const groups = computed(() => {
  const categories = [...new Set([...ALL_CATEGORIES, ...props.areas.map(area => area.properties.category)])]
  return categories.map(category => {
    const areas = props.areas.filter(area => area.properties.category === category)
      .sort((a, b) => kinds.indexOf(a.properties.kind) - kinds.indexOf(b.properties.kind))
    return { category, label: areas[0]?.properties.category_label || category, areas }
  }).filter(group => group.areas.length > 0)
})

function setOpen(value: boolean) { open.value = value; emit('update:open', value) }
function focusTrigger() { trigger.value?.focus() }
function close(restoreFocus = false) { setOpen(false); if (restoreFocus) focusTrigger() }
function select(area: ServiceAreaFeature) { close(props.selectedId === area.properties.grid_id); emit('select', area) }
function handleOutside(event: PointerEvent) { if (open.value && !root.value?.contains(event.target as Node)) close() }
watch(() => props.names, () => close())
watch(() => props.areas.length, value => { if (!value) close() })
onMounted(() => document.addEventListener('pointerdown', handleOutside))
onBeforeUnmount(() => document.removeEventListener('pointerdown', handleOutside))
defineExpose({ focusTrigger })
</script>
