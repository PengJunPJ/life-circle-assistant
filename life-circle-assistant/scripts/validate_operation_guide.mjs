import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const project = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const { chromium } = createRequire(join(project, 'frontend/package.json'))('playwright-core')
const report = JSON.parse(readFileSync(join(project, 'docs/validation/reports/hongshan-haiyundonglu-20260921.json'), 'utf8'))
const browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' })
const baseSteps = [
  ['确认数据与地图状态', '[data-guide="source-status"]'],
  ['选择填写方式与体检位置', '[data-guide="analysis-center"]'],
  ['设置步行时间与分析精度', '[data-guide="analysis-parameters"]'],
  ['选择本次体检的设施', '[data-guide="analysis-facilities"]'],
  ['核对后手动开始体检', '[data-guide="run-analysis"]'],
  ['通过 AI 规划助手推进任务', '[data-guide="conversation"], [data-guide="conversation-launcher"]'],
  ['在地图上核对判定证据', '[data-guide="map-layers"]'],
]

try {
  for (const hasReport of [false, true]) for (const theme of ['light', 'dark']) for (const mobile of [false, true]) {
    const label = `${hasReport ? '有报告' : '无报告'}/${theme}/${mobile ? '手机' : '桌面'}`
    const context = await browser.newContext({ viewport: mobile ? { width: 375, height: 667 } : { width: 1440, height: 1000 } })
    const page = await context.newPage()
    page.setDefaultTimeout(10000)
    const errors = [], unexpected = [], mutations = []
    page.on('pageerror', error => errors.push(error.message))
    await page.addInitScript(({ theme }) => {
      localStorage.setItem('life-circle:first-use-guide:v1', 'completed')
      localStorage.setItem('life-circle:workspace:v1', 'guide-workspace')
      localStorage.setItem('life-circle:theme:v1', theme)
    }, { theme })
    let workspace = { id: 'guide-workspace', revision: 1, state: { center: { ...report.center, selection_method: 'coordinates' }, minutes: report.parameters.minutes, mode: report.parameters.mode, categories: report.parameters.categories, visible_categories: report.parameters.categories, report_id: hasReport ? report.report_id : null, grid_id: null } }
    // 拦截全部业务请求，导览验证不访问真实地图或模型。
    await page.route('**/api/**', async route => {
      const req = route.request(), path = new URL(req.url()).pathname
      const headers = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'GET,POST,OPTIONS', 'Access-Control-Allow-Headers': '*' }
      if (req.method() === 'OPTIONS') return route.fulfill({ status: 204, headers })
      let result
      if (path === '/api/map/config') result = { js_api_ak: '', configured: false }
      else if (path === '/api/map/status') result = { real_api_configured: false, provider_mode: 'mock' }
      else if (path === '/api/workspaces/guide-workspace') result = workspace
      else if (path === '/api/workspaces/guide-workspace/messages' && req.method() === 'GET') result = { items: [] }
      else if (path === '/api/workspaces/guide-workspace/state') { workspace = { ...workspace, revision: workspace.revision + 1, state: req.postDataJSON().state }; result = workspace }
      else if (path === '/api/reports/history') result = { items: [], total: 0, has_more: false }
      else if (path === `/api/reports/${report.report_id}` && req.method() === 'GET') result = report
      else { unexpected.push(`${req.method()} ${path}`); return route.fulfill({ status: 500, headers, json: { detail: '导览出现未预期请求' } }) }
      if (req.method() !== 'GET' && !path.endsWith('/state')) mutations.push(`${req.method()} ${path}`)
      return route.fulfill({ json: result, headers })
    })
    await page.goto(process.env.GUIDE_APP_URL || 'http://127.0.0.1:5180', { waitUntil: 'networkidle' })
    await page.getByText('已连接', { exact: true }).waitFor()
    // 保留“一句话填写”及隐藏助手的状态，避免定位到隐藏的自主设置或失效入口。
    // 手机端面板默认收起，先展开设置填写方式，再收起回地图作为导览前的原始状态。
    if (mobile) await page.getByRole('button', { name: '分析参数', exact: true }).click()
    await page.getByRole('tab', { name: '一句话填写', exact: true }).click()
    if (mobile) await page.getByRole('button', { name: '关闭分析参数面板并返回地图', exact: true }).click()
    await page.getByRole('button', { name: '隐藏AI规划助手', exact: true }).click()
    await page.getByRole('button', { name: '操作向导', exact: true }).click()
    const steps = [...baseSteps,
      [hasReport ? '先看概览与设施详情' : '报告生成后从这里阅读', hasReport ? '.report-tabs' : '.empty-report'],
      ...(hasReport ? [
        ['逐类核对设施覆盖与空间缺口', '#report-page-facilities .page-heading'],
        ['从改善建议走到假设模拟', '#report-page-recommendations .page-heading'],
      ] : []),
      [hasReport ? '用 AI 核验形成规划闭环' : '了解报告后的 AI 核验流程', hasReport ? '.completion-nav' : '.report-actions'],
      ...(hasReport ? [['核对数据质量、预算与版本', '.auxiliary-heading']] : []),
      ['查找历史并比较两份报告', '.history-title'],
      ...(hasReport ? [['按用途导出报告与空间数据', '.auxiliary-heading']] : []),
    ]
    async function checkStep([title, selector]) {
      await page.locator('.el-tour__title').filter({ hasText: title }).waitFor()
      // 等待遮罩开孔跟随新目标，而不只是卡片文案变化。
      await page.waitForFunction(selector => {
        const target = document.querySelector(selector), path = document.querySelector('.el-tour__hollow')?.getAttribute('d')
        if (!target || !path) return false
        const rect = target.getBoundingClientRect()
        const hole = path.match(/Z M([-\d.]+),([-\d.]+)/)
        return hole && rect.width > 0 && rect.height > 0 && Math.abs(Number(hole[1]) - (rect.left - 1)) < 2 && Math.abs(Number(hole[2]) - (rect.top - 8)) < 2
      }, selector)
      const box = await page.locator('.el-tour__content').boundingBox()
      const viewport = page.viewportSize()
      assert.ok(box && box.x >= -1 && box.y >= -1 && box.x + box.width <= viewport.width + 1 && box.y + box.height <= viewport.height + 1, `${label}/${title} 卡片超出屏幕 ${JSON.stringify(box)}`)
      await assert.doesNotReject(() => page.getByRole('button', { name: title === steps.at(-1)[0] ? '完成向导' : '下一步', exact: true }).click({ trial: true }))
    }
    for (let index = 0; index < steps.length; index++) {
      await checkStep(steps[index])
      if (index === 3) {
        await page.getByRole('button', { name: '上一步', exact: true }).click()
        await checkStep(steps[index - 1])
        await page.getByRole('button', { name: '下一步', exact: true }).click()
        await checkStep(steps[index])
      }
      await page.getByRole('button', { name: index === steps.length - 1 ? '完成向导' : '下一步', exact: true }).click()
    }
    await page.locator('.el-tour__content').waitFor({ state: 'hidden' })
    assert.equal(await page.evaluate(() => localStorage.getItem('life-circle:first-use-guide:v1')), 'completed')
    // 导览前手机端面板是收起的，退出后应恢复收起；展开后再核对填写方式。
    if (mobile) {
      assert.equal(await page.getByRole('button', { name: '分析参数', exact: true }).getAttribute('aria-expanded'), 'false', `${label} 退出后未恢复收起的手机面板`)
      await page.getByRole('button', { name: '分析参数', exact: true }).click()
    }
    assert.equal(await page.getByRole('tab', { name: '一句话填写', exact: true }).getAttribute('aria-selected'), 'true')
    if (mobile) await page.getByRole('button', { name: '关闭分析参数面板并返回地图', exact: true }).click()
    await page.getByRole('button', { name: '显示AI规划助手', exact: true }).waitFor()
    await page.getByRole('button', { name: '操作向导', exact: true }).click()
    await checkStep(steps[0])
    await page.keyboard.press('Escape')
    await page.locator('.el-tour__content').waitFor({ state: 'hidden' })
    assert.equal(await page.evaluate(() => localStorage.getItem('life-circle:first-use-guide:v1')), 'dismissed')
    assert.deepEqual(unexpected, [], `${label} 未预期请求`)
    assert.deepEqual(mutations, [], `${label} 不应触发业务写入`)
    assert.deepEqual(errors, [], `${label} 浏览器错误`)
    console.log(`通过：${label}，${steps.length} 步、前后切换、完成、重开、退出与状态恢复`)
    await context.close()
  }
} finally { await browser.close() }
