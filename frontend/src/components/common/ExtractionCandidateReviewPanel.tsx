import { useCallback, useEffect, useMemo, useState, type ComponentProps, type ReactNode } from 'react';
import { Alert, Button, Card, Empty, Popconfirm, Progress, Select, Space, Spin, Tabs, Tag, Typography, message, theme } from 'antd';
import { CheckOutlined, RollbackOutlined, SwapOutlined, StopOutlined } from '@ant-design/icons';
import { extractionApi } from '../../services/api';
import type {
  CandidateAcceptRequest,
  CandidateReviewResponse,
  CanonicalTargetType,
  ExtractionCandidate,
  ExtractionCandidateStatus,
  ExtractionCandidateType,
  Settings,
} from '../../types';

const { Paragraph, Text } = Typography;

const AI_ENTITY_GENERATION_POLICY_COPY = '默认从正文自动提取角色/组织/职业；开启后才允许 AI 直接生成入库';

export interface CanonicalReviewOption {
  id: string;
  name: string;
  description?: string;
}

interface ExtractionReviewApiClient {
  listCandidates: typeof extractionApi.listCandidates;
  acceptCandidate: typeof extractionApi.acceptCandidate;
  rejectCandidate: typeof extractionApi.rejectCandidate;
  mergeCandidate: typeof extractionApi.mergeCandidate;
  rollbackCandidate: typeof extractionApi.rollbackCandidate;
}

interface ReviewActionContext {
  action: 'accept' | 'reject' | 'merge' | 'rollback';
  candidate: ExtractionCandidate;
  apiClient: ExtractionReviewApiClient;
  targetType: CanonicalTargetType;
  targetId?: string;
  rejectReason?: string;
  rollbackReason?: string;
  refreshCandidates: () => Promise<void>;
  refreshCanonical?: () => Promise<void> | void;
}

interface ExtractionCandidateReviewPanelProps {
  projectId?: string;
  entityLabel: string;
  candidateTypes: ExtractionCandidateType[];
  canonicalTargetType: CanonicalTargetType;
  canonicalOptions: CanonicalReviewOption[];
  canonicalChildren: ReactNode;
  canonicalCount?: number;
  onCanonicalChanged?: () => Promise<void> | void;
  extraTabs?: NonNullable<ComponentProps<typeof Tabs>['items']>;
  initialCandidates?: ExtractionCandidate[];
  autoLoad?: boolean;
  apiClient?: ExtractionReviewApiClient;
  defaultActiveKey?: string;
}

type CandidateSplit = {
  discovered: ExtractionCandidate[];
  merge: ExtractionCandidate[];
  history: ExtractionCandidate[];
};

const statusConfig: Record<ExtractionCandidateStatus, { label: string; color: string }> = {
  pending: { label: '待评审', color: 'processing' },
  accepted: { label: '已入库', color: 'success' },
  rejected: { label: '已拒绝', color: 'error' },
  merged: { label: '已合并', color: 'blue' },
  superseded: { label: '已替换', color: 'default' },
};

const candidateTypeLabels: Record<ExtractionCandidateType, string> = {
  character: '角色',
  organization: '组织',
  profession: '职业',
  relationship: '关系',
  goldfinger: '金手指',
  organization_affiliation: '组织归属',
  profession_assignment: '职业变更',
  world_fact: '世界观事实',
  character_state: '角色状态',
};

function isAiGenerationOverrideEnabled(settings?: Pick<Settings, 'allow_ai_entity_generation'> | null): boolean {
  return Boolean(settings?.allow_ai_entity_generation);
}

function splitExtractionCandidates(candidates: ExtractionCandidate[]): CandidateSplit {
  return candidates.reduce<CandidateSplit>((result, candidate) => {
    if (candidate.status !== 'pending') {
      result.history.push(candidate);
      return result;
    }

    if (candidate.canonical_target_id) {
      result.merge.push(candidate);
    } else {
      result.discovered.push(candidate);
    }
    return result;
  }, { discovered: [], merge: [], history: [] });
}

function formatStatus(status: ExtractionCandidateStatus): string {
  return statusConfig[status]?.label || status;
}

function formatCandidateType(type: ExtractionCandidateType): string {
  return candidateTypeLabels[type] || type;
}

