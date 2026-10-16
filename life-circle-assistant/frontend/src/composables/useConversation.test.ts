// @vitest-environment jsdom
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { createWorkspace, getWorkspace, getWorkspaceMessages, sendWorkspaceMessage, updateWorkspace, WorkspaceApiError } from '../services/workspaceApi'
import type { ConversationTurn, Workspace, WorkspaceState } from '../types/workspace'
import { useConversation, WORKSPACE_STORAGE_KEY } from './useConversation'

vi.mock('../services/workspaceApi', async importOriginal => ({ ...await importOriginal<typeof import('../services/workspaceApi')>(), createWorkspace: vi.fn(), getWorkspace: vi.fn(), getWorkspaceMessages: vi.fn(), sendWorkspaceMessage: vi.fn(), updateWorkspace: vi.fn() }))
const state: WorkspaceState = { center: { lng: 113.4872, lat: 23.1068, address: '测试中心', selection_method: 'default' }, minutes: 15, mode: 'demo', categories: ['market'], report_id: null, grid_id: null, visible_categories: ['market'] }
const saved = (): Workspace => ({ id: 'workspace-one', revision: 1, state: structuredClone(state), created_at: '', updated_at: '' })
const response = (patch: Partial<ConversationTurn> = {}): ConversationTurn => ({ id: 'turn-one', workspace_id: 'workspace-one', request_id: 'request', revision: 2, status: 'completed', message: '解释当前报告', answer: '请先生成体检报告。', actions: [], created_at: '', ...patch })
function setup(initial = state) {
  let local = structuredClone(initial)
  const applyState = vi.fn((value: WorkspaceState) => { local = JSON.parse(JSON.stringify(value)) })
  const applyTurn = vi.fn()
  const controller = useConversation({ getState: () => local, applyState, applyTurn })
  return { controller, applyState, applyTurn, edit: (patch: Partial<WorkspaceState>) => { local = { ...local, ...patch } }, getState: () => local }
}

