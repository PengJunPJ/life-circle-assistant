import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdtemp, readFile, rm } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { createServer } from 'node:net'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const project = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const { chromium } = createRequire(join(project, 'frontend/package.json'))('playwright-core')
const backendPort = 8107
const frontendPort = 5177
const api = `http://127.0.0.1:${backendPort}`
const appUrl = `http://127.0.0.1:${frontendPort}`
const errors = [], requests = [], directRequests = [], processes = []
let browser, temporaryDirectory, validationResult, phase = '启动隔离服务'
const delay = milliseconds => new Promise(resolveDelay => setTimeout(resolveDelay, milliseconds))

async function requireFreePort(port) {
  const server = createServer()
  await new Promise((resolveListen, reject) => {
    server.once('error', reject)
    server.listen(port, '127.0.0.1', resolveListen)
  })
  await new Promise(resolveClose => server.close(resolveClose))
}

function start(name, executable, args, cwd, env) {
  const child = spawn(executable, args, { cwd, env, stdio: ['ignore', 'pipe', 'pipe'] })
  const state = { name, child, logs: '' }
  for (const stream of [child.stdout, child.stderr]) stream.on('data', chunk => {
    state.logs = (state.logs + chunk.toString()).slice(-12000)
  })
  child.on('error', error => { state.error = error.message })
  processes.push(state)
  return state
}

async function waitForService(url, state) {
  const deadline = Date.now() + 30000
  while (Date.now() < deadline) {
    if (state.error || state.child.exitCode !== null) throw new Error(`${state.name}启动失败：${state.error || state.logs}`)
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(1000) })
      if (response.ok) return
    } catch { /* 服务尚未监听，继续在有界时间内检测。 */ }
    await delay(100)
  }
  throw new Error(`${state.name}未在30秒内就绪：${state.logs}`)
}

async function json(path, body) {
  const response = await fetch(`${api}/api${path}`, {
    ...(body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
    signal: AbortSignal.timeout(60000),
  })
  const payload = await response.json()
  directRequests.push({ method: body === undefined ? 'GET' : 'POST', path: `/api${path}`, status: response.status })
  assert.ok(response.ok, `${path}返回${response.status}：${JSON.stringify(payload)}`)
  return payload
}

function assertGeojsonHeaders(headers, reportId, coordinateSystem) {
  assert.match(headers.get('content-type'), /^application\/geo\+json(?:;|$)/)
  assert.equal(headers.get('x-report-id'), reportId)
  assert.equal(headers.get('x-coordinate-system'), coordinateSystem)
  const disposition = headers.get('content-disposition')
  assert.match(disposition, /^attachment; /)
  const encodedFilename = disposition.match(/filename\*=UTF-8''([^;]+)/)?.[1]
  assert.ok(encodedFilename, '导出使用UTF-8文件名')
  const filename = decodeURIComponent(encodedFilename)
  assert.match(filename, /\.geojson$/)
  assert.ok(!/[\/\\\r\n]/.test(filename), '下载名不能含路径或控制字符')
  return filename
}

async function geojsonExport(reportId, format, coordinateSystem) {
  const path = `/api/reports/${reportId}/exports/${format}`
  const response = await fetch(`${api}${path}`, { signal: AbortSignal.timeout(60000) })
  directRequests.push({ method: 'GET', path, status: response.status })
  assert.ok(response.ok, `${path}返回${response.status}：${await response.clone().text()}`)
  const filename = assertGeojsonHeaders(response.headers, reportId, coordinateSystem)
  return { document: await response.json(), filename }
}

function assertStandardGeometry(geometry) {
  if (!geometry) return
  assert.ok(!Object.hasOwn(geometry, 'crs') && !Object.hasOwn(geometry, 'bbox'), '转换后不能复用原CRS或bbox')
  if (geometry.type === 'GeometryCollection') {
    geometry.geometries.forEach(assertStandardGeometry)
    return
  }
  function coordinates(value) {
    assert.ok(Array.isArray(value) && value.length > 0)
    if (typeof value[0] === 'number') {
      assert.ok(value.every(Number.isFinite), '几何坐标必须有限')
      assert.ok(Math.abs(value[0]) <= 180 && Math.abs(value[1]) <= 90, '经纬度顺序和范围有效')
    } else value.forEach(coordinates)
  }
  coordinates(geometry.coordinates)
  function polygon(rings) {
    rings.forEach((ring, index) => {
      assert.ok(ring.length >= 4)
      assert.deepEqual(ring[0], ring.at(-1), '导出环保持闭合')
      const signedArea = ring.slice(0, -1).reduce((sum, point, i) => sum + point[0] * ring[i + 1][1] - ring[i + 1][0] * point[1], 0)
      assert.ok(index === 0 ? signedArea > 0 : signedArea < 0, '符合RFC 7946外环逆时针、孔洞顺时针')
    })
  }
  if (geometry.type === 'Polygon') polygon(geometry.coordinates)
  if (geometry.type === 'MultiPolygon') geometry.coordinates.forEach(polygon)
}

async function completedReport(taskId) {
  const deadline = Date.now() + 60000
  while (Date.now() < deadline) {
    const task = await json(`/analyze/${taskId}`)
    if (task.status === 'completed') { assert.ok(task.result?.report_id); return task.result }
    assert.notEqual(task.status, 'failed', `体检失败：${task.error}`)
    assert.notEqual(task.status, 'cancelled')
    await delay(100)
  }
  throw new Error('体检未在60秒内完成')
}

function responsePromise(page, ending) {
  return page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith(ending))
}

