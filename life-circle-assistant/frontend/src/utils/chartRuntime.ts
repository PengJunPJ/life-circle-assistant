import { BarChart, HeatmapChart, RadarChart } from 'echarts/charts'
import { GridComponent, RadarComponent, TooltipComponent, VisualMapContinuousComponent } from 'echarts/components'
import { init, use, type ECharts } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'

use([BarChart, HeatmapChart, RadarChart, GridComponent, RadarComponent, TooltipComponent, VisualMapContinuousComponent, CanvasRenderer])

export { init }
export type { ECharts }
