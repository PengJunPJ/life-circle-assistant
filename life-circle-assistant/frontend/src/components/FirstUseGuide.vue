<template>
  <el-tour
    :model-value="open"
    :current="current"
    :mask="{ color: 'rgba(18, 43, 47, .58)' }"
    :gap="{ offset: 8, radius: 7 }"
    :scroll-into-view-options="{ block: 'center', behavior: 'smooth' }"
    :z-index="120"
    type="primary"
    @update:model-value="handleOpenChange"
    @update:current="current = $event"
    @change="handleStepChange"
    @close="closeGuide"
    @finish="finishGuide"
  >
    <el-tour-step
      target="[data-guide='source-status']"
      title="先确认是真实百度地图"
      :description="sourceDescription"
      placement="right-start"
      :prev-button-props="hiddenPrevious"
      :next-button-props="nextButton"
    />
    <el-tour-step
      target="[data-guide='analysis-center']"
      title="选择分析中心点"
      description="输入地址搜索、填写 BD-09 坐标，或直接点击地图。选择候选后确认地址和坐标正确。"
      placement="right"
      :prev-button-props="previousButton"
      :next-button-props="nextButton"
    />
    <el-tour-step
      target="[data-guide='analysis-parameters']"
      title="设置体检参数"
      description="页面已默认选择“正式分析”和 15 分钟，并保留四类设施；正式分析会向百度发起更多步行路线请求。"
      placement="right"
      :prev-button-props="previousButton"
      :next-button-props="nextButton"
    />
    <el-tour-step
      target="[data-guide='run-analysis']"
      title="手动开始体检"
      description="确认页面显示真实服务就绪后点击“开始真实分析”。正式分析可能需要等待，请不要连续重复提交。"
      placement="right-end"
      :prev-button-props="previousButton"
      :next-button-props="nextButton"
    />
    <el-tour-step
      target="#analysis-report-panel"
      title="查看结果和数据质量"
      description="报告生成后先查看数据质量，再阅读评分、盲区、规划建议和判定证据。显示“部分结果”时不要直接作为正式结论。"
      placement="left-start"
      :prev-button-props="previousButton"
      :next-button-props="finishButton"
    />
  </el-tour>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElTour, ElTourStep } from 'element-plus/es/components/tour/index'
import type { MapStatus } from '../types/report'

const props = defineProps<{
  open: boolean
  mapStatus: MapStatus | null
  mapStatusLoading: boolean
  realMapReady: boolean
}>()
const emit = defineEmits<{
  close: [completed: boolean]
  'step-change': [index: number]
}>()

const current = ref(0)
const previousButton = { children: '上一步' }
const hiddenPrevious = { children: '', style: { visibility: 'hidden' } }
const nextButton = { children: '下一步' }
const finishButton = { children: '我知道了' }
const sourceDescription = computed(() => {
  if (props.mapStatusLoading) return '正在检测后端数据源和浏览器底图，请稍候。'
  if (!props.mapStatus) return '暂时无法读取地图服务状态，请先确认后端已启动。'
  if (!props.mapStatus.real_api_configured) return '当前仍是本地快照模式，不会请求最新百度地图数据。需将 BAIDU_MAP_MODE 设为 real 并重启服务。'
  if (!props.realMapReady) return '后端已配置真实 Web 服务，但接口连通性尚未探测、浏览器底图也未就绪。请检查 Web 服务 AK 与浏览器 AK 域名白名单。'
  return '后端已配置真实 Web 服务，浏览器底图已加载；Web API 的地理编码探测需在分析面板中主动触发，且会消耗 API 配额。'
})

watch(() => props.open, (value) => {
  if (!value) return
  current.value = 0
  emit('step-change', 0)
})

function handleOpenChange(value: boolean) {
  if (!value) closeGuide()
}

function handleStepChange(index: number) {
  current.value = index
  emit('step-change', index)
}

function closeGuide() {
  emit('close', false)
}

function finishGuide() {
  emit('close', true)
}
</script>
