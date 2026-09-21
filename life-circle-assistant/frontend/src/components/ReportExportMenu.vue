<template>
  <section class="export-menu" aria-labelledby="export-menu-title">
    <div class="section-title">
      <span id="export-menu-title">导出体检数据</span>
      <small>同一标准报告</small>
    </div>
    <div class="export-options">
      <button
        v-for="option in options"
        :key="option.format"
        type="button"
        :disabled="Boolean(exportingFormat)"
        @click="download(option.format)"
      >
        <Download />
        <strong>{{ exportingFormat === option.format ? option.loadingLabel : option.label }}</strong>
        <small>{{ exportingFormat === option.format ? option.loadingDescription : option.description }}</small>
      </button>
    </div>
    <p
      v-if="feedback"
      :class="['export-feedback', feedbackKind]"
      :role="feedbackKind === 'error' ? 'alert' : 'status'"
      aria-live="polite"
    >{{ feedback }}</p>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Download } from '@element-plus/icons-vue'
import { downloadReportExport, type ReportExportFormat } from '../services/analysisApi'

const props = defineProps<{ reportId: string }>()
const exportingFormat = ref<ReportExportFormat | ''>('')
const feedback = ref('')
const feedbackKind = ref<'success' | 'error'>('success')
const options: { format: ReportExportFormat; label: string; description: string; loadingLabel: string; loadingDescription: string }[] = [
  { format: 'json', label: 'JSON', description: '完整报告', loadingLabel: '正在导出', loadingDescription: '准备完整报告' },
  { format: 'csv', label: 'CSV', description: '指标与设施表', loadingLabel: '正在导出', loadingDescription: '准备表格数据' },
  { format: 'geojson', label: 'GeoJSON', description: '空间图层', loadingLabel: '正在导出', loadingDescription: '准备空间图层' },
  { format: 'pdf', label: 'PDF', description: '评审与汇报版', loadingLabel: '正在生成', loadingDescription: '排版报告与地图' },
]

async function download(format: ReportExportFormat) {
  exportingFormat.value = format
  feedback.value = ''
  try {
    const filename = await downloadReportExport(props.reportId, format)
    feedbackKind.value = 'success'
    feedback.value = `已开始下载：${filename}`
  } catch (error) {
    feedbackKind.value = 'error'
    feedback.value = error instanceof Error ? error.message : '报告导出失败，请稍后重试'
  } finally {
    exportingFormat.value = ''
  }
}
</script>
