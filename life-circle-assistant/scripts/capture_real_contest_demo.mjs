import { copyFileSync, existsSync, mkdirSync, writeFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const require = createRequire(join(root, 'frontend/package.json'))
const { chromium } = require('playwright-core')
const baseUrl = process.env.CONTEST_APP_URL || 'http://127.0.0.1:5173'
const apiUrl = process.env.CONTEST_API_URL || 'http://127.0.0.1:8000'
const output = join(root, 'docs/contest/submission')
const chrome = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const viewport = { width: 1600, height: 950 }

async function main() {
  const health = await fetch(`${apiUrl}/api/health`).then((r) => r.json())
  if (health.version !== '2.3.0' || health.provider_mode !== 'real') throw new Error('需 v2.3.0 真实后端')
  if (!existsSync(chrome)) throw new Error('请配置 Chrome 可执行文件路径')
  mkdirSync(output, { recursive: true })
  const browser = await chromium.launch({ executablePath: chrome, headless: true })
  const context = await browser.newContext({ viewport, recordVideo: { dir: output, size: viewport } })
  const page = await context.newPage()
  const video = page.video()
  let routeEvidence
  let report
  const errors = []
  // 仅保留错误概述；不归档带 AK 的请求 URL、浏览器日志或 HAR。
  page.on('pageerror', (error) => errors.push(error.message.replace(/(?:ak|key)=[^&\s]+/gi, 'key=REDACTED')))
  page.on('response', async (response) => {
    const url = new URL(response.url())
    if (url.pathname === '/api/route/walking' && response.ok()) routeEvidence = await response.json()
    if (/^\/api\/reports\/[^/]+$/.test(url.pathname) && response.ok()) report = await response.json()
  })
  const hold = async (text, seconds = 24) => {
    await page.evaluate((caption) => {
      let el = document.getElementById('recording-caption')
      if (!el) {
        el = document.createElement('div')
        el.id = 'recording-caption'
        el.style.cssText = 'position:fixed;bottom:12px;left:340px;right:18px;z-index:99999;background:#101c2ef0;color:white;padding:14px 18px;border-radius:8px;font:16px sans-serif;pointer-events:none'
        document.body.append(el)
      }
      el.textContent = `录屏说明 · ${caption}`
    }, text)
    await page.waitForTimeout(seconds * 1000)
  }
  try {
    await page.addInitScript(() => {
      localStorage.setItem('life-circle:first-use-guide:v1', 'completed')
      localStorage.setItem('life-circle:theme:v1', 'dark')
    })
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded', timeout: 30000 })
    await page.getByRole('button', { name: '验证 Web API', exact: true }).click()
    await page.getByText('Web API探测成功', { exact: false }).waitFor({ timeout: 30000 }).catch(async () => {
      const text = await page.locator('.map-readiness').innerText()
      if (!text.includes('成功') && !text.includes('已验证')) throw new Error('Web API 探测未确认通过')
    })
    await hold('真实模式、Web API 探活与浏览器底图分别验证；无密钥或降级结果会明确披露。', 20)
    await page.locator('.history-open').first().click()
    await page.locator('.report-content').waitFor({ timeout: 30000 })
    await hold('打开本次真实七类报告：热缓存来自刚完成的冷缓存分析，不冒充新的步行 API 调用。', 24)
    const labels = page.locator('.facility-map-label')
    await labels.first().waitFor({ timeout: 30000 })
    let selected = false
    for (let i = 0; i < Math.min(await labels.count(), 40); i++) {
      const box = await labels.nth(i).boundingBox()
      if (!box || box.x < 350 || box.x > 1150 || box.y < 120 || box.y > 750) continue
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
      await page.waitForTimeout(700)
      const button = page.locator('.hc-route-btn')
      if (await button.isVisible() && await button.isEnabled()) {
        await button.click()
        selected = true
        break
      }
    }
    if (!selected) throw new Error('未找到可操作的真实设施路线按钮')
    await page.locator('.route-chip').waitFor({ timeout: 30000 })
    await page.waitForTimeout(2000)
    if (!routeEvidence || !routeEvidence.polyline?.length) throw new Error('路线缺少真实返回的折线')
    await page.locator('#recording-caption').evaluate((el) => el.remove())
    await page.screenshot({ path: join(root, 'docs/contest/screenshots/07-walking-route.png') })
    await hold('真实步行路线：显示起点、终点、路径折线和分钟数；不以直线替代道路路径。', 26)
    // 路线证据已经完成；后续展示只使用稳定的报告区域，避免依赖可能为空的键盘导航列表。
    const evidence = page.locator('.service-area-evidence')
    if (await evidence.count()) await evidence.first().scrollIntoViewIfNeeded()
    await hold('盲区按网格展示距离、步行时长、数据来源与置信度；同源一致性不等于独立准确率。', 26)
    const scoreCategory = page.locator('.score-category').first()
    if (await scoreCategory.count()) await scoreCategory.scrollIntoViewIfNeeded()
    const scoreSummary = page.locator('.score-category summary').first()
    if (await scoreSummary.count()) await scoreSummary.click()
    await hold('类别评分展开数量、步行可达与覆盖率的依据；七维雷达辅助比较各类设施。', 24)
    const radar = page.locator('.radar')
    if (await radar.count()) await radar.scrollIntoViewIfNeeded()
    await hold('评分用于辅助判断，不能替代现场调查、设施开放情况与城市规划审批。', 20)
    const aiAssistant = page.locator('.ai-assistant')
    if (await aiAssistant.count()) {
      await aiAssistant.scrollIntoViewIfNeeded()
      const summaryButton = aiAssistant.getByRole('button', { name: '体检摘要', exact: true })
      if (await summaryButton.count()) {
        await summaryButton.click()
        await page.locator('.ai-result').waitFor({ timeout: 30000 })
      }
    }
    await hold('此录屏未启用外部大模型，展示基于报告证据的规则解读及引用。', 24)
    const execution = page.locator('.execution-section')
    if (await execution.count()) await execution.scrollIntoViewIfNeeded()
    await hold('核对执行指标：冷缓存 149.2 秒 / 263 次调用；热缓存 13.2 秒 / 18 次调用。视频材料仍需上传取得公开链接。', 26)
  } finally {
    await context.close()
    await browser.close()
  }
  const finalVideo = join(output, 'v2.3.0-real-demo-20261012.webm')
  // Playwright 完成编码后 video.path() 才可读取；saveAs 在 context.close() 后不可用。
  copyFileSync(await video.path(), finalVideo)
  if (!report || !routeEvidence) throw new Error('录屏未采集到报告或路线证据')
  writeFileSync(join(output, 'real-demo-evidence-20261012.json'), JSON.stringify({
    captured_at: new Date().toISOString(), app_version: health.version,
    provider_mode: health.provider_mode, report_id: report.report_id,
    screenshot: '../screenshots/07-walking-route.png', video: 'v2.3.0-real-demo-20261012.webm',
    route: routeEvidence, browser_errors: errors,
    recording_note: '实操作录屏；底部录屏说明为注释，不是产品 UI；未归档请求 URL、凭证或 HAR。',
  }, null, 2) + '\n')
  console.log('真实路线截图、操作录屏与证据已保存。')
}
main().catch((error) => { console.error(error.message); process.exitCode = 1 })
