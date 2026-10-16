// 在已采集会话中用产品原生图层开关聚焦小学、菜市场，保留原始质量状态。
import { createRequire } from 'node:module'
import { readFileSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
const app = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const require = createRequire(resolve(app, 'frontend/package.json'))
const { chromium } = require('playwright-core')
const out = resolve(app, 'docs/contest/submission/screenshots-20261015')
const b = await chromium.connectOverCDP('http://localhost:9226')
const p = b.contexts()[0].pages()[0]
const menu = p.locator('.map-layer-menu')
if (!await menu.isVisible()) await p.getByRole('button', { name: '图层', exact: true }).click()
await menu.getByRole('button', { name: '全部隐藏', exact: true }).click()
for (const name of ['小学', '菜市场']) await menu.getByRole('button', { name, exact: true }).click()
await p.getByRole('button', { name: '关闭地图显示设置', exact: true }).click()
await p.waitForTimeout(1000)
await p.screenshot({ path: resolve(out, '04-real-simulation.png'), animations: 'disabled' })
await p.getByRole('button', { name: '清除模拟', exact: true }).click()
await p.getByRole('tab', { name: '体检概览', exact: true }).click()
await p.waitForTimeout(1500)
await p.screenshot({ path: resolve(out, '01-real-map-report.png'), animations: 'disabled' })
await p.getByRole('tab', { name: '改善建议', exact: true }).click()
await p.getByRole('button', { name: '智能助手', exact: true }).click()
const responsePromise = p.waitForResponse(r => new URL(r.url()).pathname.endsWith('/ai/interpret') && r.request().method() === 'POST', { timeout: 180000 })
await p.getByRole('button', { name: '体检摘要', exact: true }).click()
const response = await responsePromise
const result = await response.json()
if (result.mode !== 'llm_structured' || result.model !== 'qwen3.7-flash') throw new Error('真实模型解读未成功')
await p.locator('.ai-result').waitFor()
await p.locator('.ai-result').scrollIntoViewIfNeeded()
await p.waitForTimeout(1000)
await p.screenshot({ path: resolve(out, '02-real-ai-summary.png'), animations: 'disabled' })
await p.locator('.ai-result').screenshot({ path: resolve(out, '05-real-ai-detail.png'), animations: 'disabled' })
const evidence = JSON.parse(readFileSync(resolve(out, 'capture-evidence.json'), 'utf8'))
const report = await (await fetch('http://127.0.0.1:8000/api/reports/' + result.report_id)).json()
const health = await (await fetch('http://127.0.0.1:8000/api/health')).json()
evidence.report = { id: report.report_id, completeness: report.completeness, categories: report.parameters.categories, score: report.scoring.score, valid_categories: report.scoring.valid_category_count, partial_failures: report.data_quality.partial_failures, sources: report.data_quality.sources }
evidence.final_map_visible_categories = ['school', 'market']
evidence.latest_summary = { mode: result.mode, model: result.model, report_id: result.report_id }
evidence.calls_after = health.llm.calls
evidence.failures_after = health.llm.failures
evidence.captures.push('05-real-ai-detail.png')
evidence.finished_at = new Date().toISOString()
writeFileSync(resolve(out, 'capture-evidence.json'), JSON.stringify(evidence, null, 2))
console.log(JSON.stringify({ mode: result.mode, model: result.model, calls: health.llm.calls, failures: health.llm.failures, report: evidence.report }))
await b.close()
