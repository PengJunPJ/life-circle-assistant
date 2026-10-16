import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const project = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const { chromium } = createRequire(join(project, 'frontend/package.json'))('playwright-core')
const fixture = JSON.parse(readFileSync(join(project, 'docs/validation/reports/hongshan-haiyundonglu-20260921.json'), 'utf8'))
const report = { ...fixture, report_id: 'browser-source' }
let executionLedger = { id: 'browser-source-ledger', status: 'completed', budget: { route_pairs: 5000 }, usage: { route_pairs: 10 }, versions: { rules: 'v1' }, cost: { currency: 'CNY', estimated_total: 99, settled_total: null, status: 'estimate_only', settlement_version: 0, usage_sha256: 'c'.repeat(64), settlement_stale: false } }, settlements = []
report.execution_ledger = structuredClone(executionLedger)
const empty = { type: 'FeatureCollection', features: [] }
const point = { type: 'Feature', geometry: { type: 'Point', coordinates: [report.center.lng, report.center.lat] }, properties: { coordinate_system: 'BD-09', source: 'local_snapshot', point_id: 'observed-1', measured_minutes: 12 } }
const layers = { observed: { type: 'FeatureCollection', features: [point] }, observed_boundary: empty, estimated: empty, unresolved: empty, time_field: empty }
let workspace = { id: 'browser-workspace', revision: 1, created_at: '', updated_at: '', state: { center: { ...report.center, selection_method: 'coordinates' }, minutes: report.parameters.minutes, minutes_confirmed: true, mode: report.parameters.mode, categories: report.parameters.categories, visible_categories: report.parameters.categories, report_id: report.report_id, grid_id: null } }
let governance = { catalog_version: 1, catalog: { version: 1, records: [{ id: 'poi-1', name: '现场设施', category: 'market' }], source_records: [{ id: 'raw-1' }] }, reviews: [], observations: [], audit: [] }
let candidates = [], demand = [], turns = []
let uncertainCheckpoints = [{ call_key: 'a'.repeat(64), operation: 'walking_matrix', updated_at: '2026-10-14T09:00:00' }], resumed = false
const calls = [], failures = []
const review = { review_id: 'review-1', report_id: report.report_id, mode: 'rules', record_count: 1, candidate_count: 0, candidates_truncated: false, records: [{ id: 'poi-1', name: '现场设施' }], category_proposals: [{ record_id: 'poi-1', original_category: 'market', proposed_category: 'pharmacy', candidate_categories: ['pharmacy'], confidence: null, status: 'pending_human_review' }], entity_proposals: [], diagnostics: [], apply_policy: 'human_review_only', affects_original_report: false, disclosure: '审核提案，正式评分尚未更改' }
const combination = { report_id: report.report_id, before: { overall_score: 30, critical_zone_count: 5 }, after: { overall_score: 50, critical_zone_count: 3, service_areas: report.service_areas }, delta: { overall_score: 20 }, hypothetical_facilities: [] }
const browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' })
try {
  const context = await browser.newContext({ viewport: { width: 1600, height: 1000 } })
  const page = await context.newPage()
  page.setDefaultTimeout(15000)
  page.on('pageerror', error => failures.push(error.message))
  await page.addInitScript(() => {
    localStorage.setItem('life-circle:first-use-guide:v1', 'completed')
    localStorage.setItem('life-circle:workspace:v1', 'browser-workspace')
  })
  // 所有业务请求由有状态夹具接管。真实地图和模型不会收到本脚本的请求。
  await page.route('**/api/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname, body = request.postDataJSON()
    calls.push({ path, method: request.method(), body })
    let result
    if (request.method() === 'OPTIONS') return route.fulfill({ status: 204, headers: { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'GET,POST,OPTIONS', 'Access-Control-Allow-Headers': '*' } })
    if (path === '/api/map/config') result = { js_api_ak: '', configured: false }
    else if (path === '/api/map/status') result = { real_api_configured: false, real_api_probe_performed: false, provider_mode: 'mock' }
    else if (path === '/api/map/isochrone-capability') result = { configured: false, available: false, account_verified: false, pricing_verified: false }
    else if (path === '/api/workspaces/browser-workspace') result = workspace
    else if (path === '/api/analyze/browser-failed-task') result = { id: 'browser-failed-task', status: resumed ? 'completed' : 'failed', progress: 20, stage: 'walking', stage_label: '计算步行路线', request: report.parameters, ...(resumed ? { result: report } : { error: '中断调用待核对' }) }
    else if (path === '/api/executions/browser-failed-task/uncertain-checkpoints') result = { items: uncertainCheckpoints }
    else if (path === '/api/executions/browser-failed-task/reconcile') { assert.equal(body.call_key, 'a'.repeat(64)); assert.equal(body.reviewer, '计费复核员'); assert.equal(body.evidence, '提供方账单请求123已核对'); uncertainCheckpoints = []; result = { status: 'retry_authorized', budget_reset: false, disclosure: '授权重试，仍使用原预算' } }
    else if (path === '/api/executions/browser-source-ledger') result = executionLedger
    else if (path === '/api/executions/browser-source-ledger/settlements') {
      if (request.method() === 'GET') result = { items: settlements }
      else {
        assert.deepEqual(body, { amount_cny: '0.00', bill_reference: '提供方账单20261014', reviewer: '结算复核员', evidence: '提供方免费额度及本次执行全部调用归属已核验', expected_version: 0, expected_usage_sha256: 'c'.repeat(64), scope: 'execution_total' })
        result = { version: 1, amount_cny: 0, bill_reference: body.bill_reference, reviewer: body.reviewer, evidence: body.evidence, usage_sha256: body.expected_usage_sha256, created_at: '2026-10-14T10:00:00', scope: 'execution_total', currency: 'CNY' }
        settlements.push(result); executionLedger.cost = { ...executionLedger.cost, settled_total: 0, status: 'manually_reconciled', settlement_version: 1 }
      }
    }
    else if (path === '/api/analyze/browser-failed-task/resume') { assert.equal(uncertainCheckpoints.length, 0); resumed = true; result = { id: 'browser-failed-task', status: 'completed', progress: 100, stage: 'completed', stage_label: '已完成', result: report } }
    else if (path === '/api/workspaces/browser-workspace/state') { workspace = { ...workspace, revision: workspace.revision + 1, state: body.state }; result = workspace }
    else if (path === '/api/workspaces/browser-workspace/messages' && request.method() === 'GET') result = { items: turns }
    else if (path === '/api/workspaces/browser-workspace/messages') {
      workspace = { ...workspace, revision: workspace.revision + 1 }
      result = { id: `turn-${turns.length}`, workspace_id: workspace.id, revision: workspace.revision, request_id: body.request_id, status: 'completed', message: body.message, answer: '已切换独立空间证据', actions: [{ type: 'set_status_layers', layers: { scarcity: true, walking_timeout: true, unknown: true } }], created_at: '' }
      turns.push(result)
    }
    else if (path === '/api/reports/history') result = { items: [], total: 0 }
    else if (path === `/api/reports/${report.report_id}`) result = report
    else if (path === `/api/reports/${report.report_id}/governance`) result = governance
    else if (path.endsWith('/ai/semantic-review')) { governance.reviews = [structuredClone(review)]; result = governance.reviews[0] }
    else if (path.endsWith('/governance/decisions')) {
      assert.equal(body.expected_version, governance.catalog_version); assert.equal(body.reviewer, '浏览器复核员'); assert.ok(body.reason)
      governance.reviews[0].category_proposals[0].status = 'accepted'; governance.catalog_version += 1; result = governance
    }
    else if (path.endsWith('/observations')) { governance.observations = [{ id: 'observation-1', text: body.text, kind: 'closure', status: 'pending_human_review' }]; result = governance.observations[0] }
    else if (path.endsWith('/observations/observation-1/decision')) {
      assert.equal(body.facility_id, 'poi-1'); assert.equal(body.expected_version, governance.catalog_version)
      governance.observations[0].status = 'accepted'; governance.catalog_version += 1; result = governance
    }
    else if (path.endsWith('/experiments/active-sampling')) {
      assert.deepEqual(body, { route_pair_budget: 12, grid_size: 5, strategy: 'uniform' })
      result = { report_id: report.report_id, status: 'experimental', layers, external_route_pairs_used: 8, enabled_for_official_analysis: false, disclosure: '观测网格仅认证中心点' }
    }
    else if (path.endsWith('/planning/candidates')) { if (request.method() === 'POST') candidates = body.candidates; result = { items: candidates } }
    else if (path.endsWith('/planning/demand')) { if (request.method() === 'POST') demand = body.items; result = { items: demand } }
    else if (path.endsWith('/planning/optimize')) {
      assert.equal(body.minimum_population, 100); assert.equal(body.budget, 100000); assert.deepEqual(body.required_ids, ['parcel-A']); assert.deepEqual(body.category_limits, { pharmacy: { min: 1, max: 2 } }); assert.equal(demand[0].population, 100)
      combination.hypothetical_facilities = candidates
      result = { report_id: report.report_id, status: 'OPTIMAL', selected_candidate_ids: ['parcel-A'], selected_candidates: candidates, covered_grid_count: 2, total_cost: 50000, confirmed_population: 100, combination, pareto_solutions: [{ candidate_ids: ['parcel-A'], covered_grid_count: 2, total_cost: 50000 }], disclosure: '有限候选与核验覆盖内最优' }
    }
    else if (path.endsWith('/audience-report')) {
      assert.equal(body.audience, 'planner')
      result = { observations: ['<img src=x onerror=alert(1)>'], possible_causes: ['可能存在入口差异'], measures: ['核验现场入口'], verification_conditions: ['新增后复测'], norms: [{ title: '生活圈规范', text: '可信条文', source: '规范台账' }], citations: ['来源报告'], disclosure: '所有数据来自来源报告' }
    }
    else { failures.push(`未预期请求 ${request.method()} ${path}`); return route.fulfill({ status: 500, json: { detail: '验证夹具未配置此入口' }, headers: { 'Access-Control-Allow-Origin': '*' } }) }
    await route.fulfill({ json: result, headers: { 'Access-Control-Allow-Origin': '*' } })
  })
  await page.goto(process.env.COMPLETION_APP_URL || 'http://127.0.0.1:5173', { waitUntil: 'networkidle' })
  await page.getByRole('tab', { name: 'AI核验', exact: true }).click()
  const workbench = page.getByRole('region', { name: 'AI核验与规划工作台' })
  await workbench.getByRole('button', { name: '生成语义审核建议', exact: true }).click()
  await workbench.getByText('现场设施', { exact: true }).waitFor()
  await workbench.getByLabel('复核人', { exact: true }).fill('浏览器复核员'); await workbench.getByLabel('复核依据', { exact: true }).fill('已查现场登记台账')
  await workbench.getByRole('button', { name: '接纳', exact: true }).click()
  await workbench.getByText('已接纳', { exact: true }).waitFor()
  assert.equal(await workbench.getByRole('button', { name: '接纳', exact: true }).isDisabled(), true)
  await workbench.getByRole('button', { name: '现场观察', exact: true }).click()
  await workbench.getByLabel('现场观察', { exact: true }).fill('现场设施已关闭')
  await workbench.getByRole('button', { name: '提交待核验观察', exact: true }).click()
  await workbench.getByLabel('关联设施').selectOption('poi-1')
  await workbench.getByRole('button', { name: '核验接纳', exact: true }).click()
  await workbench.getByText('已接纳', { exact: true }).waitFor()
  await workbench.getByRole('button', { name: '主动补测', exact: true }).click()
  await workbench.getByLabel('路线对预算', { exact: true }).fill('12'); await workbench.getByLabel('采样网格边长', { exact: true }).fill('5'); await workbench.getByLabel('采样策略').selectOption('uniform')
  await workbench.getByRole('button', { name: '执行主动补测', exact: true }).click()
  await page.getByText('青绿点：真实观测', { exact: false }).waitFor()
  await workbench.getByText('地图原生等时圈能力核验', { exact: true }).click()
  await workbench.getByRole('button', { name: '读取能力状态', exact: true }).click()
  await workbench.getByText('配置未启用', { exact: false }).waitFor()
  assert.equal(await workbench.getByRole('button', { name: '实测当前中心能力', exact: true }).isDisabled(), true)
  await workbench.getByRole('button', { name: '组合规划', exact: true }).click()
  await workbench.getByLabel('候选编号', { exact: true }).fill('parcel-A'); await workbench.getByLabel('设施类别').selectOption('pharmacy')
  await workbench.getByLabel('成本（元）', { exact: true }).fill('50000'); await workbench.getByLabel('数据来源', { exact: true }).fill('可信地块台账A'); await workbench.getByLabel('已核验上述输入与来源', { exact: true }).check()
  await workbench.getByRole('button', { name: '登记可信候选', exact: true }).click()
  await workbench.getByText('可信候选已登记。', { exact: true }).waitFor()
  await workbench.getByText('可信网格人口台账', { exact: true }).click()
  await workbench.getByLabel('人口台账（JSON数组）', { exact: true }).fill(JSON.stringify([{ grid_id: 'r1c1', population: 100, source: '核验人口台账', verified: true }]))
  await workbench.getByRole('button', { name: '保存已核验人口台账', exact: true }).click()
  await workbench.getByText('已核验人口台账已保存。', { exact: true }).waitFor()
  await workbench.getByLabel('必须选择', { exact: true }).check(); await workbench.getByLabel('预算（元）', { exact: true }).fill('100000'); await workbench.getByLabel('最低受益人口', { exact: true }).fill('100')
  await workbench.getByText('各类别数量硬约束', { exact: true }).click(); await workbench.getByLabel('至少', { exact: true }).fill('1'); await workbench.getByLabel('至多', { exact: true }).fill('2')
  await workbench.getByRole('button', { name: '求解并整体复算组合', exact: true }).click()
  await workbench.getByText('综合评分：30 → 50', { exact: false }).waitFor(); await workbench.getByText('去重确认受益人口：100', { exact: true }).waitFor()
  await page.getByText('组合假设情景 · 1处新增设施', { exact: true }).waitFor()
  await workbench.getByRole('button', { name: '角色报告', exact: true }).click(); await workbench.getByLabel('报告受众').selectOption('planner')
  await workbench.getByRole('button', { name: '生成有依据的角色报告', exact: true }).click()
  await workbench.getByText('<img src=x onerror=alert(1)>', { exact: true }).waitFor(); assert.equal(await workbench.locator('img').count(), 0)
  await page.getByLabel('和生活圈助手对话', { exact: true }).fill('只看稀缺与步行超时图层'); await page.getByRole('button', { name: '发送', exact: true }).click()
  await page.locator('.conversation-answer').filter({ hasText: '已切换独立空间证据' }).waitFor()
  assert.equal(calls.some(item => item.path.endsWith('/isochrone-probe')), false)
  assert.equal(calls.some(item => item.path.endsWith('/planning/optimize')), true)
  await page.locator('.report-actions').getByRole('button', { name: '报告说明', exact: true }).click()
  const settlementReview = page.locator('.settlement-review')
  await settlementReview.locator('summary').first().click()
  await settlementReview.getByRole('button', { name: '读取账本与结算历史', exact: true }).click()
  await settlementReview.getByText('没有结算历史。', { exact: true }).waitFor()
  assert.equal(await settlementReview.getByLabel('本次执行全部费用（人民币元）', { exact: true }).inputValue(), '')
  await settlementReview.getByLabel('本次执行全部费用（人民币元）', { exact: true }).fill('0.00')
  await settlementReview.getByLabel('提供方账单编号或引用', { exact: true }).fill('提供方账单20261014')
  await settlementReview.getByLabel('结算复核人', { exact: true }).fill('结算复核员')
  await settlementReview.getByLabel('全部费用核验依据', { exact: true }).fill('提供方免费额度及本次执行全部调用归属已核验')
  assert.equal(await settlementReview.getByRole('button', { name: '记录人工结算', exact: true }).isDisabled(), true)
  await settlementReview.getByLabel('已人工核验提供方账单，金额覆盖本次执行全部费用', { exact: true }).check()
  await settlementReview.getByRole('button', { name: '记录人工结算', exact: true }).click()
  await settlementReview.getByText('已记录人工结算：0 CNY', { exact: true }).waitFor()
  assert.equal(await settlementReview.getByLabel('本次执行全部费用（人民币元）', { exact: true }).inputValue(), '')
  executionLedger.usage.route_pairs += 1
  executionLedger.cost = { ...executionLedger.cost, settled_total: null, settlement_stale: true, status: 'settlement_stale', usage_sha256: 'd'.repeat(64) }
  await settlementReview.getByRole('button', { name: '读取账本与结算历史', exact: true }).click()
  await settlementReview.getByText('旧结算已过时：', { exact: false }).waitFor()
  await page.getByText('旧结算已过时，待重新核对', { exact: true }).waitFor()
  workspace.state.analysis_task_id = 'browser-failed-task'
  await page.reload({ waitUntil: 'networkidle' })
  const checkpoints = page.locator('.conversation-workspace .checkpoint-review')
  await checkpoints.locator('summary').click(); await checkpoints.getByRole('button', { name: '检查未决调用', exact: true }).click()
  await checkpoints.getByText('walking_matrix', { exact: true }).waitFor()
  assert.equal(await checkpoints.getByRole('button', { name: '从原任务断点续算', exact: true }).isDisabled(), true)
  await checkpoints.getByLabel('计费复核人').fill('计费复核员'); await checkpoints.getByLabel('账单与日志核对依据').fill('提供方账单请求123已核对')
  assert.equal(await checkpoints.getByRole('button', { name: '记录核对并授权本项重试', exact: true }).isDisabled(), true)
  await checkpoints.getByLabel('已核对本次调用，允许可能再次计费的重试').check()
  await checkpoints.getByRole('button', { name: '记录核对并授权本项重试', exact: true }).click()
  await checkpoints.getByText('当前没有需要人工核对的未决调用。', { exact: true }).waitFor()
  assert.equal(calls.some(item => item.path.endsWith('/resume')), false)
  await checkpoints.getByRole('button', { name: '从原任务断点续算', exact: true }).click()
  await page.locator('.conversation-task span').filter({ hasText: '体检已完成' }).waitFor()
  assert.equal(calls.some(item => item.path.endsWith('/resume')), true)
  assert.deepEqual(failures, [])
  process.stdout.write('前端浏览器工作流：语义复核、现场观察、主动补测、原生能力门控、人口台账、硬约束组合、角色报告、对话图层、人工账单结算与过时披露、中断计费复核后显式续算全部通过。所有业务请求使用隔离夹具，未调用真实地图、大模型或账单。\n')
} catch (error) {
  process.stderr.write(JSON.stringify({ failures, recentRequests: calls.slice(-5) }, null, 2) + '\n')
  throw error
} finally {
  await browser.close()
}
