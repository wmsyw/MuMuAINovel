import type { SyncCandidate } from '../../types';

export type SyncReviewEntityType = 'goldfinger' | 'relationship';

export function getPayloadRecord(candidate: SyncCandidate): Record<string, unknown> {
  return candidate.payload && typeof candidate.payload === 'object' && !Array.isArray(candidate.payload)
    ? candidate.payload
    : {};
}

function getGoldfingerCandidateDiff(candidate: SyncCandidate): Array<{ label: string; value: unknown }> {
  const payload = getPayloadRecord(candidate);
  const fields: Array<[string, string]> = [
    ['name', '名称'],
    ['owner_character_name', '拥有者'],
    ['type', '类型'],
    ['status', '状态'],
    ['summary', '概要'],
    ['rules', '规则'],
    ['tasks', '任务'],
    ['rewards', '奖励'],
    ['limits', '限制'],
    ['trigger_conditions', '触发条件'],
    ['cooldown', '冷却'],
    ['aliases', '别名'],
    ['metadata', '元数据'],
  ];

  return fields
    .filter(([key]) => payload[key] !== undefined && payload[key] !== null && payload[key] !== '')
    .map(([key, label]) => ({ label, value: payload[key] }));
}

function getRelationshipCandidateDiff(candidate: SyncCandidate): Array<{ label: string; value: unknown }> {
  const payload = getPayloadRecord(candidate);
  const fields: Array<[string, string]> = [
    ['relationship_name', '关系名称'],
    ['relationship', '关系'],
    ['character_from_name', '角色A'],
    ['character_from_id', '角色A ID'],
    ['from_entity_id', '起点实体'],
    ['character_to_name', '角色B'],
    ['character_to_id', '角色B ID'],
    ['to_entity_id', '终点实体'],
    ['intimacy_level', '亲密度'],
    ['status', '状态'],
    ['description', '描述'],
    ['started_at', '开始时间'],
    ['ended_at', '结束时间'],
    ['direction', '方向策略'],
    ['old_value', '旧值快照'],
    ['new_value', '新值/正文提案'],
  ];

  return fields
    .filter(([key]) => payload[key] !== undefined && payload[key] !== null && payload[key] !== '')
    .map(([key, label]) => ({ label, value: payload[key] }));
}

export function getSyncCandidateDiff(candidate: SyncCandidate, entityType: SyncReviewEntityType): Array<{ label: string; value: unknown }> {
  return entityType === 'relationship' ? getRelationshipCandidateDiff(candidate) : getGoldfingerCandidateDiff(candidate);
}

export function formatChapter(candidate: SyncCandidate): string {
  if (candidate.source_chapter_number !== null && candidate.source_chapter_number !== undefined) {
    return `第 ${candidate.source_chapter_number} 章`;
  }
  if (candidate.source_chapter_order !== null && candidate.source_chapter_order !== undefined) {
    return `章节顺序 ${candidate.source_chapter_order}`;
  }
  if (candidate.source_chapter_id) return `章节 ${candidate.source_chapter_id}`;
  return '未记录来源章节';
}
