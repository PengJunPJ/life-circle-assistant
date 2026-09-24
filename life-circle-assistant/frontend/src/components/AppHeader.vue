<template>
  <header class="topbar">
    <div class="brand">
      <div class="brand-mark"><MapLocation /></div>
      <div><strong>生活圈体检</strong><span>COMMUNITY PULSE · 黄埔区样例</span></div>
    </div>
    <div class="topbar-actions">
      <div class="theme-switch" role="group" aria-label="主题切换">
        <button type="button" :class="{ on: theme === 'dark' }" :aria-pressed="theme === 'dark'" title="深色科技风" aria-label="切换到深色科技风" @click="emit('update:theme', 'dark')"><Moon /></button>
        <button type="button" :class="{ on: theme === 'light' }" :aria-pressed="theme === 'light'" title="浅色高级风" aria-label="切换到浅色高级风" @click="emit('update:theme', 'light')"><Sunny /></button>
      </div>
      <div class="topbar-meta">
        <span class="live-dot" :class="{ pending: mapStatusLoading, warning: !mapStatusLoading && !realApiReady }"></span>
        {{ mapStatusLoading ? '正在检测地图服务' : !mapStatusAvailable ? '地图服务未连接' : realApiReady ? '真实百度服务已连接' : '当前为本地快照' }}
        <span class="divider"></span><span>最后分析：{{ hasReport ? '刚刚' : '等待中' }}</span>
      </div>
      <button class="guide-entry" type="button" @click="emit('open-guide')"><QuestionFilled />操作向导</button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { MapLocation, Moon, QuestionFilled, Sunny } from '@element-plus/icons-vue'

defineProps<{ hasReport: boolean; theme: 'dark' | 'light'; mapStatusLoading: boolean; mapStatusAvailable: boolean; realApiReady: boolean }>()
const emit = defineEmits<{ 'open-guide': []; 'update:theme': [value: 'dark' | 'light'] }>()
</script>
