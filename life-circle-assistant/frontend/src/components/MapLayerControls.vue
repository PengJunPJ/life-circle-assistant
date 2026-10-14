<template>
  <div ref="root" class="map-layer-controls" @keydown.esc.stop.prevent="close(true)">
    <button ref="trigger" class="map-layer-trigger" type="button" aria-controls="map-layer-menu" :aria-expanded="open" @click="open = !open"><Operation />图层</button>
    <section v-if="open" id="map-layer-menu" class="map-layer-menu layer-panel" aria-label="地图显示设置">
      <div class="layer-section-title"><div><label>地图设施展示</label><small>{{ report ? `已体检 ${available.length} 类；仅改变地图显示` : '生成报告后可设置设施展示' }}</small></div><button class="layer-menu-close" type="button" aria-label="关闭地图显示设置" @click="close(true)">×</button></div>
      <div class="facility-selection-actions" role="group" aria-label="地图设施快捷选择"><button type="button" :disabled="loading || !available.length || displayedCount === available.length" @click="emit('update:visibleCategories', [...available])">全选展示</button><button type="button" :disabled="loading || !displayedCount" @click="emit('update:visibleCategories', [])">全部隐藏</button></div>
      <div class="facility-list layer-facility-list"><button v-for="category in ALL_CATEGORIES" :key="category" type="button" :class="['facility-toggle', { selected: isDisplayed(category), unanalyzed: !available.includes(category) }]" :style="{ '--facility-color': categoryColor(category) }" :disabled="loading || !available.includes(category)" :aria-pressed="isDisplayed(category)" :aria-label="`${FACILITY_LABELS[category]}${available.includes(category) ? '' : '，未体检，补充体检后可展示'}`" @click="toggle(category)"><span class="facility-icon" :style="{ background: categoryColor(category) }" aria-hidden="true">{{ FACILITY_ICONS[category] }}</span><span class="facility-copy"><span class="facility-name">{{ FACILITY_LABELS[category] }}</span><small v-if="!available.includes(category)" class="facility-unavailable">未体检</small></span><span class="check" aria-hidden="true">{{ isDisplayed(category) ? '✓' : '' }}</span></button></div>
      <button v-if="report && available.length < ALL_CATEGORIES.length" class="prepare-supplement" type="button" :disabled="loading" @click="emit('prepare-supplement'); close()">补充未体检设施 →</button>
      <div class="coverage-list" aria-label="服务区域状态图层">
        <div v-for="layer in coverageLayers" :key="layer.key" class="coverage-item" :class="{ active: layer.value }"><span class="coverage-swatch" :class="layer.key" aria-hidden="true"></span><span class="coverage-copy"><strong>{{ layer.label }}</strong></span><el-switch :aria-label="`显示${layer.label}`" :model-value="layer.value" @update:model-value="updateCoverage(layer.key, $event)" /></div>
      </div>
      <div class="coverage-list" aria-label="独立空间证据图层"><label v-for="layer in evidenceLayers" :key="layer.key" class="coverage-item"><input type="checkbox" :checked="statusLayers?.[layer.key] ?? false" :disabled="!report" @change="emit('update:statusLayers', { [layer.key]: ($event.target as HTMLInputElement).checked })" /><span class="coverage-copy"><strong>{{ layer.label }}</strong></span></label></div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Operation } from '@element-plus/icons-vue'
import { ALL_CATEGORIES, FACILITY_ICONS, FACILITY_LABELS, categoryColor } from '../constants/facilities'
import type { Report } from '../types/report'
import type { StatusLayers } from '../types/completion'
const props = defineProps<{ report: Report | null; visibleCategories: string[]; loading: boolean; showNormal: boolean; showSparse: boolean; showCritical: boolean; statusLayers?: StatusLayers }>()
const emit = defineEmits<{ 'update:visibleCategories': [categories: string[]]; 'update:showNormal': [value: boolean]; 'update:showSparse': [value: boolean]; 'update:showCritical': [value: boolean]; 'update:statusLayers': [layers: Partial<StatusLayers>]; 'prepare-supplement': [] }>()
const evidenceLayers = [{ key: 'scarcity', label: '1公里设施稀缺' }, { key: 'walking_timeout', label: '已核验步行超时' }, { key: 'gap_groups', label: '缺口连通片区' }, { key: 'sampling', label: '观测 / 估计 / 未决时间场' }, { key: 'unknown', label: '证据不足区域' }] as const
const open = ref(false)
const root = ref<HTMLElement | null>(null)
const trigger = ref<HTMLButtonElement | null>(null)
const available = computed(() => ALL_CATEGORIES.filter(category => props.report?.parameters?.categories.includes(category)))
const isDisplayed = (category: string) => available.value.includes(category) && props.visibleCategories.includes(category)
const displayedCount = computed(() => available.value.filter(isDisplayed).length)
const coverageLayers = computed(() => [
  { key: 'normal' as const, label: '正常覆盖区', value: props.showNormal },
  { key: 'sparse' as const, label: '设施稀疏区', value: props.showSparse },
  { key: 'critical' as const, label: '重点服务盲区', value: props.showCritical },
])
function toggle(category: string) { emit('update:visibleCategories', props.visibleCategories.includes(category) ? props.visibleCategories.filter(item => item !== category) : [...props.visibleCategories, category]) }
function updateCoverage(key: 'normal' | 'sparse' | 'critical', value: string | number | boolean) {
  const enabled = Boolean(value)
  if (key === 'normal') emit('update:showNormal', enabled)
  else if (key === 'sparse') emit('update:showSparse', enabled)
  else emit('update:showCritical', enabled)
}
function close(restoreFocus = false) { open.value = false; if (restoreFocus) trigger.value?.focus() }
function handleOutside(event: PointerEvent) { if (open.value && !root.value?.contains(event.target as Node)) close() }
onMounted(() => document.addEventListener('pointerdown', handleOutside))
onBeforeUnmount(() => document.removeEventListener('pointerdown', handleOutside))
</script>