async function postFromButton(page, button, ending) {
  const response = responsePromise(page, ending)
  await button.click()
  const result = await response
  assert.ok(result.ok(), `${ending}返回${result.status()}：${await result.text()}`)
  return result.json()
}

try {
  await Promise.all([requireFreePort(backendPort), requireFreePort(frontendPort)])
  temporaryDirectory = await mkdtemp(join(tmpdir(), 'life-circle-http-smoke-'))
  // 显式值覆盖dotenv，空凭证也覆盖本机配置；绝不使用开发者数据库或线上服务。
  const env = {
    ...process.env,
    BAIDU_MAP_MODE: 'mock', BAIDU_MAP_AK: '', BAIDU_MAP_SECRET: '', BAIDU_MAP_QPS: '0',
    AMAP_VALIDATION_ENABLED: 'false', AMAP_WEB_SERVICE_KEY: '', AMAP_QPS: '0',
    LLM_ENABLED: 'false', LLM_API_KEY: '', LLM_BASE_URL: '', LLM_MODEL: '',
    SEMANTIC_EMBEDDING_ENABLED: 'false', SEMANTIC_EMBEDDING_API_KEY: '', SEMANTIC_EMBEDDING_BASE_URL: '', SEMANTIC_EMBEDDING_MODEL: '', SEMANTIC_EMBEDDING_MODEL_PATH: '',
    OBSERVATION_OCR_ENABLED: 'false', OBSERVATION_OCR_ENDPOINT: '', OBSERVATION_OCR_API_KEY: '',
    BAIDU_NATIVE_ISOCHRONE_ENABLED: 'false', LIFE_CIRCLE_NORMS_PATH: '',
    LIFE_CIRCLE_DATABASE_PATH: join(temporaryDirectory, 'smoke.sqlite'), LIFE_CIRCLE_SEED_WALKING_CACHE: '0',
    WALKING_QPS: '0', WALKING_MAX_RETRIES: '0',
    CORS_ALLOW_ORIGINS: appUrl,
    // 前端服务自行添加/api，这里必须是origin，不能重复拼接/api。
    VITE_API_BASE_URL: api, VITE_BAIDU_MAP_AK: '',
  }
  const backend = start('后端', join(project, 'backend/.venv/bin/python'), ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(backendPort)], join(project, 'backend'), env)
  await waitForService(`${api}/api/health`, backend)
  const frontend = start('前端', process.execPath, [join(project, 'frontend/node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', String(frontendPort), '--strictPort'], join(project, 'frontend'), env)
  await waitForService(appUrl, frontend)

  phase = '创建真实报告与工作区'
  const demo = await json('/demo/default')
  const parameters = { lng: demo.center.lng, lat: demo.center.lat, minutes: 15, mode: 'analysis', categories: ['pharmacy'], center_address: demo.center.address, center_selection_method: 'coordinates' }
  const task = await json('/analyze', parameters)
  const sourceReport = await completedReport(task.id)
  assert.equal(sourceReport.source, 'local_snapshot')
  const sourceBefore = await json(`/reports/${sourceReport.report_id}`)
  const workspace = await json('/workspaces', { state: { center: { lng: sourceReport.center.lng, lat: sourceReport.center.lat, address: sourceReport.center.address, selection_method: 'coordinates' }, minutes: 15, mode: 'analysis', categories: parameters.categories, visible_categories: parameters.categories, report_id: sourceReport.report_id } })
  browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' })
  const context = await browser.newContext({ viewport: { width: 1600, height: 1000 } })
  const page = await context.newPage()
  page.setDefaultTimeout(20000)
  page.on('pageerror', error => errors.push(`页面错误：${error.message}`))
  page.on('requestfailed', request => errors.push(`请求失败：${request.method()} ${request.url()} ${request.failure()?.errorText}`))
  page.on('request', request => {
    const url = new URL(request.url())
    if (!['data:', 'blob:'].includes(url.protocol) && ![api, appUrl].includes(url.origin)) errors.push(`未允许的外部请求：${request.url()}`)
  })
  page.on('response', response => {
    const url = new URL(response.url())
    if (url.origin === api && url.pathname.startsWith('/api/')) {
      requests.push({ method: response.request().method(), path: url.pathname, status: response.status() })
      if (response.status() >= 400) errors.push(`接口错误：${response.status()} ${url.pathname}`)
    }
  })
  await page.addInitScript(id => {
    localStorage.setItem('life-circle:first-use-guide:v1', 'completed')
    localStorage.setItem('life-circle:workspace:v1', id)
  }, workspace.id)
  // 不调用page.route/context.route，浏览器直接访问真实应用与后端。
  await page.goto(appUrl, { waitUntil: 'networkidle' })
  await page.getByRole('tab', { name: 'AI核验', exact: true }).click()
  const workbench = page.getByRole('region', { name: 'AI核验与规划工作台' })

  phase = '语义审核、驳回与新报告重算'
  const review = await postFromButton(page, workbench.getByRole('button', { name: '生成语义审核建议', exact: true }), '/ai/semantic-review')
  assert.ok(review.category_proposals.length > 0)
  assert.ok(review.category_proposals.every(item => item.proposed_category === null), '关闭模型时不伪造模型分类')
  await workbench.getByLabel('复核人', { exact: true }).fill('离线链路复核员')
  await workbench.getByLabel('复核依据', { exact: true }).fill('本次只验证真实HTTP驳回闭环，不改变类别')
  const rejected = await postFromButton(page, workbench.getByRole('button', { name: '驳回', exact: true }).first(), '/governance/decisions')
  assert.equal(rejected.target.category_proposals[0].status, 'rejected')
  await workbench.getByText('已驳回', { exact: false }).waitFor()
  const recomputed = await postFromButton(page, workbench.getByRole('button', { name: '按当前审核目录正式重算', exact: true }), '/governance/recompute')
  assert.notEqual(recomputed.report_id, sourceReport.report_id)
  assert.equal(recomputed.report.summary.score, sourceReport.summary.score)
  const report = recomputed.report
  const sourceAfter = await json(`/reports/${sourceReport.report_id}`)
  assert.deepEqual(sourceAfter, sourceBefore, '审核目录重算不能修改旧报告')
  await page.getByRole('tab', { name: 'AI核验', exact: true }).click()
  await workbench.getByRole('button', { name: '刷新目录', exact: true }).click()
  await workbench.getByText(/目录版本\s+1/).waitFor()

  phase = '居民文字观察提交与驳回'
  await workbench.getByRole('button', { name: '现场观察', exact: true }).click()
  await workbench.getByLabel('复核人', { exact: true }).fill('离线链路复核员')
  await workbench.getByLabel('复核依据', { exact: true }).fill('本次验证文字观察驳回，不接纳未经核验的停业信息')
  await workbench.getByLabel('现场观察', { exact: true }).fill('离线冒烟：疑似药店关闭，未经现场核验')
  const observation = await postFromButton(page, workbench.getByRole('button', { name: '提交待核验观察', exact: true }), '/observations')
  assert.equal(observation.affects_official_facts, false)
  await workbench.getByRole('button', { name: '驳回观察', exact: true }).waitFor()
  const observationDecision = await postFromButton(page, workbench.getByRole('button', { name: '驳回观察', exact: true }), `/observations/${observation.id}/decision`)
  assert.equal(observationDecision.target.status, 'rejected')
  await workbench.getByText('已驳回', { exact: true }).waitFor()

  phase = '主动补测与原生能力门控'
  await workbench.getByRole('button', { name: '主动补测', exact: true }).click()
  await workbench.getByLabel('路线对预算', { exact: true }).fill('12')
  await workbench.getByLabel('采样网格边长', { exact: true }).fill('5')
  const sampling = await postFromButton(page, workbench.getByRole('button', { name: '执行主动补测', exact: true }), '/experiments/active-sampling')
  assert.equal(sampling.enabled_for_official_analysis, false)
  assert.equal(sampling.external_route_pairs_used, 0)
  assert.ok(sampling.layers.unresolved.features.length > 0, '离线采样未知保留为未决')
  await page.getByText('青绿点：真实观测', { exact: false }).waitFor()
  await workbench.getByText('地图原生等时圈能力核验', { exact: true }).click()
  await workbench.getByRole('button', { name: '读取能力状态', exact: true }).click()
  await workbench.getByText('配置未启用', { exact: false }).waitFor()
  assert.equal(await workbench.getByRole('button', { name: '实测当前中心能力', exact: true }).isDisabled(), true)

  phase = '可信候选导入与组合整体复算'
  await workbench.getByRole('button', { name: '组合规划', exact: true }).click()
  await workbench.getByLabel('候选编号', { exact: true }).fill('HTTP-PARCEL-A')
  await workbench.locator('label').filter({ hasText: /^设施类别/ }).locator('select').selectOption('pharmacy')
  await workbench.getByLabel('经度（BD-09）', { exact: true }).fill(String(report.center.lng))
  await workbench.getByLabel('纬度（BD-09）', { exact: true }).fill(String(report.center.lat))
  await workbench.getByLabel('成本（元）', { exact: true }).fill('5000')
  await workbench.getByLabel('数据来源', { exact: true }).fill('离线浏览器测试候选，仅验证输入链路')
  await workbench.getByLabel('已核验上述输入与来源', { exact: true }).check()
  await postFromButton(page, workbench.getByRole('button', { name: '登记可信候选', exact: true }), '/planning/candidates')
  await workbench.getByText('可信候选已登记。', { exact: true }).waitFor()
  await workbench.getByLabel('必须选择', { exact: true }).check()
  await workbench.getByLabel('预算（元）', { exact: true }).fill('10000')
  const optimization = await postFromButton(page, workbench.getByRole('button', { name: '求解并整体复算组合', exact: true }), '/planning/optimize')
  assert.deepEqual(optimization.selected_candidate_ids, ['HTTP-PARCEL-A'])
  assert.equal(optimization.constraint_violations, 0)
  assert.equal(optimization.combination.before.overall_score, report.summary.score)
  assert.equal(optimization.combination.after.overall_score, null)
  assert.equal(optimization.combination.delta.overall_score, null)
  await workbench.getByText(`综合评分：${report.summary.score ?? '未知'} → 未知`, { exact: false }).waitFor()
  await page.getByText('组合假设情景 · 1处新增设施', { exact: true }).waitFor()

  phase = '规范角色报告与对话独立图层'
  await workbench.getByRole('button', { name: '角色报告', exact: true }).click()
  const audienceReports = []
  for (const role of ['resident', 'planner']) {
    await workbench.locator('label').filter({ hasText: /^报告受众/ }).locator('select').selectOption(role)
    await workbench.getByLabel('关注问题', { exact: true }).fill('设施步行可达性、盲区、评分的依据与适用范围')
    const audience = await postFromButton(page, workbench.getByRole('button', { name: '生成有依据的角色报告', exact: true }), '/audience-report')
    assert.equal(audience.audience, role)
    assert.equal(audience.report_id, report.report_id)
    assert.ok(audience.citations.length > 0)
    assert.ok(audience.norms.every(item => item.scope === '项目规则' && item.status === 'verified_project_rule'))
    for (const citation of audience.citations) {
      assert.equal(citation.version, 'repository-current')
      assert.match(citation.sha256, /^[a-f0-9]{64}$/)
      assert.ok(audience.norms.some(item => item.chunk_id === citation.chunk_id && item.source === citation.source && item.version === citation.version && item.sha256 === citation.sha256))
    }
    assert.deepEqual(audience.source_report_quality, report.data_quality)
    audienceReports.push({ role, citations: audience.citations.length })
  }
  await workbench.getByText('待核验条件', { exact: true }).waitFor()
  await page.getByLabel('和生活圈助手对话', { exact: true }).fill('只看1公里稀缺与步行超时图层')
  const turn = await postFromButton(page, page.getByRole('button', { name: '发送', exact: true }), '/messages')
  const layerAction = turn.actions.find(item => item.type === 'set_status_layers')
  assert.ok(layerAction)
  assert.equal(layerAction.layers.scarcity, true)
  assert.equal(layerAction.layers.walking_timeout, true)
  assert.equal(layerAction.layers.unknown, false)
  await page.getByRole('button', { name: '图层', exact: true }).click()
  await page.getByLabel('1公里设施稀缺', { exact: true }).waitFor()
  assert.equal(await page.getByLabel('1公里设施稀缺', { exact: true }).isChecked(), true)
  assert.equal(await page.getByLabel('已核验步行超时', { exact: true }).isChecked(), true)
  assert.equal(await page.getByLabel('证据不足区域', { exact: true }).isChecked(), false)
  // 等待本轮工作区落盘，确保没有卸载取消请求混入通过断言。
  await page.waitForLoadState('networkidle')
  const saved = await json(`/workspaces/${workspace.id}`)
  assert.equal(saved.state.report_id, report.report_id)
  assert.equal(saved.state.status_layers.scarcity, true)
  assert.equal(saved.state.status_layers.walking_timeout, true)
  assert.equal(requests.some(item => item.path.endsWith('/isochrone-probe')), false)
  assert.ok(requests.some(item => item.path.endsWith('/planning/optimize')))

  phase = '旧BD-09与标准WGS84导出和实际菜单下载'
  const reportBeforeExports = await json(`/reports/${report.report_id}`)
  const legacyExport = await geojsonExport(report.report_id, 'geojson', 'BD-09')
  const standardExport = await geojsonExport(report.report_id, 'geojson-wgs84', 'WGS84')
  const legacy = legacyExport.document, standard = standardExport.document
  assert.equal(legacy.type, 'FeatureCollection')
  assert.equal(legacy.coordinate_system, 'BD-09')
  assert.deepEqual(legacy.analysis_center, reportBeforeExports.analysis_center || reportBeforeExports.center)
  assert.equal(standard.type, 'FeatureCollection')
  assert.equal(standard.coordinate_system, 'WGS84')
  assert.equal(standard.source_coordinate_system, 'BD-09')
  assert.equal(standard.parameters_coordinate_system, 'BD-09')
  assert.equal(standard.analysis_center.coordinate_system, 'WGS84')
  assert.equal(standard.analysis_center.source_coordinate_system, 'BD-09')
  assert.equal(standard.conversion_precision.approximate, true)
  assert.equal(standard.conversion_precision.survey_grade, false)
  assert.equal(standard.conversion_precision.verified_accuracy_m, null)
  assert.ok(Math.abs(standard.analysis_center.lng - legacy.analysis_center.lng) > 0.001, '上海样本已转换坐标，不能仅换标签')
  assert.ok(Math.abs(standard.analysis_center.lat - legacy.analysis_center.lat) > 0.001)
  for (const document of [legacy, standard]) {
    assert.equal(document.report_id, report.report_id)
    assert.deepEqual(document.parameters, reportBeforeExports.request || reportBeforeExports.parameters)
    assert.deepEqual(document.data_quality, reportBeforeExports.data_quality)
    assert.ok(document.features.length > 0)
  }
  assert.equal(standard.features.length, legacy.features.length)
  assert.ok(!Object.hasOwn(standard, 'crs') && !Object.hasOwn(standard, 'bbox'))
  assert.ok(legacy.features.every(feature => feature.properties.coordinate_system === 'BD-09'))
  for (const feature of standard.features) {
    assert.equal(feature.properties.coordinate_system, 'WGS84')
    assert.equal(feature.properties.source_coordinate_system, 'BD-09')
    assertStandardGeometry(feature.geometry)
  }
  await page.getByRole('navigation', { name: '报告工具', exact: true }).getByRole('button', { name: '导出', exact: true }).click()
  const exportMenu = page.getByRole('region', { name: '导出体检数据', exact: true })
  const downloadPending = page.waitForEvent('download')
  const exportResponsePending = page.waitForResponse(response => response.request().method() === 'GET' && new URL(response.url()).pathname === `/api/reports/${report.report_id}/exports/geojson-wgs84`)
  await exportMenu.getByRole('button', { name: /标准 GeoJSON（WGS84）/ }).click()
  const download = await downloadPending
  const exportResponse = await exportResponsePending
  assert.ok(exportResponse.ok())
  const downloadFilename = assertGeojsonHeaders(new Headers(await exportResponse.allHeaders()), report.report_id, 'WGS84')
  assert.equal(download.suggestedFilename(), downloadFilename, '前端正确读取跨域UTF-8下载名')
  assert.equal(await download.failure(), null)
  const downloadPath = join(temporaryDirectory, 'download.geojson')
  await download.saveAs(downloadPath)
  assert.deepEqual(JSON.parse(await readFile(downloadPath, 'utf8')), standard, '实际下载内容等于标准出口响应')
  await exportMenu.getByText(`已开始下载：${downloadFilename}`, { exact: true }).waitFor()
  assert.deepEqual(await json(`/reports/${report.report_id}`), reportBeforeExports, '两种出口和菜单下载均不能改变持久化报告')

  phase = '终态执行费用结算与追加历史'
  const executionId = sourceReport.task_id || task.id
  const ledgerBefore = await json(`/executions/${executionId}`)
  assert.equal(ledgerBefore.status, 'completed')
  const settlement = await json(`/executions/${executionId}/settlements`, {
    amount_cny: '12.34', bill_reference: '离线测试编号，非真实提供方账单',
    reviewer: '离线链路复核员', evidence: '仅验证合成执行总账单写入链路，金额不代表本次实际费用或账户账单。',
    expected_version: ledgerBefore.cost.settlement_version,
    expected_usage_sha256: ledgerBefore.cost.usage_sha256, scope: 'execution_total',
  })
  assert.equal(settlement.version, 1)
  const ledgerAfter = await json(`/executions/${executionId}`)
  assert.equal(ledgerAfter.cost.settled_total, 12.34)
  assert.equal(ledgerAfter.cost.status, 'manually_reconciled')
  const correction = await json(`/executions/${executionId}/settlements`, {
    amount_cny: '0', bill_reference: '离线测试编号追加更正，非真实提供方账单',
    reviewer: '离线链路复核员', evidence: '合成费用更正验证；保留前一记录，仅追加零金额新版本，不代表已核验真实账单。',
    expected_version: ledgerAfter.cost.settlement_version,
    expected_usage_sha256: ledgerAfter.cost.usage_sha256, scope: 'execution_total',
  })
  assert.equal(correction.version, 2)
  const history = await json(`/executions/${executionId}/settlements`)
  assert.deepEqual(history.items.map(item => item.amount_cny), [12.34, 0])
  assert.equal((await json(`/executions/${executionId}`)).cost.settled_total, 0)
  assert.deepEqual(await json(`/reports/${sourceReport.report_id}`), sourceBefore, '所有核验、组合和结算链路均不得覆盖原报告')
  assert.deepEqual(errors, [])
  validationResult = { status: 'passed', mode: 'real_http_offline', source_report_id: sourceReport.report_id, recomputed_report_id: report.report_id, browser_api_responses: requests.length, direct_api_responses: directRequests.length, page_errors: 0, failed_requests: 0, outside_service_requests: 0, combination_scores: { before: optimization.combination.before.overall_score, after: optimization.combination.after.overall_score }, audience_reports: audienceReports, geojson_exports: { legacy_coordinate_system: legacy.coordinate_system, standard_coordinate_system: standard.coordinate_system, parameters_coordinate_system: standard.parameters_coordinate_system, approximate_conversion: standard.conversion_precision.approximate, features: standard.features.length, menu_download_verified: true, original_report_immutable: true }, settlement_history_amounts: history.items.map(item => item.amount_cny), workflows: ['semantic_reject', 'catalog_recompute_immutable_source', 'resident_observation_reject', 'active_sampling_unknown', 'native_capability_disabled', 'trusted_candidate_portfolio_unknown_score', 'grounded_resident_report', 'grounded_planner_report', 'conversation_independent_layers', 'legacy_and_standard_geojson_headers', 'wgs84_export_menu_download', 'synthetic_settlement_append_only_correction'], disclosure: '真实前后端HTTP与浏览器链路；地图采用本地快照且所有外部AI服务关闭，结算金额为合成测试，结果不代表真实账户或模型效果。' }
} catch (error) {
  process.stderr.write(JSON.stringify({ phase, errors, recentRequests: requests.slice(-12), recentDirectRequests: directRequests.slice(-12), serverLogs: processes.map(item => ({ name: item.name, logs: item.logs.slice(-4000) })) }, null, 2) + '\n')
  throw error
} finally {
  if (browser) await browser.close()
  for (const state of processes.reverse()) {
    if (state.child.exitCode === null && state.child.signalCode === null) {
      const exited = new Promise(resolveExit => state.child.once('exit', resolveExit))
      state.child.kill('SIGTERM')
      await Promise.race([exited, delay(4000)])
      if (state.child.exitCode === null && state.child.signalCode === null) { state.child.kill('SIGKILL'); await exited }
    }
  }
  if (temporaryDirectory) await rm(temporaryDirectory, { recursive: true, force: true })
  if (validationResult) {
    await Promise.all([requireFreePort(backendPort), requireFreePort(frontendPort)])
    validationResult.cleanup = { services_stopped: true, ports_released: true, temporary_database_removed: true, browser_closed: true }
  }
}
process.stdout.write(JSON.stringify(validationResult, null, 2) + '\n')
