<template>
  <header class="topbar">
    <div class="brand">
      <div class="brand-mark"><MapLocation /></div>
      <div><strong title="15分钟生活圈·智能体检与规划助手">15分钟生活圈·<br class="brand-title-break" />智能体检与规划助手</strong><span>COMMUNITY PULSE · 广州市黄埔区样例</span></div>
    </div>
    <nav class="workbench-switcher" aria-label="工作台切换">
      <button
        type="button"
        :class="{ active: activeWorkbench === 'controls' }"
        :aria-pressed="activeWorkbench === 'controls'"
        @click="emit('toggle-workbench', 'controls')"
      >智能体检工作台</button>
      <button
        type="button"
        :class="{ active: activeWorkbench === 'report' }"
        :aria-pressed="activeWorkbench === 'report'"
        @click="emit('toggle-workbench', 'report')"
      >社区体检报告</button>
    </nav>
    <div class="topbar-actions">
      <button class="theme-switch" type="button" :title="themeSwitchLabel" :aria-label="themeSwitchLabel" @click="emit('update:theme', nextTheme, $event)">
        <Sunny v-if="theme === 'dark'" aria-hidden="true" /><Moon v-else aria-hidden="true" />
      </button>
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
import { computed } from 'vue'
import { MapLocation, Moon, QuestionFilled, Sunny } from '@element-plus/icons-vue'

const props = defineProps<{ hasReport: boolean; theme: 'dark' | 'light'; mapStatusLoading: boolean; mapStatusAvailable: boolean; realApiConfigured: boolean; realApiVerified: boolean; activeWorkbench: 'controls' | 'report' | null }>()
const emit = defineEmits<{ 'open-guide': []; 'toggle-workbench': [panel: 'controls' | 'report']; 'update:theme': [value: 'dark' | 'light', event?: MouseEvent] }>()
const nextTheme = computed(() => props.theme === 'dark' ? 'light' : 'dark')
const themeSwitchLabel = computed(() => nextTheme.value === 'light' ? '切换到浅色主题' : '切换到深色主题')
</script>