function formatConfidence(confidence: number): number {
  return Math.max(0, Math.min(100, Math.round(confidence * 100)));
}

function stringifyPayloadValue(value: unknown): string | undefined {
  if (value === null || value === undefined || value === '') return undefined;
  if (Array.isArray(value)) {
    return value
      .map(item => stringifyPayloadValue(item))
      .filter((item): item is string => Boolean(item))
      .join('、') || undefined;
  }
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>;
    return stringifyPayloadValue(record.name ?? record.alias ?? record.value ?? record.label);
  }
  return String(value);
}

function buildCandidateSummaryFields(candidate: ExtractionCandidate): Array<{ label: string; value: string }> {
  const payload = candidate.payload || {};
  const fields = [
    { label: '候选名称', value: stringifyPayloadValue(candidate.display_name ?? payload.name ?? payload.display_name) },
    { label: '别名', value: stringifyPayloadValue(payload.aliases ?? payload.alias) },
    { label: '关系/职位', value: stringifyPayloadValue(payload.relationship_type ?? payload.relationship_name ?? payload.position) },
    { label: '阶段/等级', value: stringifyPayloadValue(payload.career_stage ?? payload.stage ?? payload.rank) },
    { label: '状态变化', value: stringifyPayloadValue(payload.status ?? payload.state ?? payload.current_state) },
  ];
  return fields.filter((field): field is { label: string; value: string } => Boolean(field.value));
}

async function runCandidateReviewAction({
  action,
  candidate,
  apiClient,
  targetType,
  targetId,
  rejectReason,
  rollbackReason,
  refreshCandidates,
  refreshCanonical,
}: ReviewActionContext): Promise<CandidateReviewResponse> {
  let response: CandidateReviewResponse;

  if (action === 'accept') {
    const payload: CandidateAcceptRequest = targetId ? { target_type: targetType, target_id: targetId } : {};
    response = await apiClient.acceptCandidate(candidate.id, payload);
  } else if (action === 'merge') {
    if (!targetId) {
      throw new Error('请选择要合并到的已入库目标');
    }
    response = await apiClient.mergeCandidate(candidate.id, { target_type: targetType, target_id: targetId });
  } else if (action === 'reject') {
    response = await apiClient.rejectCandidate(candidate.id, { reason: rejectReason || '前端评审拒绝' });
  } else {
    response = await apiClient.rollbackCandidate(candidate.id, { reason: rollbackReason || '前端评审回滚' });
  }

  await refreshCandidates();
  await refreshCanonical?.();
  return response;
}

const defaultApiClient: ExtractionReviewApiClient = extractionApi;
const emptyCandidates: ExtractionCandidate[] = [];

interface ExtractionCandidateReviewPanelTestUtils {
  AI_ENTITY_GENERATION_POLICY_COPY: string;
  buildCandidateSummaryFields: typeof buildCandidateSummaryFields;
  formatCandidateType: typeof formatCandidateType;
  formatConfidence: typeof formatConfidence;
  formatStatus: typeof formatStatus;
  isAiGenerationOverrideEnabled: typeof isAiGenerationOverrideEnabled;
  runCandidateReviewAction: typeof runCandidateReviewAction;
  splitExtractionCandidates: typeof splitExtractionCandidates;
}

type ExtractionCandidateReviewPanelComponent = ((props: ExtractionCandidateReviewPanelProps) => JSX.Element) & {
  __testUtils: ExtractionCandidateReviewPanelTestUtils;
};

