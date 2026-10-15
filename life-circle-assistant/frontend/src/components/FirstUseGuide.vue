<template>
  <el-tour
    :model-value="open"
    :current="current"
    :mask="{ color: 'rgba(18, 43, 47, .58)' }"
    :gap="{ offset: 8, radius: 7 }"
    :content-style="{ width: '360px', maxWidth: 'calc(100vw - 32px)' }"
    :scroll-into-view-options="{ block: 'center', behavior: 'instant' }"
    :target-area-clickable="false"
    :z-index="120"
    type="primary"
    @update:current="current = $event"
    @change="handleStepChange"
    @close="closeGuide"
    @finish="finishGuide"
  >
    <el-tour-step
      v-for="(step, index) in steps"
      :key="step.id"
      :target="currentTarget"
      :title="step.title"
      :description="step.description"
      :placement="placement(step)"
      :prev-button-props="previousButton"
      :next-button-props="index === steps.length - 1 ? finishButton : nextButton"
    />
  </el-tour>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { ElTour, ElTourStep } from 'element-plus/es/components/tour/index'
import type { MapProbeResult, MapStatus } from '../types/report'
import type { GuideStep } from '../types/guide'

const props = defineProps<{
  open: boolean
  hasReport: boolean
  mapStatus: MapStatus | null
  mapStatusLoading: boolean
  mapProbeResult: MapProbeResult | null
  realMapReady: boolean
}>()
const emit = defineEmits<{
  close: [completed: boolean]
  'step-change': [step: GuideStep]
}>()

const current = ref(0)
const currentTarget = shallowRef<HTMLElement>()
// 手机端面板从底部弹出，左右放置会把卡片推出屏幕，改为放在目标上方。
// 首帧就按视口取方位，避免手机端先渲染出屏幕外的卡片再纠正。
const viewportQuery =
  typeof window.matchMedia === 'function'
    ? window.matchMedia('(max-width: 820px)')
    : null
const narrowViewport = ref(viewportQuery?.matches ?? false)
function syncViewport(event: MediaQueryListEvent) {
  narrowViewport.value = event.matches
}
onMounted(() => {
  viewportQuery?.addEventListener('change', syncViewport)
})
onBeforeUnmount(() => {
  viewportQuery?.removeEventListener('change', syncViewport)
})
function placement(step: TourStep) {
  if (step.surface === 'controls' || step.surface === 'report') {
    if (narrowViewport.value) return 'top'
    return step.surface === 'controls' ? 'right' : 'left'
  }
  return 'bottom'
}
// 一次导览保持同一套步骤，分析在后台完成时也不会跳步。
const withReport = ref(props.hasReport)
const previousButton = { children: '上一步' }
const nextButton = { children: '下一步' }
const finishButton = { children: '完成向导' }
const sourceDescription = computed(() => {
  if (props.mapStatusLoading) return '正在读取数据服务状态。底图加载和 Web API 验证是两项独立检查；导览不会发起验证。'
  if (!props.mapStatus) return '暂时无法读取数据服务状态。请退出向导后展开“详情”，点击“刷新状态”；仍不可用时联系管理员。'
  if (!props.mapStatus.real_api_configured) return '当前使用本地快照，仅支持沙涌长盛花园样例周边，数据非实时。可先体验样例；分析其他地点前请联系管理员启用真实服务。'
  const api = props.mapProbeResult?.verified ? 'Web API 已通过本次验证。' : props.mapProbeResult ? 'Web API 最近一次验证未通过，请展开“详情”查看原因并重试。' : 'Web API 已配置但尚未验证。可在“详情”中主动点击“验证 Web API”，这会消耗地图配额。'
  return `${api}${props.realMapReady ? '浏览器底图已加载。' : '浏览器底图尚未加载，可稍后重试或联系管理员检查。'}导览不会自动调用地图接口。`
})

