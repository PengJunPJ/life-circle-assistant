import assert from 'node:assert/strict'
import { mkdtempSync } from 'node:fs'
import { createRequire } from 'node:module'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(resolve(dirname(fileURLToPath(import.meta.url)), '../../life-circle-assistant/frontend/package.json'))
const { chromium } = require('playwright-core')
const outputDir = mkdtempSync(join(tmpdir(), 'life-circle-planning-browser-'))
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true })
const errors = []
const evidence = []
try {
  for (const [name, viewport, theme] of [
    ['desktop-dark', { width: 1440, height: 1000 }, 'dark'],
    ['mobile-light', { width: 390, height: 844 }, 'light'],
  ]) {
    const page = await browser.newPage({ viewport })
    page.on('pageerror', error => errors.push(error.message))
    await page.addInitScript(value => {
      localStorage.setItem('life-circle:first-use-guide:v1', 'completed')
      localStorage.setItem('life-circle:theme:v1', value)
    }, theme)
    await page.goto('http://127.0.0.1:5177')
    if (viewport.width < 820) await page.locator('.mobile-workspace-actions [aria-controls="analysis-controls-panel"]').click()
    await page.locator('[data-guide="run-analysis"]').click()
    if (viewport.width < 820) {
      await page.locator('#analysis-controls-panel .mobile-panel-close').click()
      await page.locator('.mobile-workspace-actions [aria-controls="analysis-report-panel"]').click()
    }
    await page.locator('.score-value').waitFor({ timeout: 60000 })
    const assistant = page.locator('.ai-assistant')
    await page.locator('.simulation-field select').selectOption('market')
    await page.locator('.simulation-location button').click()
    if (viewport.width < 820) await page.locator('#analysis-report-panel .mobile-panel-close').click()
    const canvas = page.locator('.map-canvas')
    const box = await canvas.boundingBox()
    await canvas.click({ position: { x: box.width / 2, y: box.height / 2 } })
    if (viewport.width < 820) await page.locator('.mobile-workspace-actions [aria-controls="analysis-report-panel"]').click()
    await page.locator('.simulation-location strong').filter({ hasText: /\d/ }).waitFor()
    await assistant.getByLabel('向规划助手提问').fill('查一下菜市场盲区，再模拟新增一个菜市场')
    const responsePromise = page.waitForResponse(response => response.request().method() === 'POST' && response.url().endsWith('/ai/plan'))
    await assistant.locator('.ai-question button').click()
    const response = await responsePromise
    assert.equal(response.status(), 200)
    const turn = await response.json()
    assert.equal(turn.mode, 'tool_rules')
    assert.equal(turn.simulations.length, 1)
    assert.deepEqual(turn.tool_calls.map(call => call.name), ['query_facilities', 'get_grid_evidence', 'get_planning_candidates', 'simulate_facility'])
    assert.ok(turn.tool_calls.every(call => call.status === 'completed'))
    await assistant.locator('.planning-tools').waitFor()
    await page.locator('.simulation-comparison').waitFor()
    assert.ok(await page.locator('.simulation-legend').count())
    assert.ok((await assistant.textContent()).includes('规则工具 · 模型未启用'))
    await assistant.getByLabel('向规划助手提问').fill('为什么这里值得优先考虑？')
    const followupPromise = page.waitForRequest(request => request.method() === 'POST' && request.url().endsWith('/ai/plan'))
    const followupResponse = page.waitForResponse(response => response.request().method() === 'POST' && response.url().endsWith('/ai/plan'))
    await assistant.locator('.ai-question button').click()
    assert.equal((await followupPromise).postDataJSON().previous_turn_id, turn.id)
    assert.equal((await followupResponse).status(), 200)
    await assistant.locator('.ai-new-topic').click()
    await assistant.getByLabel('向规划助手提问').fill('查询药店')
    const freshPromise = page.waitForRequest(request => request.method() === 'POST' && request.url().endsWith('/ai/plan'))
    const freshResponse = page.waitForResponse(response => response.request().method() === 'POST' && response.url().endsWith('/ai/plan'))
    await assistant.locator('.ai-question button').click()
    assert.equal((await freshPromise).postDataJSON().previous_turn_id, undefined)
    assert.equal((await freshResponse).status(), 200)
    await assistant.locator('.planning-tools').waitFor()
    const overflow = await assistant.evaluate(element => element.scrollWidth > element.clientWidth + 1)
    assert.equal(overflow, false, '工具结果不能横向溢出')
    await assistant.scrollIntoViewIfNeeded()
    await page.screenshot({ path: join(outputDir, `${name}.png`), animations: 'disabled' })
    evidence.push({ name, toolCalls: turn.tool_calls.length, simulationId: turn.simulations[0].id, previousTurnVerified: true, newTopicVerified: true, horizontalOverflow: overflow })
    await page.close()
  }
  assert.deepEqual(errors, [], '浏览器运行时不应报错')
  process.stdout.write(JSON.stringify({ evidence, errors, outputDir }, null, 2) + '\n')
} finally {
  await browser.close()
}
