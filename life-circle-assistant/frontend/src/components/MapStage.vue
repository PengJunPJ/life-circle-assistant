<template>
  <section class="map-stage">
    <div class="map-toolbar"><div class="layer-status"><span class="legend-item"><span class="legend-origin"></span>起点</span><span class="legend-item"><span class="legend-isochrone"></span>{{ minutes }}分钟等时圈</span><span class="legend-item"><span class="status-dot red"></span>重点盲区</span><span class="legend-item"><span class="status-dot amber"></span>稀疏区</span></div><button class="icon-btn" title="刷新分析" @click="emit('refresh')"><Refresh /></button></div>
    <div class="facility-legend"><span v-for="category in Object.keys(FACILITY_LABELS)" :key="category" class="facility-legend-item"><b :style="{ background: categoryColor(category) }">{{ categoryShort(category) }}</b>{{ FACILITY_LABELS[category] }}</span></div>
    <div ref="mapContainer" class="map-container" :class="{ hidden: !realMapReady }"></div><canvas ref="mapCanvas" class="map-canvas" :class="{ hidden: realMapReady }"></canvas>
    <div class="map-scale"><span>0</span><span class="scale-line"></span><span>500m</span></div>
    <div v-if="loading" class="map-loading"><div class="loader-ring"></div><strong>正在生成生活圈体检</strong><span>正在计算真实步行可达性… {{ progress }}%</span></div>
    <div class="map-caption"><span class="caption-kicker">分析区域</span><strong>广州市黄埔区 · 萝岗街道</strong><span>中心点周边 1 公里</span></div>
  </section>
</template>

<script setup lang="ts">
import { toRef, watch } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { FACILITY_LABELS, categoryColor, categoryShort } from '../constants/facilities'
import { useMapRenderer } from '../composables/useMapRenderer'
import type { Report } from '../types/report'

const props = defineProps<{ report: Report | null; minutes: 10 | 15 | 20; visibleCategories: string[]; showSparse: boolean; loading: boolean; progress: number }>()
const emit = defineEmits<{ refresh: [] ; 'map-ready': [value: boolean] }>()
const report = toRef(props, 'report')
const visibleCategories = toRef(props, 'visibleCategories')
const showSparse = toRef(props, 'showSparse')
const { mapCanvas, mapContainer, realMapReady, mapLoadComplete } = useMapRenderer({ report, visibleCategories, showSparse })

watch(mapLoadComplete, (value) => { if (value) emit('map-ready', realMapReady.value) }, { immediate: true })
</script>
