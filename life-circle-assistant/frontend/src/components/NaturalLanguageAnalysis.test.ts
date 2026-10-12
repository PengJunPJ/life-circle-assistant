// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import NaturalLanguageAnalysis from './NaturalLanguageAnalysis.vue'
import { parseAnalysisIntent, searchAddressCandidates } from '../services/analysisApi'
import type { AnalysisIntent, IntentDraft } from '../types/analysisIntent'
import type { AnalysisCenter } from '../types/location'

vi.mock('../services/analysisApi', () => ({ parseAnalysisIntent: vi.fn(), searchAddressCandidates: vi.fn() }))
const center: AnalysisCenter = { lng: 113.4872, lat: 23.1068, address: '已确认的样例中心', selectionMethod: 'default', source: 'local_snapshot', supportStatus: 'supported' }
const candidate = { lng: 113.49, lat: 23.11, address: '红山街道海韵东路', source: 'local_snapshot', provider: 'snapshot' }
function result(patch: Partial<IntentDraft> = {}): AnalysisIntent {
  return { draft: { address: '红山街道海韵东路', use_current_center: false, minutes: 15, mode: 'demo', categories: ['market', 'pharmacy'], defaulted_fields: ['minutes', 'mode'], ...patch }, parser: 'rules', model: null, missing_fields: [], message: '请确认参数' }
}
const setup = () => mount(NaturalLanguageAnalysis, { props: { center, disabled: false, realApiConfigured: false } })
async function send(wrapper: ReturnType<typeof setup>, text = '红山街道海韵东路，买菜和买药') {
  await wrapper.get('textarea').setValue(text)
  await wrapper.get('.natural-send').trigger('click')
  await flushPromises()
}