describe('持久对话与公共工作台一致性', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    window.localStorage.clear()
    vi.mocked(createWorkspace).mockResolvedValue(saved())
    vi.mocked(getWorkspace).mockResolvedValue(saved())
    vi.mocked(getWorkspaceMessages).mockResolvedValue({ items: [] })
    vi.mocked(updateWorkspace).mockImplementation(async (_id, revision, next) => ({ ...saved(), revision: revision + 1, state: structuredClone(next) }))
    vi.mocked(sendWorkspaceMessage).mockResolvedValue(response())
  })
  afterEach(() => { vi.useRealTimers() })

  it('刷新从服务端恢复选点、报告和历史，本地只保留会话标识', async () => {
    window.localStorage.setItem(WORKSPACE_STORAGE_KEY, 'workspace-one')
    const persisted = { ...saved(), revision: 8, state: { ...state, minutes: 20 as const, minutes_confirmed: false, report_id: 'report-one', grid_id: 'market-r1c1', analysis_task_id: 'task-one' } }
    vi.mocked(getWorkspace).mockResolvedValue(persisted)
    vi.mocked(getWorkspaceMessages).mockResolvedValue({ items: [response()] })
    const { controller, getState } = setup()
    await controller.initialize()
    expect(createWorkspace).not.toHaveBeenCalled()
    expect(getState()).toEqual(persisted.state)
    expect(controller.turns.value).toHaveLength(1)
    expect(Object.keys(window.localStorage)).toEqual([WORKSPACE_STORAGE_KEY])
    expect(window.localStorage.getItem(WORKSPACE_STORAGE_KEY)).toBe('workspace-one')
  })

  it('先保存用户地图/表单变更，再用新revision发送消息', async () => {
    const { controller, edit } = setup()
    await controller.initialize()
    edit({ minutes: 20 })
    vi.mocked(getWorkspace).mockResolvedValue({ ...saved(), revision: 3, state: { ...state, minutes: 20 } })
    await controller.send('开始体检')
    expect(updateWorkspace).toHaveBeenCalledWith('workspace-one', 1, expect.objectContaining({ minutes: 20 }))
    expect(sendWorkspaceMessage).toHaveBeenCalledWith('workspace-one', expect.any(String), 2, '开始体检', undefined)
    expect(vi.mocked(updateWorkspace).mock.invocationCallOrder[0]).toBeLessThan(vi.mocked(sendWorkspaceMessage).mock.invocationCallOrder[0]!)
  })

  it('字段序不同和省略的空task不会无故修改revision或令确认失效', async () => {
    const { controller } = setup({ analysis_task_id: null, ...state })
    await controller.initialize()
    vi.mocked(sendWorkspaceMessage).mockResolvedValue(response({ status: 'awaiting_confirmation', pending: { token: 'confirm-one', label: '开始体检', budget: { max_route_pairs: 50, max_model_calls: 1 }, command: {} } }))
    vi.mocked(getWorkspace).mockResolvedValue({ ...saved(), revision: 2 })
    await controller.send('开始体检')
    expect(updateWorkspace).not.toHaveBeenCalled()
    expect(controller.pending.value?.token).toBe('confirm-one')
    await controller.confirm()
    expect(sendWorkspaceMessage).toHaveBeenLastCalledWith('workspace-one', expect.any(String), 2, '确认执行', 'confirm-one')
  })

  it('响应丢失重试复用request_id，只应用一次动作', async () => {
    const { controller, applyTurn } = setup()
    await controller.initialize()
    vi.mocked(sendWorkspaceMessage).mockRejectedValueOnce(new Error('连接中断')).mockResolvedValueOnce(response())
    expect(await controller.send('解释当前报告')).toBe(false)
    const id = vi.mocked(sendWorkspaceMessage).mock.calls[0]![1]
    expect(await controller.retry()).toBe(true)
    expect(vi.mocked(sendWorkspaceMessage).mock.calls[1]![1]).toBe(id)
    expect(applyTurn).toHaveBeenCalledTimes(1)
    expect(controller.turns.value).toHaveLength(1)
    expect(controller.retryRequest.value).toBeNull()
  })

  it('409恢复其他页面的最新状态，不自动覆盖或继续执行旧命令', async () => {
    const { controller, edit, getState } = setup()
    await controller.initialize()
    edit({ minutes: 20 })
    vi.mocked(updateWorkspace).mockRejectedValueOnce(new WorkspaceApiError(409, '版本冲突'))
    vi.mocked(getWorkspace).mockResolvedValue({ ...saved(), revision: 8, state: { ...state, minutes: 10 } })
    expect(await controller.send('开始体检')).toBe(false)
    expect(sendWorkspaceMessage).not.toHaveBeenCalled()
    expect(getState().minutes).toBe(10)
    expect(controller.error.value).toContain('其他页面更新')
    expect(controller.retryRequest.value).toBeNull()
  })

  it('相同请求仍在后台执行的409保留标识，后续重试不重复创建副作用', async () => {
    const { controller, applyTurn } = setup()
    await controller.initialize()
    vi.mocked(sendWorkspaceMessage).mockRejectedValueOnce(new WorkspaceApiError(409, '这条消息正在执行，请稍后用相同请求标识重试')).mockResolvedValueOnce(response())
    expect(await controller.send('开始体检')).toBe(false)
    const requestId = vi.mocked(sendWorkspaceMessage).mock.calls[0]![1]
    expect(controller.retryRequest.value?.id).toBe(requestId)
    expect(controller.error.value).toContain('相同请求标识')
    expect(await controller.retry()).toBe(true)
    expect(vi.mocked(sendWorkspaceMessage).mock.calls[1]![1]).toBe(requestId)
    expect(applyTurn).toHaveBeenCalledTimes(1)
  })

  it('响应丢失后其他页面已更新时，幂等旧结果只恢复记录，不重放旧地图动作', async () => {
    const { controller, applyTurn, getState } = setup()
    await controller.initialize()
    vi.mocked(sendWorkspaceMessage).mockRejectedValueOnce(new Error('响应丢失')).mockResolvedValueOnce(response({ actions: [{ type: 'set_layers', categories: ['market'] }] }))
    expect(await controller.send('只看菜市场')).toBe(false)
    vi.mocked(getWorkspace).mockResolvedValue({ ...saved(), revision: 7, state: { ...state, minutes: 20 } })
    vi.mocked(getWorkspaceMessages).mockResolvedValue({ items: [response()] })
    expect(await controller.retry()).toBe(false)
    expect(getState().minutes).toBe(20)
    expect(applyTurn).not.toHaveBeenCalled()
    expect(updateWorkspace).not.toHaveBeenCalled()
    expect(controller.turns.value).toHaveLength(1)
    expect(controller.retryRequest.value).toBeNull()
    expect(controller.error.value).toContain('最新上下文')
  })

  it('位置未确认以null回写，不复用原地址；变更后旧确认不可执行', async () => {
    vi.useFakeTimers()
    const { controller, edit } = setup()
    await controller.initialize()
    vi.mocked(getWorkspace).mockResolvedValue({ ...saved(), revision: 2 })
    vi.mocked(sendWorkspaceMessage).mockResolvedValue(response({ status: 'awaiting_confirmation', pending: { token: 'old', label: '体检', budget: { max_route_pairs: 50, max_model_calls: 0 }, command: {} } }))
    await controller.send('开始体检')
    edit({ center: null })
    controller.scheduleSync()
    await vi.advanceTimersByTimeAsync(300)
    expect(updateWorkspace).toHaveBeenLastCalledWith('workspace-one', 2, expect.objectContaining({ center: null }))
    expect(controller.pending.value).toBeNull()
    expect(await controller.confirm()).toBe(false)
    expect(sendWorkspaceMessage).toHaveBeenCalledTimes(1)
    controller.dispose()
  })

  it('已删除的会话可重建；网络错误保留原标识以供重试', async () => {
    window.localStorage.setItem(WORKSPACE_STORAGE_KEY, 'workspace-one')
    vi.mocked(getWorkspace).mockRejectedValueOnce(new Error('服务离线'))
    const { controller } = setup()
    await controller.initialize()
    expect(createWorkspace).not.toHaveBeenCalled()
    expect(controller.ready.value).toBe(false)
    expect(window.localStorage.getItem(WORKSPACE_STORAGE_KEY)).toBe('workspace-one')
    vi.mocked(getWorkspace).mockRejectedValueOnce(new WorkspaceApiError(404, '已删除'))
    await controller.initialize()
    expect(createWorkspace).toHaveBeenCalledTimes(1)
    expect(controller.ready.value).toBe(true)
  })
})
