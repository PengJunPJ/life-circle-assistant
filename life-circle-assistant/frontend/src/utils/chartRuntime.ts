import { BarChart } from 'echarts/charts'
import { GridComponent } from 'echarts/components'
import { init, use, type ECharts } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'

use([BarChart, GridComponent, CanvasRenderer])

export { init }
export type { ECharts }
