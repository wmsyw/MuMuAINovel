import { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Empty, Input, List, Space, Spin, Tag, Typography, message, theme } from 'antd';
import { CheckOutlined, CloseOutlined, ReloadOutlined } from '@ant-design/icons';
import type { SyncCandidate } from '../../types';
import { syncApi } from '../../services/api';
import { formatConfidence, stringifyGoldfingerValue } from './constants';
import {
  formatChapter,
  getPayloadRecord,
  getSyncCandidateDiff,
  type SyncReviewEntityType,
} from './syncReviewUtils';

const { Paragraph, Text } = Typography;
const EMPTY_CANDIDATES: SyncCandidate[] = [];

interface SyncReviewApiClient {
  listCandidates: typeof syncApi.listCandidates;
  approveCandidate: typeof syncApi.approveCandidate;
  rejectCandidate: typeof syncApi.rejectCandidate;
}

interface GoldfingerPendingReviewPanelProps {
  projectId: string;
  entityType?: SyncReviewEntityType;
  onReviewed?: () => Promise<void> | void;
  initialCandidates?: SyncCandidate[];
  autoLoad?: boolean;
  apiClient?: SyncReviewApiClient;
}

const REVIEW_META: Record<SyncReviewEntityType, {
  title: string;
  countLabel: string;
  alertMessage: string;
  alertDescription: string;
  emptyDescription: string;
  fallbackReason: string;
  rejectReason: string;
  approveTargetType: string;
}> = {
  goldfinger: {
    title: '待审核正文同步',
    countLabel: '金手指',
    alertMessage: '金手指候选需要人工确认',
    alertDescription: '来自章节正文同步的候选会保留来源章节、证据片段、置信度和变更明细；通过后写入金手指档案，拒绝会记录审核原因。',
    emptyDescription: '暂无待审核金手指候选',
    fallbackReason: '命中金手指同步策略，需要人工确认后合并。',
    rejectReason: '前端金手指管理页拒绝',
    approveTargetType: 'goldfinger',
  },
  relationship: {
    title: '待审核关系同步',
    countLabel: '关系',
    alertMessage: '关系候选需要人工确认',
    alertDescription: '低置信度、方向冲突或关系名冲突不会直接覆盖正式关系；候选会展示来源章节、证据、旧值/新值和审核原因。',
    emptyDescription: '暂无待审核关系候选',
    fallbackReason: '关系同步发现冲突或低置信度事实，需要人工确认后合并。',
    rejectReason: '前端关系管理页拒绝',
    approveTargetType: 'relationship',
  },
};

const REVIEW_REASON_LABELS: Record<string, string> = {
  low_confidence: '低置信度，需要人工确认',
  self_loop: '关系端点指向同一实体',
  direction_conflict: '关系方向与现有记录冲突',
  relationship_type_conflict: '关系类型与现有记录冲突',
  relationship_name_conflict: '关系名称与现有记录冲突',
  destructive_change_requires_review: '破裂/结束类关系变更需要确认',
  owner_ambiguity: '归属对象存在歧义',
  status_contradiction: '状态与现有档案冲突',
};

function stringifyCandidateValue(value: unknown): string {
  return stringifyGoldfingerValue(value);
}

function getGoldfingerCandidateTitle(candidate: SyncCandidate): string {
  const payload = getPayloadRecord(candidate);
  return String(candidate.display_name || payload.name || payload.normalized_name || candidate.normalized_name || '未命名金手指');
}

function getRelationshipEndpointLabel(payload: Record<string, unknown>, keys: string[]): string | undefined {
  for (const key of keys) {
    const value = payload[key];
    if (value !== undefined && value !== null && value !== '') return String(value);
  }
  return undefined;
}

function getRelationshipCandidateTitle(candidate: SyncCandidate): string {
  const payload = getPayloadRecord(candidate);
  const relation = payload.relationship_name || payload.relationship || payload.state || candidate.display_name || '关系候选';
  const from = getRelationshipEndpointLabel(payload, ['character_from_name', 'from_entity_name', 'character_from_id', 'from_entity_id']);
  const to = getRelationshipEndpointLabel(payload, ['character_to_name', 'to_entity_name', 'character_to_id', 'to_entity_id']);
  return from && to ? `${from} → ${to} · ${relation}` : String(relation);
}

function getCandidateTitle(candidate: SyncCandidate, entityType: SyncReviewEntityType): string {
  return entityType === 'relationship' ? getRelationshipCandidateTitle(candidate) : getGoldfingerCandidateTitle(candidate);
}

function formatReviewReason(candidate: SyncCandidate, fallbackReason: string): string {
  const reason = candidate.review_required_reason || candidate.rejection_reason;
  if (!reason) return fallbackReason;
  return REVIEW_REASON_LABELS[reason] ? `${REVIEW_REASON_LABELS[reason]}（${reason}）` : reason;
}

