import type { GoldfingerStatus } from '../../types';

export const GOLDFINGER_PAYLOAD_VERSION = 'goldfinger-card.v1' as const;

export const goldfingerStatusOptions: Array<{ value: GoldfingerStatus; label: string; color: string }> = [
  { value: 'latent', label: '潜伏', color: 'default' },
  { value: 'active', label: '激活', color: 'success' },
  { value: 'sealed', label: '封印', color: 'warning' },
  { value: 'cooldown', label: '冷却', color: 'processing' },
  { value: 'upgrading', label: '升级中', color: 'blue' },
  { value: 'lost', label: '遗失', color: 'error' },
  { value: 'completed', label: '已完成', color: 'purple' },
  { value: 'unknown', label: '未知', color: 'default' },
];

export const goldfingerJsonFieldLabels: Record<string, string> = {
  rules: '规则',
  tasks: '任务',
  rewards: '奖励',
  limits: '限制',
  trigger_conditions: '触发条件',
  cooldown: '冷却',
  aliases: '别名',
  metadata: '元数据',
};

export const goldfingerJsonFields = Object.keys(goldfingerJsonFieldLabels) as Array<keyof typeof goldfingerJsonFieldLabels>;

export function getGoldfingerStatusMeta(status?: string | null) {
  return goldfingerStatusOptions.find(item => item.value === status) || goldfingerStatusOptions[goldfingerStatusOptions.length - 1];
}

export function formatConfidence(confidence?: number | null): string {
  if (confidence === null || confidence === undefined) {
    return '未记录';
  }
  return `${Math.round(Math.max(0, Math.min(1, confidence)) * 100)}%`;
}

export function stringifyGoldfingerValue(value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return '—';
  }
  if (typeof value === 'string') {
    return value;
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function toEditorText(value: unknown): string | undefined {
  if (value === null || value === undefined || value === '') {
    return undefined;
  }
  if (typeof value === 'string') {
    return value;
  }
  return stringifyGoldfingerValue(value);
}
