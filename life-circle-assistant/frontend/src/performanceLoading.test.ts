import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const app = readFileSync(new URL('./App.vue', import.meta.url), 'utf8')
const main = readFileSync(new URL('./main.ts', import.meta.url), 'utf8')
const reportPanel = readFileSync(new URL('./components/ReportPanel.vue', import.meta.url), 'utf8')
const viteConfig = readFileSync(new URL('../vite.config.ts', import.meta.url), 'utf8')

describe('前端主要功能按需加载', () => {
  it('报告和比较面板使用异步组件，不阻塞地图工作台首屏', () => {
    expect(app).toMatch(/defineAsyncComponent\(\(\) => import\('\.\/components\/ReportPanel\.vue'\)\)/)
    expect(app).toMatch(/defineAsyncComponent\(\(\) => import\('\.\/components\/ReportComparisonPanel\.vue'\)\)/)
  })

  it('图表动态加载，Element Plus 只注册首屏所需控件', () => {
    expect(reportPanel).toContain("import('../utils/chartRuntime')")
    expect(reportPanel).not.toMatch(/import \* as echarts from 'echarts'/)
    expect(main).not.toContain('.use(ElementPlus)')
    expect(main).toContain("component('ElSwitch'")
    expect(main).not.toContain("element-plus/dist/index.css")
  })

  it('构建时把图表与 UI 库拆成独立资源块', () => {
    expect(viteConfig).toContain("return 'charts'")
    expect(viteConfig).toContain("return 'element-plus'")
  })
})