export default function GoldfingerPendingReviewPanel({
  projectId,
  entityType = 'goldfinger',
  onReviewed,
  initialCandidates = EMPTY_CANDIDATES,
  autoLoad = true,
  apiClient = syncApi,
}: GoldfingerPendingReviewPanelProps) {
  const { token } = theme.useToken();
  const [candidates, setCandidates] = useState<SyncCandidate[]>(initialCandidates);
  const [loading, setLoading] = useState(false);
  const [reviewingId, setReviewingId] = useState<string | null>(null);
  const [rejectReasons, setRejectReasons] = useState<Record<string, string>>({});
  const meta = REVIEW_META[entityType];

  const loadCandidates = useCallback(async () => {
    setLoading(true);
    try {
      const response = await apiClient.listCandidates(projectId, {
        entity_type: entityType,
        status: 'pending',
        limit: 50,
      });
      setCandidates(response.items || []);
    } finally {
      setLoading(false);
    }
  }, [apiClient, entityType, projectId]);

  useEffect(() => {
    if (autoLoad) {
      void loadCandidates();
    }
  }, [autoLoad, loadCandidates]);

  useEffect(() => {
    setCandidates(initialCandidates);
  }, [initialCandidates]);

  const pendingCount = useMemo(() => candidates.length, [candidates]);

  const handleApprove = async (candidate: SyncCandidate) => {
    setReviewingId(candidate.id);
    try {
      await apiClient.approveCandidate(candidate.id, {
        target_type: meta.approveTargetType,
        target_id: candidate.canonical_target_id || undefined,
        override: entityType === 'relationship' ? true : undefined,
      });
      message.success(`已通过「${getCandidateTitle(candidate, entityType)}」`);
      await loadCandidates();
      await onReviewed?.();
    } finally {
      setReviewingId(null);
    }
  };

  const handleReject = async (candidate: SyncCandidate) => {
    setReviewingId(candidate.id);
    try {
      await apiClient.rejectCandidate(candidate.id, { reason: rejectReasons[candidate.id]?.trim() || meta.rejectReason });
      message.success(`已拒绝「${getCandidateTitle(candidate, entityType)}」`);
      setRejectReasons(prev => ({ ...prev, [candidate.id]: '' }));
      await loadCandidates();
      await onReviewed?.();
    } finally {
      setReviewingId(null);
    }
  };

  return (
    <Card
      title={<Space><span>{meta.title}</span><Tag color={pendingCount > 0 ? 'orange' : 'default'}>{pendingCount}</Tag></Space>}
      extra={<Button size="small" icon={<ReloadOutlined />} onClick={loadCandidates} loading={loading}>刷新</Button>}
    >
      <Alert
        type="info"
        showIcon
        message={meta.alertMessage}
        description={meta.alertDescription}
        style={{ marginBottom: token.marginMD }}
      />
      {loading ? (
        <div style={{ padding: token.paddingXL, textAlign: 'center' }}><Spin tip="加载候选中..." /></div>
      ) : candidates.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={meta.emptyDescription} />
      ) : (
        <List
          itemLayout="vertical"
          dataSource={candidates}
          renderItem={candidate => {
            const diff = getSyncCandidateDiff(candidate, entityType);
            return (
              <List.Item key={candidate.id}>
                <Card
                  size="small"
                  style={{
                    borderColor: entityType === 'relationship' ? token.colorWarningBorder : token.colorBorderSecondary,
                    borderStyle: entityType === 'relationship' ? 'dashed' : 'solid',
                    borderRadius: token.borderRadiusLG,
                  }}
                >
                  <Space direction="vertical" size="small" style={{ width: '100%' }}>
                    <Space wrap>
                      <Text strong>{getCandidateTitle(candidate, entityType)}</Text>
                      <Tag color="cyan">{formatChapter(candidate)}</Tag>
                      <Tag color="gold">置信度 {formatConfidence(candidate.confidence)}</Tag>
                      {candidate.canonical_target_id && <Tag color="orange">待合并</Tag>}
                      {candidate.trigger_type && <Tag>{candidate.trigger_type}</Tag>}
                    </Space>
                    <div>
                      <Text type="secondary">证据摘录</Text>
                      <Paragraph style={{ margin: `${token.marginXXS}px 0 0`, padding: token.paddingSM, background: token.colorFillTertiary, borderRadius: token.borderRadius }}>
                        {candidate.evidence_text || '暂无证据片段'}
                      </Paragraph>
                    </div>
                    <div>
                      <Text type="secondary">拟应用变更 / Diff 明细</Text>
                      <div style={{ marginTop: token.marginXS, display: 'grid', gap: token.marginXS }}>
                        {diff.length === 0 ? (
                          <Text type="secondary">候选 payload 未提供可展示字段</Text>
                        ) : diff.map(item => (
                          <div key={item.label} style={{ borderLeft: `3px solid ${entityType === 'relationship' ? token.colorWarning : token.colorPrimary}`, paddingLeft: token.paddingSM }}>
                            <Text strong>{item.label}</Text>
                            <pre style={{ margin: `${token.marginXXS}px 0 0`, whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontFamily: 'inherit' }}>
                              {stringifyCandidateValue(item.value)}
                            </pre>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div>
                      <Text type="secondary">审核原因</Text>
                      <Paragraph style={{ marginBottom: 0 }}>
                        {formatReviewReason(candidate, meta.fallbackReason)}
                      </Paragraph>
                    </div>
                    <Input.TextArea
                      rows={2}
                      placeholder="拒绝原因（可选）"
                      value={rejectReasons[candidate.id] || ''}
                      onChange={event => setRejectReasons(prev => ({ ...prev, [candidate.id]: event.target.value }))}
                    />
                    <Space wrap>
                      <Button
                        type="primary"
                        icon={<CheckOutlined />}
                        loading={reviewingId === candidate.id}
                        onClick={() => handleApprove(candidate)}
                      >
                        通过并合并
                      </Button>
                      <Button
                        danger
                        icon={<CloseOutlined />}
                        loading={reviewingId === candidate.id}
                        onClick={() => handleReject(candidate)}
                      >
                        拒绝
                      </Button>
                    </Space>
                  </Space>
                </Card>
              </List.Item>
            );
          }}
        />
      )}
    </Card>
  );
}
