// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ConversationWorkspace from './ConversationWorkspace.vue'
import type { ConversationTurn } from '../types/workspace'
const props = { context: '测试中心 · 15分钟 · 1类', turns: [] as ConversationTurn[], ready: true, busy: false, restoring: false, error: '', canRetry: false, pending: null, task: null, analyzing: false, progress: 0, progressLabel: '', cancelling: false }

describe('地图上的对话入口', () => {
  it('快捷 AI 意图会复用对话发送链路并展开会话记录', async () => {
    const wrapper = mount(ConversationWorkspace, { props })
    const action = wrapper.findAll('.conversation-quick-actions button').find(button => button.text() === '找步行盲区')
    expect(action).toBeDefined()
    await action!.trigger('click')
    expect(wrapper.emitted('send')).toEqual([['找出当前15分钟步行盲区']])
    expect(wrapper.get('.conversation-heading button').attributes('aria-expanded')).toBe('true')
  })

  it('直接输入可发送，中文输入法确认与Shift Enter均不会误发', async () => {
    const wrapper = mount(ConversationWorkspace, { props })
    const input = wrapper.get('textarea')
    await input.setValue('  只看菜市场  ')
    await input.trigger('keydown', { key: 'Enter', isComposing: true })
    await input.trigger('keydown', { key: 'Enter', shiftKey: true })
    expect(wrapper.emitted('send')).toBeUndefined()
    await input.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('send')).toEqual([['只看菜市场']])
    expect(wrapper.get('.conversation-heading button').attributes('aria-expanded')).toBe('true')
  })

  it('模型文本按纯文字显示，确认前展示调用预算并提供显式操作', async () => {
    const pending = { token: 'one', label: '开始正式体检', budget: { max_route_pairs: 50, max_model_calls: 1 }, command: {} }
    const turn = { id: 'one', message: '开始', answer: '<script>alert(1)</script>', actions: [], created_at: '', workspace_id: 'one', request_id: 'one', revision: 1, status: 'awaiting_confirmation', pending } satisfies ConversationTurn
    const wrapper = mount(ConversationWorkspace, { props: { ...props, turns: [turn], pending } })
    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.text()).toContain('<script>alert(1)</script>')
    expect(wrapper.text()).toContain('50条路线')
    await wrapper.get('.conversation-confirmation button').trigger('click')
    expect(wrapper.emitted('confirm')).toHaveLength(1)
  })

  it('后台任务进行时仍能对话询问进度与取消，取消按钮也可使用', async () => {
    const wrapper = mount(ConversationWorkspace, { props: { ...props, analyzing: true, task: { id: 'task', status: 'running', progress: 40, stage: 'walking', stage_label: '计算步行路线' } } })
    expect(wrapper.get('textarea').attributes('disabled')).toBeUndefined()
    await wrapper.get('textarea').setValue('取消体检')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('send')).toEqual([['取消体检']])
    await wrapper.get('.conversation-task button').trigger('click')
    expect(wrapper.emitted('cancel-task')).toHaveLength(1)
  })

  it('可隐藏AI规划助手，并通过机器人入口恢复', async () => {
    const wrapper = mount(ConversationWorkspace, { props })
    await wrapper.get('.conversation-hide').trigger('click')
    expect(wrapper.find('.conversation-workspace').exists()).toBe(false)
    expect(wrapper.get('.conversation-launcher').attributes('aria-label')).toBe('显示AI规划助手')
    expect(wrapper.emitted('resize')).toContainEqual([0])
    await wrapper.get('.conversation-launcher').trigger('click')
    expect(wrapper.find('.conversation-workspace').exists()).toBe(true)
  })
})
