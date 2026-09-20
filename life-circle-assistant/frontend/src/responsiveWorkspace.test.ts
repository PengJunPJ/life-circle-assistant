import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import app from './App.vue?raw'
import controls from './components/AnalysisControls.vue?raw'
import mapStage from './components/MapStage.vue?raw'

const styles = readFileSync(new URL('./styles.css', import.meta.url), 'utf8')

describe('响应式工作台布局契约', () => {
  it('桌面视口保留参数、地图、报告三栏工作台', () => {
    expect(styles).toMatch(/\.workspace\s*\{[^}]*display:\s*grid;[^}]*grid-template-columns:\s*286px minmax\(480px, 1fr\) 355px;/s)
    expect(styles).toContain('.mobile-panel-heading, .mobile-workspace-actions, .mobile-panel-backdrop, .mobile-legend-toggle, .mobile-map-legend { display: none; }')
  })

  it('移动视口消除页面横向溢出并以地图作为主区域', () => {
    expect(styles).toContain('@media (max-width: 820px)')
    expect(styles).toMatch(/html, body, #app\s*\{[^}]*width:\s*100%;[^}]*overflow:\s*hidden;/s)
    expect(styles).toMatch(/@media \(max-width: 820px\)[\s\S]*?\.workspace\s*\{[^}]*display:\s*block;[^}]*width:\s*100%;[^}]*overflow:\s*hidden;/)
    expect(styles).toMatch(/\.map-stage\s*\{[^}]*position:\s*absolute;[^}]*inset:\s*0;/s)
    expect(styles).toMatch(/\.control-panel, \.report-panel\s*\{[^}]*left:\s*8px;[^}]*right:\s*8px;[^}]*width:\s*auto;[^}]*overflow-x:\s*hidden;/s)
  })

  it('移动参数抽屉和独立报告面板默认收起且可显式展开', () => {
    expect(styles).toMatch(/\.control-panel, \.report-panel\s*\{[^}]*transform:\s*translateY\(calc\(100% \+ 92px\)\);[^}]*visibility:\s*hidden;/s)
    expect(styles).toMatch(/\.control-panel\.mobile-open, \.report-panel\.mobile-open\s*\{[^}]*transform:\s*translateY\(0\);[^}]*visibility:\s*visible;/s)
    expect(app).toContain('aria-controls="analysis-controls-panel"')
    expect(app).toContain('aria-controls="analysis-report-panel"')
    expect(app).toContain("event.key === 'Escape'")
  })

  it('主要状态、控件和地图信息提供辅助技术可识别的表达', () => {
    expect(app).toContain('aria-live="polite"')
    expect(app).toContain('role="alert"')
    expect(controls).toContain(':aria-pressed="visibleCategories.includes(category)"')
    expect(controls).toContain('aria-label="使用输入的 BD-09 坐标"')
    expect(mapStage).toContain('aria-label="重新运行当前分析"')
    expect(mapStage).toContain('红色网纹与感叹号')
    expect(mapStage).toContain('黄色斜纹与三角形')
  })
})
