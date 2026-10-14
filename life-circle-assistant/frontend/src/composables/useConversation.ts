import { computed, ref } from 'vue'
import { createWorkspace, getWorkspace, getWorkspaceMessages, sendWorkspaceMessage, updateWorkspace, WorkspaceApiError } from '../services/workspaceApi'
import type { ConversationTurn, Workspace, WorkspaceState } from '../types/workspace'

export const WORKSPACE_STORAGE_KEY = 'life-circle:workspace:v1'

function stateSignature(state: WorkspaceState) {
  // 服务端字段顺序和可选空字段不应产生一次新的修改。
  return JSON.stringify([
    state.center ? [state.center.lng, state.center.lat, state.center.address, state.center.selection_method] : null,
    state.minutes, state.minutes_confirmed !== false, state.mode, state.categories, state.report_id, state.grid_id, state.visible_categories, state.analysis_task_id || null,
    state.status_layers || null, state.address_candidates || [], state.history_report_ids || [],
  ])
}

export function useConversation(options: {
  getState: () => WorkspaceState
  applyState: (state: WorkspaceState) => Promise<void> | void
  applyTurn: (turn: ConversationTurn) => Promise<void> | void
}) {
  const workspace = ref<Workspace | null>(null)
  const turns = ref<ConversationTurn[]>([])
  const ready = ref(false)
  const busy = ref(false)
  const restoring = ref(false)
  const error = ref('')
  const retryRequest = ref<{ id: string; message: string; token?: string } | null>(null)
  const pending = computed(() => {
    const latest = turns.value.at(-1)
    return latest?.status === 'awaiting_confirmation' && latest.revision === workspace.value?.revision ? latest.pending ?? null : null
  })
  let queue = Promise.resolve()
  let timer: ReturnType<typeof setTimeout> | undefined
  let disposed = false
  let applying = false
  const enqueue = <T>(operation: () => Promise<T>) => {
    const next = queue.then(operation)
    queue = next.then(() => undefined, () => undefined)
    return next
  }
  function store(value: Workspace) {
    workspace.value = value
    window.localStorage.setItem(WORKSPACE_STORAGE_KEY, value.id)
  }
  async function apply(state: WorkspaceState) {
    applying = true
    try { await options.applyState(state) } finally { applying = false }
  }
  async function recoverConflict() {
    if (!workspace.value) return
    store(await getWorkspace(workspace.value.id))
    await apply(workspace.value.state)
    turns.value = (await getWorkspaceMessages(workspace.value.id)).items
    retryRequest.value = null
    error.value = '工作台已在其他页面更新，已恢复最新状态。请检查当前参数后重新发送。'
  }
  async function sync() {
    if (!ready.value || !workspace.value || disposed || applying) return
    const state = options.getState()
    if (stateSignature(state) === stateSignature(workspace.value.state)) return
    try {
      store(await updateWorkspace(workspace.value.id, workspace.value.revision, state))
      retryRequest.value = null
    } catch (cause) {
      if (cause instanceof WorkspaceApiError && cause.status === 409) { await recoverConflict(); throw cause }
      throw cause
    }
  }
  function scheduleSync() {
    if (!ready.value || applying || disposed) return
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      timer = undefined
      void enqueue(sync).catch(cause => { if (!(cause instanceof WorkspaceApiError && cause.status === 409)) error.value = cause.message || '工作台状态保存失败' })
    }, 250)
  }
  async function initialize() {
    if (restoring.value || ready.value) return
    restoring.value = true
    error.value = ''
    try {
      const saved = window.localStorage.getItem(WORKSPACE_STORAGE_KEY)
      if (saved) {
        try {
          store(await getWorkspace(saved))
        } catch (cause) {
          if (!(cause instanceof WorkspaceApiError && cause.status === 404)) throw cause
          store(await createWorkspace(options.getState()))
        }
      } else store(await createWorkspace(options.getState()))
      turns.value = (await getWorkspaceMessages(workspace.value!.id)).items
      await apply(workspace.value!.state)
      ready.value = true
    } catch (cause: unknown) {
      error.value = cause instanceof Error ? cause.message : '对话工作台暂不可用'
    } finally { restoring.value = false }
  }
  async function submit(message: string, token?: string, retry = false) {
    const trimmed = message.trim()
    if (busy.value || !ready.value || !trimmed || disposed) return false
    busy.value = true
    error.value = ''
    if (timer) { clearTimeout(timer); timer = undefined }
    try {
      return await enqueue(async () => {
        await sync()
        const value = workspace.value!
        const request = retry && retryRequest.value ? retryRequest.value : { id: crypto.randomUUID(), message: trimmed, token }
        retryRequest.value = request
        const turn = await sendWorkspaceMessage(value.id, request.id, value.revision, request.message, request.token)
        const latest = await getWorkspace(value.id)
        store(latest)
        // 响应丢失后的幂等结果可能已经早于其他页面的新操作，不能重放旧动作覆盖新上下文。
        if (turn.revision < latest.revision) {
          await apply(latest.state)
          turns.value = (await getWorkspaceMessages(value.id)).items
          retryRequest.value = null
          error.value = '本条消息已完成，工作台随后发生更新，已恢复最新上下文。'
          return false
        }
        // 幂等重试只展示一轮；动作在首次收到响应时执行。
        if (!turns.value.some(item => item.id === turn.id)) {
          applying = true
          try { await options.applyTurn(turn) } finally { applying = false }
          turns.value = [...turns.value, turn]
        }
        retryRequest.value = null
        await sync()
        return true
      })
    } catch (cause) {
      if (cause instanceof WorkspaceApiError && cause.status === 409 && cause.message === '这条消息正在执行，请稍后用相同请求标识重试') error.value = cause.message
      else if (cause instanceof WorkspaceApiError && cause.status === 409) await recoverConflict()
      else error.value = cause instanceof Error ? cause.message : '消息发送失败，请重试'
      return false
    } finally { busy.value = false }
  }
  const send = (message: string) => submit(message)
  const confirm = () => pending.value ? submit('确认执行', pending.value.token) : Promise.resolve(false)
  const retry = () => retryRequest.value ? submit(retryRequest.value.message, retryRequest.value.token, true) : Promise.resolve(false)
  function dispose() { disposed = true; if (timer) clearTimeout(timer) }
  return { workspace, turns, ready, busy, restoring, error, retryRequest, pending, initialize, scheduleSync, send, confirm, retry, dispose }
}
