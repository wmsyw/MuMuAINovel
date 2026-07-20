import { describe, expect, it } from 'vitest'

import { normalizeSMTPFromName, normalizeSMTPSettings } from '../../utils/smtpSettings'

describe('System settings SMTP normalization', () => {
  it('replaces the exact legacy sender name with the generic default', () => {
    expect(normalizeSMTPFromName('MuMuAINovel')).toBe('AI Novel Studio')
    expect(normalizeSMTPFromName('My Novel')).toBe('My Novel')
  })

  it('normalizes the sender name without changing other SMTP values', () => {
    expect(normalizeSMTPSettings({
      smtp_provider: 'custom',
      smtp_host: 'smtp.example.test',
      smtp_from_name: 'MuMuAINovel',
    })).toEqual({
      smtp_provider: 'custom',
      smtp_host: 'smtp.example.test',
      smtp_from_name: 'AI Novel Studio',
    })
  })
})
