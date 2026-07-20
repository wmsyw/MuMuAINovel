import type { SystemSMTPSettingsUpdate } from '../types'

const LEGACY_SMTP_FROM_NAME = 'MuMuAINovel'
const DEFAULT_SMTP_FROM_NAME = 'AI Novel Studio'

export const normalizeSMTPFromName = (value?: string | null): string => (
  value === LEGACY_SMTP_FROM_NAME ? DEFAULT_SMTP_FROM_NAME : value || DEFAULT_SMTP_FROM_NAME
)

export const normalizeSMTPSettings = (settings: Partial<SystemSMTPSettingsUpdate>) => ({
  ...settings,
  smtp_from_name: normalizeSMTPFromName(settings.smtp_from_name),
})
