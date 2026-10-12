// 真实地图回归入口：历史报告打开后必须实际出现设施标签。
import { createRequire } from 'node:module'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const { chromium } = createRequire(join(root, 'frontend/package.json'))('playwright-core')
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true })
try {
  const page = await browser.newPage({ viewport: { width: 1600, height: 950 } })
  page.on('pageerror', (e) => console.log(e.stack?.split('\n').slice(0, 2).join('\n').replace(/\?[^\s)]+/g, '?REDACTED')))
  page.on('response', async (r) => {
    const url = new URL(r.url())
    if (url.hostname === 'api.map.baidu.com' && url.searchParams.get('qt') === 'verify') {
      const body = await r.text()
      console.log('鉴权 HTTP 状态', r.status(), '仅状态字段', body.match(/(?:status|code|message|msg)["']?\s*:\s*(?:\d+|["'][^"']*["'])/g))
    }
  })
  await page.addInitScript(() => localStorage.setItem('life-circle:first-use-guide:v1', 'completed'))
  await page.goto(process.env.CONTEST_APP_URL || 'http://127.0.0.1:5173', { waitUntil: 'domcontentloaded' })
  await page.locator('.history-open').first().click()
  await page.locator('.report-content').waitFor({ timeout: 10000 })
  await page.waitForTimeout(5000)
  console.log('标签数', await page.locator('.facility-map-label').count())
  console.log('底图状态', await page.locator('.map-readiness').innerText())
  console.log('地图大小', await page.locator('.map-container').boundingBox())
  console.log('BMap 状态', await page.evaluate(() => ({ map: typeof window.BMap?.Map, point: typeof window.BMap?.Point, label: typeof window.BMap?.Label })))
  console.log('百度脚本数量', await page.locator('script[src*="api.map.baidu.com/api?"]').count())
  await page.screenshot({ path: '/tmp/life-circle-real-map-debug.png' })
  if (!await page.locator('.facility-map-label').count()) throw new Error('真实地图未生成设施标签')
} finally { await browser.close() }
