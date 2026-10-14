// @vitest-environment jsdom
import { readFileSync } from 'node:fs'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App.vue'
import AnalysisControls from './components/AnalysisControls.vue'
import MapStage from './components/MapStage.vue'
import ConversationWorkspace from './components/ConversationWorkspace.vue'
import { downloadReportExport, getAnalysisTask, getHistoricalReport, searchAddressCandidates, waitForAnalysis } from './services/analysisApi'
import { createWorkspace, getWorkspace, getWorkspaceMessages, sendWorkspaceMessage, updateWorkspace } from './services/workspaceApi'
import type { ConversationTurn, Workspace, WorkspaceState } from './types/workspace'
import type { Report } from './types/report'
import { WORKSPACE_STORAGE_KEY } from './composables/useConversation'
import { DEFAULT_STATUS_LAYERS } from './types/completion'

vi.mock('./services/workspaceApi', async importOriginal => ({ ...await importOriginal<typeof import('./services/workspaceApi')>(), createWorkspace: vi.fn(), getWorkspace: vi.fn(), getWorkspaceMessages: vi.fn(), sendWorkspaceMessage: vi.fn(), updateWorkspace: vi.fn() }))
vi.mock('./services/analysisApi', () => ({ fetchMapStatus: vi.fn().mockResolvedValue({ real_api_configured: false }), getHistoricalReport: vi.fn(), fetchReportHistory: vi.fn().mockResolvedValue({ items: [], total: 0 }), searchAddressCandidates: vi.fn(), probeMapApi: vi.fn(), createAnalysis: vi.fn(), waitForAnalysis: vi.fn(), cancelAnalysisTask: vi.fn(), retryAnalysisTask: vi.fn(), getAnalysisTask: vi.fn(), downloadReportExport: vi.fn() }))
vi.mock('element-plus/es/components/message/index', () => ({ default: { success: vi.fn(), error: vi.fn() } }))
const fixture: Report = JSON.parse(readFileSync('../docs/validation/reports/hongshan-haiyundonglu-20260921.json', 'utf8'))
let server: Workspace
const turn = (patch: Partial<ConversationTurn> = {}): ConversationTurn => ({ id: 'one', workspace_id: 'workspace-one', revision: 2, request_id: 'one', status: 'completed', message: '只看菜市场', answer: '已切换地图图层', actions: [], created_at: '', ...patch })
const reply = (patch: Partial<ConversationTurn> = {}) => async () => {
  server = { ...server, revision: server.revision + 1 }
  return turn({ ...patch, revision: server.revision })
}