type TourStep = GuideStep & { title: string; description: string; target: string }
const steps = computed<TourStep[]>(() => {
  const reportReady = withReport.value && props.hasReport
  const result: TourStep[] = [
    { id: 'source', surface: 'controls', target: '[data-guide="source-status"]', title: '确认数据与地图状态', description: sourceDescription.value },
    { id: 'location', surface: 'controls', target: '[data-guide="analysis-center"]', title: '选择填写方式与体检位置', description: '“自主设置”可搜索地址或地图选点；“一句话填写”把描述填入同一套参数。出现同名候选时，需在公共位置区确认地点，填写本身不会开始体检。' },
    { id: 'parameters', surface: 'controls', target: '[data-guide="analysis-parameters"]', title: '设置步行时间与分析精度', description: '选择 10、15 或 20 分钟步行时间。“高级设置”可切换快速分析与正式分析，也可确认 BD-09、GCJ-02 或 WGS84 输入坐标。正式分析使用更多步行采样，耗时较长。' },
    { id: 'facilities', surface: 'controls', target: '[data-guide="analysis-facilities"]', title: '选择本次体检的设施', description: '七类设施可多选，默认选择医疗服务、小学、购物、养老。已有报告缺少某类设施时，可补充体检；地图图层只改变显示，不会扩大已体检的范围。' },
    { id: 'run', surface: 'controls', target: '[data-guide="run-analysis"]', title: '核对后手动开始体检', description: '核对底部地点、步行时间和设施数量，退出向导后点击“开始体检”或“补充体检”。位置未确认、参数缺失或任务执行中时按钮不可用。' },
    { id: 'conversation', surface: 'conversation', target: '[data-guide="conversation"], [data-guide="conversation-launcher"]', title: '通过 AI 规划助手推进任务', description: '打开 AI 规划助手，可用一句话体检、找步行盲区、切换图层或做组合选址。需要确认的计划会列出路线和模型预算，请检查后再“确认执行”；执行中可查看进度或取消。' },
    { id: 'map', surface: 'map', target: '[data-guide="map-layers"]', title: '在地图上核对判定证据', description: `${reportReady ? '' : '报告生成后，'}通过“图层”筛选设施与服务区域；“区域判定”列出当前可见区域，可定位查看步行时间、判定依据、来源与置信度。1 公里稀缺、步行超时和未知状态需分别阅读，未知不代表已确认盲区。` },
    { id: 'overview', surface: 'report', reportPage: 'overview', target: reportReady ? '.report-tabs' : '.empty-report', title: reportReady ? '先看概览与设施详情' : '报告生成后从这里阅读', description: reportReady ? '先检查数据质量和“部分结果”提示，再看评分、可达面积、盲区与稀疏区。“设施详情”可查看各类设施和缺口；数据受限时请结合证据阅读结论。' : '当前还没有报告。体检完成后，这里会显示“体检概览”“设施详情”“改善建议”和“AI核验”。先检查数据质量和部分结果提示，再阅读评分与缺口；报告说明和导出也会随之开放。' },
  ]
  if (reportReady) result.push(
    { id: 'facility-details', surface: 'report', reportPage: 'facilities', target: '#report-page-facilities .page-heading', title: '逐类核对设施覆盖与空间缺口', description: '“设施详情”列出各类设施的数量、最近步行时间和评分依据。新报告还会分别统计 1 公里附近稀缺、已核验步行超时与未知网格；缺少路线证据时请先核验。' },
    { id: 'recommendations', surface: 'report', reportPage: 'recommendations', target: '#report-page-recommendations .page-heading', title: '从改善建议走到假设模拟', description: '可定位建议区域、模拟单设施或在地图上选择位置，也可借助智能助手分析。缺口代表点用于假设模拟，可建设条件仍需另行核验；组合规划可在 AI 核验中完成。' },
  )
  result.push({ id: 'ai', surface: 'report', reportPage: reportReady ? 'ai' : 'overview', target: reportReady ? '.completion-nav' : '.report-actions', title: reportReady ? '用 AI 核验形成规划闭环' : '了解报告后的 AI 核验流程', description: `${reportReady ? '' : '生成报告后进入“AI核验”：'}语义复核可审核设施类别与实体关系；现场观察支持文字和图片，复核前不改变事实。主动补测区分观测、估计和未决，预测不参与正式评分。组合规划使用候选地块和预算约束，角色报告提供不同读者的引用说明；正式重算会保留原报告并生成新报告。` })
  if (reportReady) result.push({ id: 'details', surface: 'report', reportPage: 'details', target: '.auxiliary-heading', title: '核对数据质量、预算与版本', description: '“报告说明”包含数据质量、评分依据、高德辅助验证、执行与缓存指标，以及报告具备的预算与版本账本。核对实际用量与结算状态；未决调用需先核对再授权重试。' })
  result.push({ id: 'history', surface: 'report', reportPage: 'history', target: '.history-title', title: '查找历史并比较两份报告', description: `“历史”支持按地址搜索、打开报告、重新体检；勾选两份报告后可比较结果。${reportReady ? '重新体检会运行新任务，请先确认范围。' : '当前没有报告也能查看历史。完成一次体检后，还可通过“导出”下载 PDF、JSON、CSV 或空间图层。'}` })
  if (reportReady) result.push({ id: 'export', surface: 'report', reportPage: 'export', target: '.auxiliary-heading', title: '按用途导出报告与空间数据', description: 'PDF 用于评审汇报，JSON 保留完整报告，CSV 提供指标与设施表。GeoJSON 兼容格式使用 BD-09；标准 GeoJSON（WGS84）用于 GIS 交换，坐标由近似逆转换得到。退出向导后选择格式下载。' })
  return result
})

watch(() => props.open, async (value) => {
  if (!value) return
  currentTarget.value = undefined
  withReport.value = props.hasReport
  current.value = 0
  await handleStepChange(0)
}, { immediate: true })

async function handleStepChange(index: number) {
  const step = steps.value[index]
  if (!step || !props.open) return
  current.value = index
  emit('step-change', { id: step.id, surface: step.surface, reportPage: step.reportPage })
  // 先展开桌面/手机面板并切换报告子页，再让 Tour 测量新的目标。
  await nextTick()
  if (!props.open || current.value !== index) return
  currentTarget.value = document.querySelector<HTMLElement>(step.target) ?? undefined
}

function closeGuide() {
  // Element Plus 完成时也会先触发 close，延后处理以保留完成状态。
  void nextTick(() => { if (props.open) emit('close', false) })
}

function finishGuide() {
  emit('close', true)
}
</script>
