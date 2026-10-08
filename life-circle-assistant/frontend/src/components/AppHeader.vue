<template>
  <header class="topbar">
    <div class="brand">
      <div class="brand-mark"><MapLocation /></div>
      <div><strong>生活圈体检</strong><span>COMMUNITY PULSE · 黄埔区样例</span></div>
    </div>
    <div class="topbar-actions">
      <div class="theme-switch" role="group" aria-label="主题切换">
        <button type="button" :class="{ on: theme === 'dark' }" :aria-pressed="theme === 'dark'" title="深色科技风" aria-label="切换到深色科技风" @click="emit('update:theme', 'dark', $event)"><Moon /></button>
        <button type="button" :class="{ on: theme === 'light' }" :aria-pressed="theme === 'light'" title="浅色高级风" aria-label="切换到浅色高级风" @click="emit('update:theme', 'light', $event)"><Sunny /></button>
      </div>
      <div class="topbar-meta">
        <span class="live-dot" :class="{ pending: mapStatusLoading, warning: !mapStatusLoading && !realApiConfigured }"></span>
        {{ mapStatusLoading ? '正在读取地图配置' : !mapStatusAvailable ? '地图配置不可用' : realApiConfigured ? realApiVerified ? '真实百度 Web API 探测成功' : '真实百度服务已配置（未探测）' : '当前为本地快照' }}
        <span class="divider"></span><span>最后分析：{{ hasReport ? '刚刚' : '等待中' }}</span>
      </div>
      <button class="guide-entry" type="button" @click="emit('open-guide')"><QuestionFilled />操作向导</button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { MapLocation, Moon, QuestionFilled, Sunny } from '@element-plus/icons-vue'

defineProps<{ hasReport: boolean; theme: 'dark' | 'light'; mapStatusLoading: boolean; mapStatusAvailable: boolean; realApiConfigured: boolean; realApiVerified: boolean }>()
const emit = defineEmits<{ 'open-guide': []; 'update:theme': [value: 'dark' | 'light', event?: MouseEvent] }>()
</script>
