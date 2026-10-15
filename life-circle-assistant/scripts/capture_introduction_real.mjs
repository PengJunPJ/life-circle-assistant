// 为作品介绍采集当前真实地图与实际模型结果；不拦截或模拟任何业务请求。
import { createRequire } from 'node:module'
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const app = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const require = createRequire(resolve(app, 'frontend/package.json'))
const { chromium } = require('playwright-core')
const out = resolve(app, 'docs/contest/submission/screenshots-20261015')
mkdirSync(out, { recursive: true })
const health = await (await fetch('http://127.0.0.1:8000/api/health')).json()
if (health.mode !== 'real' || !health.llm?.available) throw new Error('需要真实地图和可用模型')
const evidence = { captured_at: new Date().toISOString(), version: health.version, mode: health.mode, model: health.llm.model, calls_before: health.llm.calls, captures: [], responses: [] }
const save = () => writeFileSync(resolve(out, 'capture-evidence.json'), JSON.stringify(evidence, null, 2))
const browser = await chromium.launch({ headless: true, executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', args: ['--remote-debugging-port=9226'] })
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 2 })
page.setDefaultTimeout(20000)
page.on('response', async response => {
  const path = new URL(response.url()).pathname
  if (!path.startsWith('/api/') || response.request().method() !== 'POST') return
  if (!/analyze|probe|interpret|plan|simulations/.test(path)) return
  try {
    const data = await response.json()
    const item = { path, status: response.status(), id: data.report_id || data.task_id || data.id, mode: data.mode, model: data.model, completeness: data.completeness, summary: data.summary, tool_calls: data.tool_calls?.map(t => ({ name: t.name, status: t.status })) }
    evidence.responses.push(item); save()
    console.log('response', JSON.stringify({ path, status: item.status, mode: item.mode, model: item.model, id: item.id }))
  } catch { /* 只记录可解析且已完成的响应 */ }
})
async function capture(filename) {
  await page.screenshot({ path: resolve(out, filename), animations: 'disabled' })
  evidence.captures.push(filename); save(); console.log('captured', filename)
}
await page.addInitScript(() => {
  localStorage.setItem('life-circle:first-use-guide:v1', 'completed')
  localStorage.setItem('life-circle:theme:v1', 'dark')
})
try {
  await page.goto('http://localhost:5173', { waitUntil: 'networkidle' })
  await page.locator('.compact-data-status summary').click()
  await page.getByRole('button', { name: '验证 Web API', exact: true }).click()
  await page.locator('.readiness-checks').getByText('Web API · 探测成功', { exact: false }).waitFor({ timeout: 60000 })
  await capture('00-real-service.png')
  await page.locator('.compact-data-status summary').click()
  const all = page.locator('.control-panel').getByRole('button', { name: '全选', exact: true })
  if (await all.isEnabled()) await all.click()
  await page.locator('.advanced-settings summary').click()
  await page.getByRole('button', { name: '正式分析', exact: true }).click()
  await page.locator('.advanced-settings summary').click()
  await page.locator('.primary-action').click()
  console.log('真实七类15分钟正式分析已启动')
  await page.locator('.score-value').waitFor({ state: 'attached', timeout: 600000 })
  await page.locator('.workbench-switcher').getByRole('button', { name: '社区体检报告', exact: true }).click()
  await page.locator('.score-value').waitFor()
  await page.waitForTimeout(2000)
  await capture('01-real-map-report.png')
  await page.getByRole('tab', { name: '改善建议', exact: true }).click()
  await page.getByRole('button', { name: '智能助手', exact: true }).click()
  await page.getByRole('button', { name: '体检摘要', exact: true }).click()
  await page.locator('.ai-result').waitFor({ timeout: 180000 })
  await page.locator('.ai-result').scrollIntoViewIfNeeded()
  await page.waitForTimeout(700)
  await capture('02-real-ai-summary.png')
  console.log('AI result mode', await page.locator('.ai-mode').innerText())
  await page.getByRole('button', { name: '查询服务短板', exact: true }).click()
  await page.locator('.ai-state[role="status"]').waitFor({ state: 'hidden', timeout: 180000 })
  await page.locator('.ai-result').scrollIntoViewIfNeeded()
  await capture('03-real-ai-tools.png')
  const details = page.locator('.recommendation-card details').first()
  await details.locator('summary').click()
  await details.getByRole('button', { name: '模拟此点', exact: true }).first().click()
  await page.locator('.simulation-result').waitFor({ timeout: 240000 })
  await page.locator('.simulation-result').scrollIntoViewIfNeeded()
  await page.waitForTimeout(700)
  await capture('04-real-simulation.png')
  const after = await (await fetch('http://127.0.0.1:8000/api/health')).json()
  evidence.calls_after = after.llm.calls; evidence.failures_after = after.llm.failures
  save(); console.log('完成', JSON.stringify({ calls: after.llm.calls, failures: after.llm.failures }))
} catch (error) {
  console.log('采集阶段异常', error.message.split('\n')[0])
  await capture('debug-current.png')
}
console.log('浏览器保留供复核，CDP端口9226')
await new Promise(resolve => browser.once('disconnected', resolve))
