<template>
  <header class="topbar">
    <div class="brand">
      <div class="brand-mark"><MapLocation /></div>
      <div><strong>生活圈体检</strong><span>COMMUNITY PULSE · 黄埔区样例</span></div>
    </div>
    <div class="topbar-meta"><span class="live-dot"></span>数据服务正常 <span class="divider"></span><span>最后分析：{{ hasReport ? '刚刚' : '等待中' }}</span></div>
  </header>
</template>

<script setup lang="ts">
import { MapLocation } from '@element-plus/icons-vue'

defineProps<{ hasReport: boolean }>()
</script>
