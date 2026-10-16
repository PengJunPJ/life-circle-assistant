import assert from 'node:assert/strict'
import { mkdtempSync } from 'node:fs'
import { createRequire } from 'node:module'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(resolve(dirname(fileURLToPath(import.meta.url)), '../../life-circle-assistant/frontend/package.json'))
const { chromium } = require('playwright-core')
const outputDir = mkdtempSync(join(tmpdir(), 'life-circle-intent-browser-'))
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
    let analysisRequests = 0
    page.on('request', request => {
      if (request.method() === 'POST' && request.url().endsWith('/api/analyze')) analysisRequests++
    })
    await page.addInitScript(value => {
      localStorage.setItem('life-circle:first-use-guide:v1', 'completed')
      localStorage.setItem('life-circle:theme:v1', value)
    }, theme)
    await page.goto('http://127.0.0.1:5177')
    if (viewport.width < 820) await page.locator('.mobile-workspace-actions [aria-controls="analysis-controls-panel"]').click()
    const input = page.locator('#analysis-message')
    await input.fill('步行10分钟，关注买药和看病')
    await page.locator('.natural-send').click()
    await page.locator('.natural-conversation').getByText(/请补充社区或地址/).waitFor()
    assert.equal(await page.locator('.natural-preview .primary-action').isDisabled(), true)
    await input.fill('地址是红山街道海韵东路')
    await page.locator('.natural-send').click()
    const confirm = page.locator('.natural-preview .primary-action')
    await page.waitForFunction(() => !document.querySelector('.natural-preview .primary-action')?.disabled)
    await page.getByLabel('对话步行时间').selectOption('20')
    assert.equal(analysisRequests, 0, '确认前不应启动分析')
    assert.equal(await page.locator('[data-guide="run-analysis"]').count(), 0, '对话预览中不应展示旧表单启动按钮')
    await confirm.scrollIntoViewIfNeeded()
    await page.screenshot({ path: join(outputDir, `${name}.png`), animations: 'disabled' })
    const overflow = await page.locator('.natural-analysis').evaluate(element => element.scrollWidth > element.clientWidth + 1)
    assert.equal(overflow, false, '对话区域不应横向溢出')
    const requestPromise = page.waitForRequest(request => request.method() === 'POST' && request.url().endsWith('/api/analyze'))
    await confirm.click()
    const request = await requestPromise
    assert.equal(request.postDataJSON().minutes, 20)
    assert.deepEqual(request.postDataJSON().categories, ['pharmacy', 'medical'])
    assert.equal(analysisRequests, 1)
    if (viewport.width < 820) {
      await page.locator('#analysis-controls-panel .mobile-panel-close').click()
      await page.locator('.mobile-workspace-actions [aria-controls="analysis-report-panel"]').click()
    }
    await page.locator('.score-value').waitFor({ timeout: 60000 })
    evidence.push({ name, analysisRequests, reportRendered: true, horizontalOverflow: overflow })
    await page.close()
  }
  assert.deepEqual(errors, [], '浏览器运行时不应报错')
  process.stdout.write(JSON.stringify({ evidence, errors, outputDir }, null, 2) + '\n')
} finally {
  await browser.close()
}
