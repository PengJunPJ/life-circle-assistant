// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import NaturalLanguageAnalysis from './NaturalLanguageAnalysis.vue'
import { parseAnalysisIntent } from '../services/analysisApi'
import type { AnalysisIntent, IntentDraft } from '../types/analysisIntent'

vi.mock('../services/analysisApi', () => ({ parseAnalysisIntent: vi.fn() }))
const previous: IntentDraft = { address: '已确认的样例中心', use_current_center: true, minutes: 15, mode: 'analysis', categories: ['medical', 'school', 'convenience', 'elderly'], defaulted_fields: [] }
function result(patch: Partial<IntentDraft> = {}): AnalysisIntent { return { draft: { ...previous, minutes: 20, categories: ['market', 'pharmacy'], ...patch }, parser: 'rules', model: null, missing_fields: [], message: '请确认参数' } }
const setup = () => mount(NaturalLanguageAnalysis, { props: { previous: structuredClone(previous), disabled: false } })
async function send(wrapper: ReturnType<typeof setup>, description = '20分钟，买菜和买药') { await wrapper.get('textarea').setValue(description); await wrapper.get('.natural-send').trigger('click'); await flushPromises() }

describe('一句话只填公共参数', () => {
  beforeEach(() => { vi.resetAllMocks(); vi.mocked(parseAnalysisIntent).mockResolvedValue(result()) })
  it('使用当前参数作为基础，成功发出填写事件，没有重复表单或启动按钮', async () => {
    const wrapper = setup()
    expect(parseAnalysisIntent).not.toHaveBeenCalled()
    await send(wrapper)
    expect(parseAnalysisIntent).toHaveBeenCalledWith('20分钟，买菜和买药', previous)
    expect(wrapper.emitted('fill')).toEqual([[result()]])
    expect(wrapper.text()).toContain('已填入，可继续修改')
    expect(wrapper.findAll('select,input,.primary-action')).toHaveLength(0)
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('20分钟，买菜和买药')
    expect(wrapper.emitted('update:blocked')?.at(-1)).toEqual([false])
  })
  it('下一轮解析沿用公共表单的新修改，而不是上一轮私有草稿', async () => {
    const wrapper = setup()
    await send(wrapper)
    const edited: IntentDraft = { ...previous, minutes: 10, mode: 'demo', categories: ['park'], address: '新选位置' }
    await wrapper.setProps({ previous: edited })
    await send(wrapper, '增加养老')
    expect(parseAnalysisIntent).toHaveBeenLastCalledWith('增加养老', edited)
  })
  it('未发送的修改和解析中阻止启动，重复点击只发起一次解析', async () => {
    const wrapper = setup()
    await send(wrapper)
    await wrapper.get('textarea').setValue('改成10分钟')
    expect(wrapper.emitted('update:blocked')?.at(-1)).toEqual([true])
    let finish!: (intent: AnalysisIntent) => void
    vi.mocked(parseAnalysisIntent).mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    await wrapper.get('.natural-send').trigger('click')
    await wrapper.get('textarea').trigger('keydown', { key: 'Enter', ctrlKey: true })
    expect(parseAnalysisIntent).toHaveBeenCalledTimes(2)
    expect(wrapper.get('textarea').attributes('disabled')).toBeDefined()
    expect(wrapper.emitted('update:busy')?.at(-1)).toEqual([true])
    finish(result({ minutes: 10 }))
    await flushPromises()
    expect(wrapper.emitted('update:blocked')?.at(-1)).toEqual([false])
  })
  it('解析失败保留描述和公共参数，显示错误；重试成功解除阻止', async () => {
    vi.mocked(parseAnalysisIntent).mockRejectedValueOnce(new Error('后端连接失败'))
    const wrapper = setup()
    await send(wrapper)
    expect(wrapper.emitted('fill')).toBeUndefined()
    expect(wrapper.get('[role="alert"]').text()).toContain('后端连接失败')
    expect(wrapper.emitted('update:blocked')?.at(-1)).toEqual([true])
    await send(wrapper)
    expect(wrapper.emitted('fill')).toHaveLength(1)
    expect(wrapper.emitted('update:blocked')?.at(-1)).toEqual([false])
  })
})
