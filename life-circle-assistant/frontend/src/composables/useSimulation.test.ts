// @vitest-environment jsdom
import { effectScope, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { useSimulation } from './useSimulation'
import { simulateFacility } from '../services/analysisApi'
import type { Report } from '../types/report'
import type { SimulationResult } from '../types/simulation'

vi.mock('../services/analysisApi', () => ({ simulateFacility: vi.fn() }))
vi.mock('element-plus/es/components/message/index', () => ({ default: { info: vi.fn(), success: vi.fn(), error: vi.fn() } }))

describe('助手模拟与地图联动', () => {
  it('接受当前报告已计算的结果，拒绝其他报告结果，不重复调用模拟接口', () => {
    const scope = effectScope()
    const report = ref({ report_id: 'report-one', parameters: { categories: ['market'] } } as Report)
    const controller = scope.run(() => useSimulation(report))!
    const simulation = { id: 'simulation', report_id: 'report-one', category: 'market', selection_method: 'recommendation', candidate_id: 'candidate-one', hypothetical_facility: { lng: 113.5, lat: 23.1 } } as SimulationResult
    controller.applyAssistantSimulation(simulation)
    expect(controller.result.value?.id).toBe('simulation')
    expect(controller.location.value).toEqual({ lng: 113.5, lat: 23.1, selectionMethod: 'recommendation', candidateId: 'candidate-one' })
    controller.applyAssistantSimulation({ ...simulation, id: 'other', report_id: 'another-report' })
    expect(controller.result.value?.id).toBe('simulation')
    expect(simulateFacility).not.toHaveBeenCalled()
    scope.stop()
  })
})