describe('对话驱动同一个地图和公共表单', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    localStorage.clear()
    localStorage.setItem('life-circle:first-use-guide:v1', 'completed')
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: false }))
    vi.mocked(createWorkspace).mockImplementation(async state => { server = { id: 'workspace-one', revision: 1, state, created_at: '', updated_at: '' }; return server })
    vi.mocked(getWorkspace).mockImplementation(async () => server)
    vi.mocked(getWorkspaceMessages).mockResolvedValue({ items: [] })
    vi.mocked(updateWorkspace).mockImplementation(async (_id, revision, state) => { server = { ...server, revision: revision + 1, state }; return server })
    vi.mocked(searchAddressCandidates).mockResolvedValue([{ lng: 113.501, lat: 23.11, address: '候选一', source: 'local_snapshot', provider: 'baidu' }, { lng: 113.502, lat: 23.12, address: '候选二', source: 'local_snapshot', provider: 'baidu' }])
    vi.mocked(getHistoricalReport).mockResolvedValue(structuredClone(fixture))
  })

  it('对话标准GeoJSON动作调用WGS84出口并保留地图与报告原坐标', async () => {
    localStorage.setItem(WORKSPACE_STORAGE_KEY, 'workspace-one')
    server = { id: 'workspace-one', revision: 1, state: { center: { ...fixture.center, selection_method: 'coordinates' }, minutes: fixture.parameters.minutes, mode: fixture.parameters.mode, categories: fixture.parameters.categories, report_id: fixture.report_id, grid_id: null, visible_categories: fixture.parameters.categories }, created_at: '', updated_at: '' }
    const wrapper = shallowMount(App); await flushPromises()
    const mapReport = JSON.parse(JSON.stringify(wrapper.getComponent(MapStage).props('report')))
    vi.mocked(sendWorkspaceMessage).mockImplementation(reply({ actions: [{ type: 'download_report', report_id: fixture.report_id, format: 'geojson-wgs84' }] }))
    wrapper.getComponent(ConversationWorkspace).vm.$emit('send', '导出标准GeoJSON WGS84'); await flushPromises()
    expect(downloadReportExport).toHaveBeenCalledWith(fixture.report_id, 'geojson-wgs84')
    expect(downloadReportExport).toHaveBeenCalledTimes(1)
    expect(wrapper.getComponent(MapStage).props('report')).toEqual(mapReport)
    expect(server.state.center?.lng).toBe(fixture.center.lng); expect(server.state.report_id).toBe(fixture.report_id)
    wrapper.unmount()
  })

  it('刷新保留未确认的分钟状态，不能把遗留分钟当作有效参数', async () => {
    localStorage.setItem(WORKSPACE_STORAGE_KEY, 'workspace-one')
    server = { id: 'workspace-one', revision: 1, state: { center: null, minutes: 15, minutes_confirmed: false, mode: 'analysis', categories: ['market'], report_id: null, grid_id: null, visible_categories: ['market'] }, created_at: '', updated_at: '' }
    const wrapper = shallowMount(App)
    await flushPromises()
    expect(wrapper.getComponent(AnalysisControls).props('minutesValid')).toBe(false)
    expect(wrapper.getComponent(ConversationWorkspace).props('context')).toContain('时间待确认')
    wrapper.getComponent(AnalysisControls).vm.$emit('update:minutes', 20)
    vi.mocked(sendWorkspaceMessage).mockImplementation(reply())
    wrapper.getComponent(ConversationWorkspace).vm.$emit('send', '检查参数')
    await flushPromises()
    expect(server.state.minutes).toBe(20)
    expect(server.state.minutes_confirmed).toBe(true)
    wrapper.unmount()
  })

  it('聊天填参复用地址候选和分钟控件，多候选确认前state中心为空', async () => {
    const wrapper = shallowMount(App)
    await flushPromises()
    vi.mocked(sendWorkspaceMessage).mockImplementation(async () => {
      server = { ...server, revision: 2, state: { ...server.state, center: null, minutes: 20, categories: ['market'], report_id: null } }
      return turn({ actions: [{ type: 'apply_parameters', draft: { address: '同名社区', use_current_center: false, minutes: 20, mode: 'analysis', categories: ['market'], defaulted_fields: [] } }] })
    })
    wrapper.getComponent(ConversationWorkspace).vm.$emit('send', '同名社区20分钟只查菜市场')
    await flushPromises()
    const controls = wrapper.getComponent(AnalysisControls)
    expect(controls.props('minutes')).toBe(20)
    expect(controls.props('candidates')).toHaveLength(2)
    expect(controls.props('locationPending')).toBe(true)
    expect(server.state.center).toBeNull()
    controls.vm.$emit('select-candidate', controls.props('candidates')[1])
    wrapper.getComponent(ConversationWorkspace).vm.$emit('send', '解释当前参数')
    vi.mocked(sendWorkspaceMessage).mockImplementation(reply({ id: 'two' }))
    await flushPromises()
    expect(server.state.center?.lng).toBe(113.502)
    wrapper.unmount()
  })

  it('持久报告恢复地图，再用聊天切换图层并定位真实网格', async () => {
    localStorage.setItem(WORKSPACE_STORAGE_KEY, 'workspace-one')
    const gridId = fixture.service_areas.features[0]!.properties.grid_id
    const category = fixture.service_areas.features[0]!.properties.category
    const state: WorkspaceState = { center: { ...fixture.center, selection_method: 'default' }, minutes: fixture.parameters.minutes, mode: fixture.parameters.mode, categories: fixture.parameters.categories, report_id: fixture.report_id, grid_id: gridId, visible_categories: fixture.parameters.categories }
    server = { id: 'workspace-one', revision: 1, state, created_at: '', updated_at: '' }
    const wrapper = shallowMount(App)
    await flushPromises()
    expect(wrapper.getComponent(MapStage).props('report')?.report_id).toBe(fixture.report_id)
    expect(wrapper.getComponent(MapStage).props('focusGridId')).toBe(gridId)
    vi.mocked(sendWorkspaceMessage).mockImplementation(reply({ actions: [{ type: 'set_layers', categories: [category] }, { type: 'focus_grid', grid_id: gridId }] }))
    wrapper.getComponent(ConversationWorkspace).vm.$emit('send', '只看这个区域的设施')
    await flushPromises()
    expect(wrapper.getComponent(MapStage).props('visibleCategories')).toEqual([category])
    expect(wrapper.getComponent(MapStage).props('focusGridId')).toBe(gridId)
    expect(server.state.visible_categories).toEqual([category])
    wrapper.getComponent(AnalysisControls).vm.$emit('update:minutes', fixture.parameters.minutes === 20 ? 10 : 20)
    wrapper.getComponent(ConversationWorkspace).vm.$emit('send', '重新核验')
    vi.mocked(sendWorkspaceMessage).mockImplementation(reply({ id: 'three' }))
    await flushPromises()
    expect(server.state.report_id).toBeNull()
    expect(server.state.grid_id).toBeNull()
    expect(wrapper.getComponent(ConversationWorkspace).props('context')).toContain('待重新体检')
    wrapper.unmount()
  })

  it('刷新恢复已完成的后台任务并绑定真实报告；删减分析类别解除旧报告和图层绑定', async () => {
    localStorage.setItem(WORKSPACE_STORAGE_KEY, 'workspace-one')
    server = { id: 'workspace-one', revision: 1, state: { center: { ...fixture.center, selection_method: 'coordinates' }, minutes: fixture.parameters.minutes, mode: fixture.parameters.mode, categories: fixture.parameters.categories, report_id: null, grid_id: null, visible_categories: fixture.parameters.categories, analysis_task_id: 'task' }, created_at: '', updated_at: '' }
    vi.mocked(getAnalysisTask).mockResolvedValue({ id: 'task', status: 'completed', progress: 100, stage: 'completed', stage_label: '已完成', request: fixture.parameters, result: fixture })
    vi.mocked(waitForAnalysis).mockResolvedValue(fixture)
    const wrapper = shallowMount(App)
    await flushPromises()
    expect(wrapper.getComponent(MapStage).props('report')?.report_id).toBe(fixture.report_id)
    expect(wrapper.getComponent(ConversationWorkspace).props('task')?.status).toBe('completed')
    wrapper.getComponent(AnalysisControls).vm.$emit('update:analysis-categories', ['market'])
    vi.mocked(sendWorkspaceMessage).mockImplementation(reply())
    wrapper.getComponent(ConversationWorkspace).vm.$emit('send', '查看当前参数')
    await flushPromises()
    expect(server.state.analysis_task_id).toBeNull()
    expect(server.state.report_id).toBeNull()
    expect(server.state.visible_categories).toEqual(['market'])
    wrapper.unmount()
  })
  it('共享状态恢复独立证据图层，对话动作切换并持久保存，未知类别不会被误关', async () => {
    localStorage.setItem(WORKSPACE_STORAGE_KEY, 'workspace-one')
    server = { id: 'workspace-one', revision: 1, state: { center: { ...fixture.center, selection_method: 'coordinates' }, minutes: fixture.parameters.minutes, mode: fixture.parameters.mode, categories: fixture.parameters.categories, report_id: fixture.report_id, grid_id: null, visible_categories: fixture.parameters.categories, status_layers: { ...DEFAULT_STATUS_LAYERS, normal: false, scarcity: true } }, created_at: '', updated_at: '' }
    const wrapper = shallowMount(App); await flushPromises()
    expect(wrapper.getComponent(MapStage).props('statusLayers')).toEqual(expect.objectContaining({ scarcity: true, walking_timeout: false, unknown: true }))
    vi.mocked(sendWorkspaceMessage).mockImplementation(reply({ actions: [{ type: 'set_status_layers', layers: { scarcity: false, walking_timeout: true, gap_groups: true, unknown: false } }] }))
    wrapper.getComponent(ConversationWorkspace).vm.$emit('send', '只看核验步行超时和缺口片区'); await flushPromises()
    expect(wrapper.getComponent(MapStage).props('statusLayers')).toEqual(expect.objectContaining({ scarcity: false, walking_timeout: true, gap_groups: true, unknown: false }))
    expect(server.state.status_layers).toEqual(expect.objectContaining({ walking_timeout: true, gap_groups: true, unknown: false }))
    wrapper.unmount()
  })
  it('对话地址候选进入公共选址控件，确认后清空候选并用新位置续接工作台', async () => {
    const wrapper = shallowMount(App); await flushPromises()
    const items = [{ lng: 113.501, lat: 23.11, address: '同名地点一' }, { lng: 113.502, lat: 23.12, address: '同名地点二' }]
    vi.mocked(sendWorkspaceMessage).mockImplementation(reply({ actions: [{ type: 'show_address_candidates', items }] }))
    wrapper.getComponent(ConversationWorkspace).vm.$emit('send', '查询同名地点'); await flushPromises()
    expect(wrapper.getComponent(AnalysisControls).props('candidates')).toHaveLength(2)
    vi.mocked(sendWorkspaceMessage).mockImplementation(reply({ id: 'address-selected', actions: [{ type: 'select_address_candidate', candidate: items[1]! }] }))
    wrapper.getComponent(ConversationWorkspace).vm.$emit('send', '选择第2个地址'); await flushPromises()
    expect(wrapper.getComponent(MapStage).props('analysisCenter')?.lng).toBe(113.502)
    expect(wrapper.getComponent(AnalysisControls).props('candidates')).toEqual([])
    expect(server.state.center?.lng).toBe(113.502); expect(server.state.address_candidates).toEqual([])
    wrapper.unmount()
  })
  it('对话补测的真实Point与估计时间场在同一地图自动显示且保留正式报告', async () => {
    localStorage.setItem(WORKSPACE_STORAGE_KEY, 'workspace-one')
    server = { id: 'workspace-one', revision: 1, state: { center: { ...fixture.center, selection_method: 'coordinates' }, minutes: fixture.parameters.minutes, mode: fixture.parameters.mode, categories: fixture.parameters.categories, report_id: fixture.report_id, grid_id: null, visible_categories: fixture.parameters.categories }, created_at: '', updated_at: '' }
    const wrapper = shallowMount(App); await flushPromises()
    const empty = { type: 'FeatureCollection' as const, features: [] }
    const layers = { observed: { type: 'FeatureCollection' as const, features: [{ type: 'Feature' as const, geometry: { type: 'Point' as const, coordinates: [113.5, 23.1] }, properties: { source: 'real_api', coordinate_system: 'BD-09' } }] }, estimated: empty, unresolved: empty, time_field: empty }
    vi.mocked(sendWorkspaceMessage).mockImplementation(reply({ sampling_experiment: { report_id: fixture.report_id, status: 'experimental', external_route_pairs_used: 1, enabled_for_official_analysis: false, disclosure: '独立证据', layers } }))
    wrapper.getComponent(ConversationWorkspace).vm.$emit('send', '主动补测'); await flushPromises()
    expect(wrapper.getComponent(MapStage).props('samplingLayers')).toEqual(layers)
    expect(wrapper.getComponent(MapStage).props('statusLayers')?.sampling).toBe(true)
    expect(wrapper.getComponent(MapStage).props('report')?.report_id).toBe(fixture.report_id)
    wrapper.unmount()
  })
})
