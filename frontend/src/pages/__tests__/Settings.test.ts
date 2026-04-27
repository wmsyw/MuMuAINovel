import { describe, expect, it } from 'vitest'

import type { ReasoningCapabilitiesResponse, ReasoningCapability, ReasoningIntensity, SettingsUpdate } from '../../types'
import SettingsPage from '../Settings'

interface SettingsTestUtils {
  ENTITY_GENERATION_WARNING_COPY: string;
  findReasoningCapability: (
    provider: string | undefined,
    model: string | undefined,
    capabilities?: ReasoningCapability[],
  ) => ReasoningCapability | undefined;
  getApiErrorMessage: (error: unknown, fallback: string) => string;
  getReasoningIntensityOptions: (
    registry: ReasoningCapabilitiesResponse | null,
    provider?: string,
    model?: string,
  ) => Array<{ value: ReasoningIntensity; label: string; disabled: boolean; reason?: string }>;
  getReasoningSelectionError: (
    provider: string | undefined,
    model: string | undefined,
    intensity: ReasoningIntensity | undefined,
    registry: ReasoningCapabilitiesResponse | null,
  ) => string | undefined;
  normalizeReasoningProvider: (provider?: string) => string;
  normalizeSettingsFormDefaults: <T extends Partial<SettingsUpdate>>(settings?: T) => T & {
    default_reasoning_intensity: ReasoningIntensity;
    allow_ai_entity_generation: boolean;
  };
}

const {
  ENTITY_GENERATION_WARNING_COPY,
  findReasoningCapability,
  getApiErrorMessage,
  getReasoningIntensityOptions,
  getReasoningSelectionError,
  normalizeReasoningProvider,
  normalizeSettingsFormDefaults,
} = (SettingsPage as typeof SettingsPage & {
  __testUtils: SettingsTestUtils;
}).__testUtils

const registry: ReasoningCapabilitiesResponse = {
  intensities: ['auto', 'off', 'low', 'medium', 'high', 'maximum'],
  capabilities: [
    {
      provider: 'openai',
      model_pattern: 'gpt-4o*',
      supported_intensities: ['auto', 'off'],
      default_intensity: 'auto',
      provider_metadata: {
        native_field: 'responses.reasoning.effort',
        read_only: true,
        payload_mappings: {
          auto: {},
          off: { reasoning: { effort: 'none' } },
        },
      },
      last_verified_date: '2026-04-26',
      notes: 'OpenAI non-reasoning family rejects explicit effort levels.',
    },
    {
      provider: 'anthropic',
      model_pattern: 'claude-sonnet-4*',
      supported_intensities: ['auto', 'off', 'low', 'medium', 'high', 'maximum'],
      default_intensity: 'auto',
      provider_metadata: {
        native_field: 'output_config.effort',
        read_only: true,
        payload_mappings: {
          auto: {},
          off: { output_config: { effort: 'off' } },
          low: { output_config: { effort: 'low' } },
          medium: { output_config: { effort: 'medium' } },
          high: { output_config: { effort: 'high' } },
          maximum: { output_config: { effort: 'high' } },
        },
      },
      last_verified_date: '2026-04-26',
      notes: 'Claude model pattern with explicit effort controls.',
    },
    {
      provider: 'gemini',
      model_pattern: 'gemini-2.5*',
      supported_intensities: ['auto', 'off', 'low', 'medium', 'high', 'maximum'],
      default_intensity: 'auto',
      provider_metadata: {
        native_field: 'generationConfig.thinkingConfig.thinkingBudget',
        read_only: true,
        payload_mappings: {
          auto: {},
          off: { generationConfig: { thinkingConfig: { thinkingBudget: 0 } } },
          low: { generationConfig: { thinkingConfig: { thinkingBudget: 1024 } } },
          medium: { generationConfig: { thinkingConfig: { thinkingBudget: 4096 } } },
          high: { generationConfig: { thinkingConfig: { thinkingBudget: 8192 } } },
          maximum: { generationConfig: { thinkingConfig: { thinkingBudget: 24576 } } },
        },
      },
      last_verified_date: '2026-04-26',
      notes: 'Gemini thinking budget mapping.',
    },
  ],
}

describe('Settings reasoning capability helpers', () => {
  it('matches backend OpenAI/Claude/Gemini capability metadata', () => {
    expect(normalizeReasoningProvider('mumu')).toBe('openai')
    expect(findReasoningCapability('openai', 'gpt-4o-mini', registry.capabilities)?.provider_metadata.native_field)
      .toBe('responses.reasoning.effort')
    expect(findReasoningCapability('anthropic', 'claude-sonnet-4-20250514', registry.capabilities)?.provider_metadata.native_field)
      .toBe('output_config.effort')
    expect(findReasoningCapability('gemini', 'gemini-2.5-pro', registry.capabilities)?.provider_metadata.native_field)
      .toBe('generationConfig.thinkingConfig.thinkingBudget')
    expect(registry.capabilities.every(capability => capability.provider_metadata.read_only)).toBe(true)
  })

  it('disables unsupported reasoning intensity options for the selected provider/model', () => {
    const openAiOptions = getReasoningIntensityOptions(registry, 'openai', 'gpt-4o-mini')
    expect(openAiOptions.find(option => option.value === 'off')?.disabled).toBe(false)
    expect(openAiOptions.find(option => option.value === 'high')?.disabled).toBe(true)

    const geminiOptions = getReasoningIntensityOptions(registry, 'gemini', 'gemini-2.5-pro')
    expect(geminiOptions.find(option => option.value === 'maximum')?.disabled).toBe(false)
  })

  it('rejects unsupported selections before save or test submission', () => {
    expect(getReasoningSelectionError('openai', 'gpt-4o-mini', 'auto', registry)).toBeUndefined()
    expect(getReasoningSelectionError('openai', 'gpt-4o-mini', 'high', registry))
      .toContain('不支持推理强度 high')
    expect(getReasoningSelectionError('anthropic', 'claude-sonnet-4-latest', 'maximum', registry))
      .toBeUndefined()
    expect(getReasoningSelectionError('openai', 'unknown-model', 'low', registry))
      .toContain('未匹配到该 provider/model 的推理能力元数据')
  })

  it('surfaces deterministic backend validation rejection details', () => {
    const error = {
      response: {
        data: {
          detail: '模型 openai/gpt-4o-mini 不支持推理强度 high；支持: auto, off',
        },
      },
    }

    expect(getApiErrorMessage(error, '保存设置失败')).toBe(error.response.data.detail)
  })
})

describe('Settings advanced entity generation override defaults', () => {
  it('defaults allow_ai_entity_generation off and preserves backend-backed true values', () => {
    expect(normalizeSettingsFormDefaults({}).allow_ai_entity_generation).toBe(false)
    expect(normalizeSettingsFormDefaults({ allow_ai_entity_generation: true }).allow_ai_entity_generation).toBe(true)
  })

  it('keeps the required advanced warning copy exact', () => {
    expect(ENTITY_GENERATION_WARNING_COPY).toBe('默认从正文自动提取角色/组织/职业；开启后才允许 AI 直接生成入库')
  })
})