const ExtractionCandidateReviewPanelImpl = ({
  projectId,
  entityLabel,
  candidateTypes,
  canonicalTargetType,
  canonicalOptions,
  canonicalChildren,
  canonicalCount,
  onCanonicalChanged,
  extraTabs = [],
  initialCandidates = emptyCandidates,
  autoLoad = true,
  apiClient = defaultApiClient,
  defaultActiveKey = 'canonical',
}: ExtractionCandidateReviewPanelProps) => {
  const { token } = theme.useToken();
  const [loading, setLoading] = useState(false);
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<ExtractionCandidate[]>(initialCandidates);
  const [selectedTargets, setSelectedTargets] = useState<Record<string, string | undefined>>({});

  const loadCandidates = useCallback(async () => {
    if (!projectId || candidateTypes.length === 0) {
      setCandidates([]);
      return;
    }

    setLoading(true);
    try {
      const responses = await Promise.all(candidateTypes.map(type => apiClient.listCandidates({
        project_id: projectId,
        type,
        limit: 200,
      })));
      const merged = responses.flatMap(response => response.items);
      merged.sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')));
      setCandidates(merged);
    } catch (error) {
      console.error('加载抽取候选失败:', error);
      message.error('加载正文发现候选失败');
    } finally {
      setLoading(false);
    }
  }, [apiClient, candidateTypes, projectId]);

  useEffect(() => {
    if (autoLoad) {
      void loadCandidates();
    }
  }, [autoLoad, loadCandidates]);

  useEffect(() => {
    setCandidates(initialCandidates);
  }, [initialCandidates]);

  const split = useMemo(() => splitExtractionCandidates(candidates), [candidates]);

  const handleAction = async (
    action: ReviewActionContext['action'],
    candidate: ExtractionCandidate,
    targetId?: string,
  ) => {
    setActionLoadingId(candidate.id);
    try {
      await runCandidateReviewAction({
        action,
        candidate,
        apiClient,
        targetType: canonicalTargetType,
        targetId,
        refreshCandidates: loadCandidates,
        refreshCanonical: onCanonicalChanged,
      });
      message.success(action === 'accept' ? '候选已接受入库' : action === 'merge' ? '候选已合并' : action === 'reject' ? '候选已拒绝' : '候选已回滚');
    } catch (error: unknown) {
      const fallback = action === 'accept' ? '接受失败' : action === 'merge' ? '合并失败' : action === 'reject' ? '拒绝失败' : '回滚失败';
      const err = error as { message?: string; response?: { data?: { detail?: string | { message?: string } } } };
      const detail = err.response?.data?.detail;
      message.error(typeof detail === 'string' ? detail : detail?.message || err.message || fallback);
    } finally {
      setActionLoadingId(null);
    }
  };

  const renderCandidateCard = (candidate: ExtractionCandidate) => {
    const confidence = formatConfidence(candidate.confidence);
    const targetId = selectedTargets[candidate.id] ?? candidate.canonical_target_id ?? undefined;
    const summaryFields = buildCandidateSummaryFields(candidate);
    const status = statusConfig[candidate.status] || statusConfig.pending;
    const canReview = candidate.status === 'pending';
    const canRollback = candidate.status === 'accepted' || candidate.status === 'merged';

    return (
      <Card
        key={candidate.id}
        size="small"
        style={{
          marginBottom: 12,
          borderColor: token.colorBorderSecondary,
          borderRadius: token.borderRadiusLG,
        }}
        title={
          <Space wrap>
            <Tag color="geekblue">{formatCandidateType(candidate.candidate_type)}</Tag>
            <Text strong>{candidate.display_name || candidate.normalized_name || '未命名候选'}</Text>
            <Tag color={status.color}>{status.label}</Tag>
          </Space>
        }
      >
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center' }}>
            <Text type="secondary">来源：{candidate.source_chapter_number ? `第 ${candidate.source_chapter_number} 章` : '未知章节'}</Text>
            <Text type="secondary">位置：{candidate.source_start_offset}–{candidate.source_end_offset}</Text>
            {candidate.story_time_label && <Tag>{candidate.story_time_label}</Tag>}
            <div style={{ minWidth: 160, flex: '0 1 220px' }} aria-label={`置信度 ${confidence}%`}>
              <Progress percent={confidence} size="small" strokeColor={confidence >= 80 ? token.colorSuccess : token.colorPrimary} />
              <Text type="secondary" style={{ fontSize: 12 }}>置信度 {confidence}%</Text>
            </div>
          </div>

          <div
            style={{
              padding: '10px 12px',
              background: token.colorFillTertiary,
              border: `1px solid ${token.colorBorderSecondary}`,
              borderRadius: token.borderRadius,
            }}
          >
            <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>证据片段</Text>
            <Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }} ellipsis={{ rows: 3, expandable: true, symbol: '展开' }}>
              {candidate.evidence_text}
            </Paragraph>
          </div>

          {summaryFields.length > 0 && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 8 }}>
              {summaryFields.map(field => (
                <div key={`${candidate.id}-${field.label}`}>
                  <Text type="secondary" style={{ fontSize: 12 }}>{field.label}</Text>
                  <div><Text>{field.value}</Text></div>
                </div>
              ))}
            </div>
          )}

          {candidate.rejection_reason && (
            <Alert type="warning" showIcon message="拒绝原因" description={candidate.rejection_reason} />
          )}

          <Space wrap style={{ justifyContent: 'space-between', width: '100%' }}>
            {canReview && (
              <Space wrap>
                <Select
                  allowClear
                  showSearch
                  placeholder={`选择已入库${entityLabel}用于合并`}
                  value={targetId}
                  style={{ minWidth: 220 }}
                  optionFilterProp="label"
                  onChange={(value) => setSelectedTargets(prev => ({ ...prev, [candidate.id]: value }))}
                  options={canonicalOptions.map(option => ({
                    label: option.description ? `${option.name} · ${option.description}` : option.name,
                    value: option.id,
                  }))}
                />
                <Button
                  type="primary"
                  icon={<CheckOutlined />}
                  loading={actionLoadingId === candidate.id}
                  onClick={() => handleAction('accept', candidate, targetId)}
                >
                  接受入库
                </Button>
                <Button
                  icon={<SwapOutlined />}
                  disabled={!targetId}
                  loading={actionLoadingId === candidate.id}
                  onClick={() => handleAction('merge', candidate, targetId)}
                >
                  合并
                </Button>
                <Popconfirm
                  title="拒绝这个候选？"
                  okText="拒绝"
                  cancelText="取消"
                  okButtonProps={{ danger: true }}
                  onConfirm={() => handleAction('reject', candidate)}
                >
                  <Button danger icon={<StopOutlined />} loading={actionLoadingId === candidate.id}>拒绝</Button>
                </Popconfirm>
              </Space>
            )}
            {canRollback && (
              <Popconfirm
                title="回滚该候选造成的入库/合并变更？"
                okText="回滚"
                cancelText="取消"
                onConfirm={() => handleAction('rollback', candidate)}
              >
                <Button icon={<RollbackOutlined />} loading={actionLoadingId === candidate.id}>回滚</Button>
              </Popconfirm>
            )}
          </Space>
        </Space>
      </Card>
    );
  };

  const renderCandidateList = (items: ExtractionCandidate[], emptyText: string) => {
    if (loading) {
      return <div style={{ padding: 32, textAlign: 'center' }}><Spin tip="加载正文发现候选..." /></div>;
    }

    if (items.length === 0) {
      return <Empty description={emptyText} />;
    }

    return <div>{items.map(renderCandidateCard)}</div>;
  };

  const tabs = [
    {
      key: 'canonical',
      label: `已入库 (${canonicalCount ?? canonicalOptions.length})`,
      children: canonicalChildren,
    },
    {
      key: 'discovered',
      label: `正文发现 (${split.discovered.length})`,
      children: renderCandidateList(split.discovered, `暂无新的${entityLabel}候选。保存或导入章节后，系统会从正文中自动发现。`),
    },
    {
      key: 'merge',
      label: `待合并 (${split.merge.length})`,
      children: renderCandidateList(split.merge, `暂无需要合并到已有${entityLabel}的候选。`),
    },
    {
      key: 'history',
      label: `已拒绝/历史 (${split.history.length})`,
      children: renderCandidateList(split.history, '暂无评审历史。'),
    },
    ...extraTabs,
  ];

  return (
    <Space direction="vertical" style={{ width: '100%', minHeight: 0 }} size="middle">
      <Alert
        type="info"
        showIcon
        message="抽取优先工作流"
        description={`${entityLabel}默认从章节正文自动发现，评审后再入库；手动创建/编辑仍可直接使用。`}
      />
      <Tabs items={tabs} defaultActiveKey={defaultActiveKey} destroyOnHidden={false} />
    </Space>
  );
};

export const ExtractionCandidateReviewPanel = ExtractionCandidateReviewPanelImpl as ExtractionCandidateReviewPanelComponent;

ExtractionCandidateReviewPanel.__testUtils = {
  AI_ENTITY_GENERATION_POLICY_COPY,
  buildCandidateSummaryFields,
  formatCandidateType,
  formatConfidence,
  formatStatus,
  isAiGenerationOverrideEnabled,
  runCandidateReviewAction,
  splitExtractionCandidates,
};

export default ExtractionCandidateReviewPanel;