describe('自然语言体检入口', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.mocked(parseAnalysisIntent).mockResolvedValue(result())
    vi.mocked(searchAddressCandidates).mockResolvedValue([candidate])
  })

  it('只在确认后提交经过地图确认且可编辑的参数', async () => {
    const wrapper = setup()
    expect(parseAnalysisIntent).not.toHaveBeenCalled()
    await send(wrapper)
    expect(searchAddressCandidates).toHaveBeenCalledWith('红山街道海韵东路')
    expect(wrapper.emitted('confirm')).toBeUndefined()
    expect(wrapper.text()).toContain('规则解析 · 模型未启用')
    expect(wrapper.text()).toContain('未提及的参数采用默认值')
    expect(wrapper.text()).toContain('本地快照')
    await wrapper.get('[aria-label="对话步行时间"]').setValue('20')
    await wrapper.get('[aria-label="对话分析精度"]').setValue('analysis')
    await wrapper.get('input[value="pharmacy"]').setValue(false)
    await wrapper.get('.primary-action').trigger('click')
    expect(wrapper.emitted('confirm')?.[0]?.[0]).toMatchObject({
      center: { ...candidate, selectionMethod: 'address', supportStatus: 'supported' }, minutes: 20, mode: 'analysis', categories: ['market'],
    })
  })

  it('缺少地点时追问，补充消息携带前一轮参数', async () => {
    const missing = result({ address: '' })
    missing.message = '请补充社区或地址'
    missing.missing_fields = ['location']
    vi.mocked(parseAnalysisIntent).mockResolvedValueOnce(missing).mockResolvedValueOnce(result())
    const wrapper = setup()
    await send(wrapper, '买药和买菜')
    expect(wrapper.text()).toContain('请补充社区或地址')
    expect(searchAddressCandidates).not.toHaveBeenCalled()
    expect(wrapper.get('.primary-action').attributes('disabled')).toBeDefined()
    await send(wrapper, '地址是红山街道海韵东路')
    expect(parseAnalysisIntent).toHaveBeenLastCalledWith('地址是红山街道海韵东路', missing.draft)
    expect(wrapper.get('.primary-action').attributes('disabled')).toBeUndefined()
  })

  it('多个地址候选必须选择，修改地址后必须重新查询', async () => {
    vi.mocked(searchAddressCandidates).mockResolvedValue([candidate, { ...candidate, lng: 113.5, address: '另一处同名小区' }])
    const wrapper = setup()
    await send(wrapper)
    expect(wrapper.get('.primary-action').attributes('disabled')).toBeDefined()
    await wrapper.findAll('.candidate-list button')[1]!.trigger('click')
    expect(wrapper.get('.primary-action').attributes('disabled')).toBeUndefined()
    await wrapper.get('#intent-address').setValue('新地址')
    expect(wrapper.get('.primary-action').attributes('disabled')).toBeDefined()
    expect(wrapper.find('.natural-location').exists()).toBe(false)
  })

  it('地址查询失败不启动体检，允许编辑重试', async () => {
    vi.mocked(searchAddressCandidates).mockRejectedValueOnce(new Error('离线快照不支持此社区'))
    const wrapper = setup()
    await send(wrapper)
    expect(wrapper.get('[role="alert"]').text()).toContain('离线快照不支持此社区')
    expect(wrapper.get('.primary-action').attributes('disabled')).toBeDefined()
    expect(wrapper.emitted('confirm')).toBeUndefined()
    await wrapper.get('#intent-address').setValue('红山街道海韵东路')
    await wrapper.get('.natural-address-row button').trigger('click')
    await flushPromises()
    expect(wrapper.get('.primary-action').attributes('disabled')).toBeUndefined()
  })

  it('只有明确使用当前选点才复用位置，选点改变后要求再次确认', async () => {
    vi.mocked(parseAnalysisIntent).mockResolvedValue(result({ address: '', use_current_center: true }))
    const wrapper = setup()
    await send(wrapper, '当前选点，买药')
    expect(searchAddressCandidates).not.toHaveBeenCalled()
    expect(wrapper.get('.primary-action').attributes('disabled')).toBeUndefined()
    await wrapper.setProps({ center: { ...center, lng: 113.5 } })
    expect(wrapper.text()).toContain('当前选点已改变')
    expect(wrapper.get('.primary-action').attributes('disabled')).toBeDefined()
  })

  it('不支持的时间与空设施阻止启动，可在预览中修正', async () => {
    vi.mocked(parseAnalysisIntent).mockResolvedValue(result({ minutes: null, categories: [] }))
    const wrapper = setup()
    await send(wrapper, '30分钟')
    expect(wrapper.get('.primary-action').attributes('disabled')).toBeDefined()
    await wrapper.get('[aria-label="对话步行时间"]').setValue('10')
    await wrapper.get('input[value="medical"]').setValue(true)
    expect(wrapper.get('.primary-action').attributes('disabled')).toBeUndefined()
  })

  it('未发送的修改和请求进行中均不能使用旧参数启动', async () => {
    const wrapper = setup()
    await send(wrapper)
    await wrapper.get('textarea').setValue('改成20分钟')
    expect(wrapper.get('.primary-action').attributes('disabled')).toBeDefined()
    let finish!: (value: AnalysisIntent) => void
    vi.mocked(parseAnalysisIntent).mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    await wrapper.get('.natural-send').trigger('click')
    expect(wrapper.get('.primary-action').attributes('disabled')).toBeDefined()
    expect(wrapper.get('textarea').attributes('disabled')).toBeDefined()
    finish(result({ minutes: 20 }))
    await flushPromises()
    expect(wrapper.get('.primary-action').attributes('disabled')).toBeUndefined()
  })

  it('明确显示模型降级，解析接口失败后保留输入并阻止启动', async () => {
    vi.mocked(parseAnalysisIntent).mockResolvedValueOnce({ ...result(), parser: 'rules_degraded' })
    const wrapper = setup()
    await send(wrapper)
    expect(wrapper.text()).toContain('模型不可用或结果未通过校验')
    vi.mocked(parseAnalysisIntent).mockRejectedValueOnce(new Error('后端连接失败'))
    await send(wrapper, '改成10分钟')
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('改成10分钟')
    expect(wrapper.get('.primary-action').attributes('disabled')).toBeDefined()
    expect(wrapper.emitted('confirm')).toBeUndefined()
  })

  it('重置清空草稿与对话，通知表单恢复手工启动入口', async () => {
    const wrapper = setup()
    await send(wrapper)
    expect(wrapper.emitted('update:active')?.at(-1)).toEqual([true])
    await wrapper.get('.natural-heading button').trigger('click')
    expect(wrapper.find('.natural-preview').exists()).toBe(false)
    expect(wrapper.find('.natural-conversation').exists()).toBe(false)
    expect(wrapper.emitted('update:active')?.at(-1)).toEqual([false])
  })
})
