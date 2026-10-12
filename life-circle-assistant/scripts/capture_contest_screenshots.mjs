import { existsSync, mkdirSync, readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const projectRoot = resolve(scriptDir, '..')
const requireFromFrontend = createRequire(join(projectRoot, 'frontend', 'package.json'))
const { chromium } = requireFromFrontend('playwright-core')
const outputDir = join(projectRoot, 'docs', 'contest', 'screenshots')
const baseUrl = process.env.CONTEST_APP_URL || 'http://127.0.0.1:5173'
const viewport = { width: 1600, height: 950 }

const chromeCandidates = [
  process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/Applications/Chromium.app/Contents/MacOS/Chromium',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser',
].filter(Boolean)

function executablePath() {
  return chromeCandidates.find((candidate) => existsSync(candidate))
}

function pngDimensions(path) {
  const bytes = readFileSync(path)
  if (bytes.toString('ascii', 1, 4) !== 'PNG') throw new Error(`${path} 不是 PNG 文件`)
  return { width: bytes.readUInt32BE(16), height: bytes.readUInt32BE(20) }
}

async function setTheme(page, theme) {
  await page.evaluate((value) => {
    document.documentElement.setAttribute('data-theme', value)
    window.localStorage.setItem('life-circle:theme:v1', value)
    window.dispatchEvent(new CustomEvent('life-circle:theme'))
  }, theme)
  await page.waitForTimeout(450)
}

async function reveal(page, selector) {
  const locator = page.locator(selector).first()
  await locator.waitFor({ state: 'visible', timeout: 20_000 })
  await locator.scrollIntoViewIfNeeded()
  await page.waitForTimeout(300)
  return locator
}

async function capture(page, filename) {
  const path = join(outputDir, filename)
  await page.screenshot({ path, animations: 'disabled' })
  const size = pngDimensions(path)
  if (size.width !== viewport.width || size.height !== viewport.height) {
    throw new Error(`${filename} 尺寸为 ${size.width}x${size.height}，预期 ${viewport.width}x${viewport.height}`)
  }
  process.stdout.write(`  ${filename} (${size.width}x${size.height})\n`)
}

async function showBarTooltip(page) {
  const canvas = await reveal(page, '.chart canvas')
  const box = await canvas.boundingBox()
  if (!box) throw new Error('无法读取柱状图位置')
  for (let index = 0; index < 7; index += 1) {
    const x = box.x + 42 + index * ((box.width - 60) / 7)
    await page.mouse.move(x, box.y + box.height * 0.58)
    await page.waitForTimeout(180)
    const visible = await page.locator('body > div').filter({ hasText: '类别得分' }).count()
    if (visible > 0) return
  }
  throw new Error('未能触发柱状图悬浮提示')
}

async function main() {
  const health = await fetch(`${process.env.CONTEST_API_URL || 'http://127.0.0.1:8000'}/api/health`).then((response) => response.json())
  if (health.provider_mode !== 'mock') throw new Error('离线截图采集仅允许 mock 后端，避免覆盖或混用真实证据')
  mkdirSync(outputDir, { recursive: true })
  const path = executablePath()
  const browser = await chromium.launch({
    headless: true,
    ...(path ? { executablePath: path } : { channel: 'chrome' }),
  })

  try {
    const page = await browser.newPage({ viewport, deviceScaleFactor: 1 })
    page.setDefaultTimeout(20_000)
    await page.addInitScript(() => {
      window.localStorage.setItem('life-circle:first-use-guide:v1', 'completed')
      window.localStorage.setItem('life-circle:theme:v1', 'dark')
    })
    await page.goto(baseUrl, { waitUntil: 'networkidle', timeout: 30_000 })
    await page.locator('.primary-action').waitFor({ state: 'visible' })

    process.stdout.write(`从 ${baseUrl} 采集参赛截图：\n`)
    await setTheme(page, 'dark')
    await capture(page, '01-workspace-dark.png')
    await setTheme(page, 'light')
    await capture(page, '01-workspace-light.png')

    await setTheme(page, 'dark')
    await page.locator('.primary-action').click()
    await page.locator('.report-content').waitFor({ state: 'visible', timeout: 120_000 })
    await page.locator('.chart canvas').waitFor({ state: 'visible', timeout: 20_000 })
    await capture(page, '02-isochrone-grid-dark.png')
    await setTheme(page, 'light')
    await capture(page, '02-isochrone-grid-light.png')

    await setTheme(page, 'dark')
    await page.locator('.service-area-keyboard-list button').first().click()
    await reveal(page, '.service-area-evidence')
    await capture(page, '03-blindspot-evidence.png')

    const firstScore = await reveal(page, '.score-category')
    if (!(await firstScore.evaluate((element) => element.hasAttribute('open')))) await firstScore.locator('summary').click()
    await capture(page, '04-score-breakdown.png')

    await showBarTooltip(page)
    await capture(page, '05-bar-tooltip.png')

    await reveal(page, '.radar canvas')
    await capture(page, '06-radar-dark.png')
    await setTheme(page, 'light')
    await reveal(page, '.radar canvas')
    await capture(page, '06-radar-light.png')

    await setTheme(page, 'dark')
    const assistant = await reveal(page, '.ai-assistant')
    await assistant.getByRole('button', { name: '体检摘要' }).click()
    await reveal(page, '.ai-result')
    await capture(page, '08-ai-interpretation.png')

    const simulationButton = await reveal(page, '.candidate-simulate')
    await simulationButton.click()
    await reveal(page, '.simulation-result')
    await capture(page, '09-simulation.png')

    await reveal(page, '.export-menu')
    await capture(page, '10-export-menu.png')
    await reveal(page, '.execution-section')
    await capture(page, '11-execution-metrics.png')

    const qualityButton = page.locator('.quality-banner button')
    await qualityButton.scrollIntoViewIfNeeded()
    if ((await qualityButton.getAttribute('aria-expanded')) !== 'true') await qualityButton.click()
    await reveal(page, '#quality-details')
    await capture(page, '12-data-quality.png')
  } finally {
    await browser.close()
  }
}

main().catch((error) => {
  process.stderr.write(`截图采集失败：${error instanceof Error ? error.message : String(error)}\n`)
  process.exitCode = 1
})
