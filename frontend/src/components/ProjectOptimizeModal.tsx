import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Divider,
  Form,
  Input,
  Modal,
  Progress,
  Space,
  Spin,
  Switch,
  Tag,
  Typography,
  message,
  theme,
} from 'antd';
import {
  CheckOutlined,
  CloseOutlined,
  EditOutlined,
  LoadingOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { projectApi } from '../services/api';
import type {
  FieldSuggestion,
  OptimizableField,
  OptimizeConversationTurn,
  Project,
  ProjectOptimizeRequest,
  ProjectOptimizeResult,
} from '../types';

const { TextArea } = Input;
const { Paragraph, Text, Title } = Typography;

const OPTIMIZABLE_FIELDS: OptimizableField[] = [
  'title',
  'description',
  'theme',
  'genre',
  'world_time_period',
  'world_location',
  'world_atmosphere',
  'world_rules',
  'narrative_perspective',
];

const FIELD_LABELS: Record<OptimizableField, string> = {
  title: '项目标题',
  description: '项目简介',
  theme: '主题',
  genre: '小说类型',
  world_time_period: '时间背景',
  world_location: '地理位置',
  world_atmosphere: '氛围基调',
  world_rules: '世界规则',
  narrative_perspective: '叙事视角',
};

const FIELD_MAX_LENGTH: Record<OptimizableField, number> = {
  title: 200,
  description: 5000,
  theme: 5000,
  genre: 50,
  world_time_period: 5000,
  world_location: 5000,
  world_atmosphere: 5000,
  world_rules: 5000,
  narrative_perspective: 50,
};

type OptimizableProject = Pick<Project, OptimizableField>;
type OptimizeStatus = 'idle' | 'loading' | 'result' | 'error' | 'applying';
type AcceptedFieldMap = Partial<Record<OptimizableField, boolean>>;
type EditedValueMap = Partial<Record<OptimizableField, string>>;

export interface ProjectOptimizeModalProps {
  visible: boolean;
  onCancel: () => void;
  onApply: (acceptedFields: Partial<Record<OptimizableField, string>>) => void | Promise<void>;
  projectId: string;
  currentProject: OptimizableProject;
}

function normalizeValue(value: unknown): string {
  if (value === null || value === undefined) {
    return '';
  }

  return String(value);
}

function buildEmptySuggestionState(result: ProjectOptimizeResult | null) {
  const accepted: AcceptedFieldMap = {};
  const editedValues: EditedValueMap = {};

  if (!result) {
    return { accepted, editedValues };
  }

  for (const field of OPTIMIZABLE_FIELDS) {
    const suggestion = result.fields[field];
    if (!suggestion) {
      continue;
    }

    accepted[field] = true;
    editedValues[field] = normalizeValue(suggestion.value);
  }

  return { accepted, editedValues };
}

function sanitizeOptimizeResult(data: ProjectOptimizeResult): ProjectOptimizeResult {
  const safeFields: Partial<Record<OptimizableField, FieldSuggestion>> = {};

  for (const field of OPTIMIZABLE_FIELDS) {
    const suggestion = data.fields?.[field];
    if (!suggestion) {
      continue;
    }

    safeFields[field] = {
      value: normalizeValue(suggestion.value),
      reason: normalizeValue(suggestion.reason) || 'AI 未提供理由',
    };
  }

  return {
    fields: safeFields,
    reply: normalizeValue(data.reply),
  };
}

function isProjectOptimizeResult(value: unknown): value is ProjectOptimizeResult {
  if (!value || typeof value !== 'object') {
    return false;
  }

  const maybeResult = value as Partial<ProjectOptimizeResult>;
  return typeof maybeResult.reply === 'string' && !!maybeResult.fields && typeof maybeResult.fields === 'object';
}

function getTextAreaRows(field: OptimizableField): number {
  if (field === 'title' || field === 'genre' || field === 'narrative_perspective') {
    return 2;
  }

  if (field === 'world_rules' || field === 'description') {
    return 5;
  }

  return 3;
}

const ProjectOptimizeModal: React.FC<ProjectOptimizeModalProps> = ({
  visible,
  onCancel,
  onApply,
  projectId,
  currentProject,
}) => {
  const { token } = theme.useToken();
  const [requirement, setRequirement] = useState('');
  const [refineRequirement, setRefineRequirement] = useState('');
  const [status, setStatus] = useState<OptimizeStatus>('idle');
  const [progress, setProgress] = useState(0);
  const [progressMessage, setProgressMessage] = useState('');
  const [streamText, setStreamText] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const [result, setResult] = useState<ProjectOptimizeResult | null>(null);
  const [accepted, setAccepted] = useState<AcceptedFieldMap>({});
  const [editedValues, setEditedValues] = useState<EditedValueMap>({});
  const [conversationHistory, setConversationHistory] = useState<OptimizeConversationTurn[]>([]);

  const requestSeqRef = useRef(0);
  const abortControllerRef = useRef<AbortController | null>(null);
  const visibleRef = useRef(visible);

  const isLoading = status === 'loading';
  const isApplying = status === 'applying';
  const isBusy = isLoading || isApplying;

  const resetState = useCallback(() => {
    setRequirement('');
    setRefineRequirement('');
    setStatus('idle');
    setProgress(0);
    setProgressMessage('');
    setStreamText('');
    setErrorMessage('');
    setResult(null);
    setAccepted({});
    setEditedValues({});
    setConversationHistory([]);
  }, []);

  const abortActiveRequest = useCallback(() => {
    requestSeqRef.current += 1;
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
  }, []);

  useEffect(() => {
    visibleRef.current = visible;

    if (!visible) {
      abortActiveRequest();
      resetState();
    }
  }, [abortActiveRequest, resetState, visible]);

  useEffect(() => {
    return () => {
      visibleRef.current = false;
      abortActiveRequest();
    };
  }, [abortActiveRequest]);

  const suggestionFields = useMemo(() => {
    if (!result) {
      return [];
    }

    return OPTIMIZABLE_FIELDS.filter(field => !!result.fields[field]);
  }, [result]);

  const buildAcceptedFields = useCallback((): Partial<Record<OptimizableField, string>> => {
    if (!result) {
      return {};
    }

    const fields: Partial<Record<OptimizableField, string>> = {};
    for (const field of OPTIMIZABLE_FIELDS) {
      if (!result.fields[field] || !accepted[field]) {
        continue;
      }

      fields[field] = normalizeValue(editedValues[field]);
    }

    return fields;
  }, [accepted, editedValues, result]);

  const acceptedFields = useMemo(() => buildAcceptedFields(), [buildAcceptedFields]);
  const acceptedCount = Object.keys(acceptedFields).length;

  const isCurrentRequest = useCallback((requestId: number, controller: AbortController) => (
    visibleRef.current && requestSeqRef.current === requestId && !controller.signal.aborted
  ), []);

  const commitOptimizeResult = useCallback((
    data: ProjectOptimizeResult,
    requestId: number,
    controller: AbortController,
    nextHistory: OptimizeConversationTurn[],
  ) => {
    if (!isCurrentRequest(requestId, controller)) {
      return;
    }

    const safeResult = sanitizeOptimizeResult(data);
    const nextState = buildEmptySuggestionState(safeResult);

    setResult(safeResult);
    setAccepted(nextState.accepted);
    setEditedValues(nextState.editedValues);
    setConversationHistory([
      ...nextHistory,
      { role: 'assistant', content: safeResult.reply || '已生成项目优化建议。' },
    ]);
    setProgress(100);
    setProgressMessage('优化建议已生成');
    setStatus('result');
  }, [isCurrentRequest]);

  const runOptimizeRequest = useCallback(async (mode: 'initial' | 'refine') => {
    const rawRequirement = mode === 'initial' ? requirement : refineRequirement;
    const trimmedRequirement = rawRequirement.trim();

    if (mode === 'refine' && !trimmedRequirement) {
      message.warning('请输入追加诉求');
      return;
    }

    if (!projectId) {
      message.error('缺少项目ID，无法优化');
      return;
    }

    abortActiveRequest();
    const controller = new AbortController();
    const requestId = requestSeqRef.current + 1;
    requestSeqRef.current = requestId;
    abortControllerRef.current = controller;

    const userContent = trimmedRequirement || '均衡改进';
    const baseHistory = mode === 'refine' ? conversationHistory : [];
    const nextHistory: OptimizeConversationTurn[] = [
      ...baseHistory,
      { role: 'user', content: userContent },
    ];
    const payload: ProjectOptimizeRequest = {
      requirement: trimmedRequirement || undefined,
    };

    if (mode === 'refine') {
      payload.conversation_history = nextHistory;
      payload.current_draft = buildAcceptedFields();
    }

    if (mode === 'initial') {
      setResult(null);
      setAccepted({});
      setEditedValues({});
      setConversationHistory([]);
    }

    setStatus('loading');
    setProgress(0);
    setProgressMessage(mode === 'initial' ? '正在分析项目设定...' : '正在根据追加诉求细化...');
    setStreamText('');
    setErrorMessage('');

    let receivedResult = false;
    let receivedError = false;

    try {
      const finalResult = await projectApi.optimizeProjectStream(projectId, payload, {
        signal: controller.signal,
        onProgress: (messageText, nextProgress) => {
          if (!isCurrentRequest(requestId, controller)) {
            return;
          }

          setProgress(Math.max(0, Math.min(100, nextProgress ?? 0)));
          setProgressMessage(messageText || '正在优化项目设定...');
        },
        onChunk: (content) => {
          if (!isCurrentRequest(requestId, controller)) {
            return;
          }

          setStreamText(prev => `${prev}${content}`);
        },
        onResult: (data: ProjectOptimizeResult) => {
          receivedResult = true;
          commitOptimizeResult(data, requestId, controller, nextHistory);
        },
        onError: (error) => {
          if (!isCurrentRequest(requestId, controller)) {
            return;
          }

          receivedError = true;
          setErrorMessage(error || '优化失败');
          setStatus('error');
        },
        onComplete: () => {
          if (!isCurrentRequest(requestId, controller)) {
            return;
          }

          setProgress(prev => Math.max(prev, receivedResult ? 100 : prev));
        },
      });

      if (!receivedResult && isProjectOptimizeResult(finalResult)) {
        receivedResult = true;
        commitOptimizeResult(finalResult, requestId, controller, nextHistory);
      }
    } catch (error) {
      if (!isCurrentRequest(requestId, controller) || receivedError) {
        return;
      }

      const nextErrorMessage = error instanceof Error ? error.message : '优化失败';
      setErrorMessage(nextErrorMessage);
      setStatus('error');
    } finally {
      if (isCurrentRequest(requestId, controller)) {
        abortControllerRef.current = null;
        if (!receivedResult && !receivedError) {
          setStatus(prev => prev === 'loading' ? 'idle' : prev);
        }
      }
    }
  }, [
    abortActiveRequest,
    buildAcceptedFields,
    commitOptimizeResult,
    conversationHistory,
    isCurrentRequest,
    projectId,
    refineRequirement,
    requirement,
  ]);

  const handleCancel = () => {
    abortActiveRequest();
    resetState();
    onCancel();
  };

  const handleApply = async () => {
    const fieldsToApply = buildAcceptedFields();
    if (Object.keys(fieldsToApply).length === 0) {
      message.warning('请至少接受一个字段后再应用');
      return;
    }

    setStatus('applying');
    try {
      await onApply(fieldsToApply);
      message.success('已提交接受的优化字段');
      resetState();
      onCancel();
    } catch (error) {
      const nextErrorMessage = error instanceof Error ? error.message : '应用失败，请重试';
      setErrorMessage(nextErrorMessage);
      setStatus('result');
      message.error(nextErrorMessage);
    }
  };

  const updateAccepted = (field: OptimizableField, checked: boolean) => {
    setAccepted(prev => ({ ...prev, [field]: checked }));
  };

  const updateEditedValue = (field: OptimizableField, value: string) => {
    setEditedValues(prev => ({ ...prev, [field]: value }));
  };

  const renderOriginalValue = (field: OptimizableField) => {
    const value = normalizeValue(currentProject[field]);
    if (!value) {
      return <Text type="secondary">未填写</Text>;
    }

    return (
      <Paragraph
        style={{
          margin: 0,
          color: token.colorTextSecondary,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
        }}
      >
        {value}
      </Paragraph>
    );
  };

  const renderProgressPanel = () => {
    if (!isLoading && !progressMessage && !streamText) {
      return null;
    }

    return (
      <Card
        size="small"
        style={{
          marginTop: token.marginMD,
          borderRadius: token.borderRadiusLG,
          borderColor: isLoading ? token.colorPrimaryBorder : token.colorBorderSecondary,
          background: `linear-gradient(135deg, ${token.colorBgContainer} 0%, ${token.colorFillQuaternary} 100%)`,
        }}
      >
        <Spin spinning={isLoading} indicator={<LoadingOutlined spin />}>
          <Space direction="vertical" style={{ width: '100%' }} size="small">
            <Space style={{ width: '100%', justifyContent: 'space-between' }}>
              <Text strong>流式进度</Text>
              <Text type="secondary">{progress}%</Text>
            </Space>
            <Progress
              percent={progress}
              status={status === 'error' ? 'exception' : progress >= 100 ? 'success' : 'active'}
              showInfo={false}
            />
            <Text type={status === 'error' ? 'danger' : 'secondary'}>
              {progressMessage || '等待服务返回进度...'}
            </Text>
            {streamText && (
              <Paragraph
                style={{
                  margin: 0,
                  padding: token.paddingSM,
                  borderRadius: token.borderRadius,
                  background: token.colorFillTertiary,
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                }}
              >
                {streamText}
              </Paragraph>
            )}
          </Space>
        </Spin>
      </Card>
    );
  };

  const renderFieldReview = (field: OptimizableField) => {
    const suggestion = result?.fields[field];
    if (!suggestion) {
      return null;
    }

    const originalValue = normalizeValue(currentProject[field]);
    const editedValue = normalizeValue(editedValues[field]);
    const unchanged = originalValue === editedValue;
    const fieldAccepted = !!accepted[field];

    return (
      <Card
        key={field}
        size="small"
        data-omo-field={field}
        style={{
          borderRadius: token.borderRadiusLG,
          borderColor: fieldAccepted ? token.colorPrimaryBorder : token.colorBorderSecondary,
          background: fieldAccepted
            ? `linear-gradient(135deg, ${token.colorBgContainer} 0%, ${token.colorFillQuaternary} 100%)`
            : token.colorFillQuaternary,
        }}
      >
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(110px, 0.7fr) minmax(180px, 1.2fr) minmax(220px, 1.6fr) minmax(120px, 0.6fr)',
            gap: token.marginMD,
            alignItems: 'start',
          }}
        >
          <Space direction="vertical" size={4}>
            <Space wrap>
              <Text strong>{FIELD_LABELS[field]}</Text>
              {unchanged && <Tag color="default">无变化</Tag>}
            </Space>
            <Text type="secondary" style={{ fontSize: 12 }}>{field}</Text>
          </Space>

          <div>
            <Text type="secondary" style={{ display: 'block', marginBottom: token.marginXXS }}>
              原值
            </Text>
            <div
              style={{
                minHeight: 44,
                padding: token.paddingSM,
                borderRadius: token.borderRadius,
                background: token.colorFillTertiary,
                border: `1px solid ${token.colorBorderSecondary}`,
              }}
            >
              {renderOriginalValue(field)}
            </div>
          </div>

          <div>
            <Text type="secondary" style={{ display: 'block', marginBottom: token.marginXXS }}>
              建议值（可编辑）
            </Text>
            <TextArea
              rows={getTextAreaRows(field)}
              value={editedValue}
              maxLength={FIELD_MAX_LENGTH[field]}
              showCount
              disabled={isBusy || !fieldAccepted}
              onChange={event => updateEditedValue(field, event.target.value)}
            />
            <Text type="secondary" style={{ display: 'block', marginTop: token.marginXS, lineHeight: 1.6 }}>
              理由：{suggestion.reason || 'AI 未提供理由'}
            </Text>
          </div>

          <Space direction="vertical" size={8} style={{ width: '100%' }}>
            <Text type="secondary">接受 / 拒绝</Text>
            <Switch
              checked={fieldAccepted}
              checkedChildren="接受"
              unCheckedChildren="拒绝"
              disabled={isBusy}
              onChange={checked => updateAccepted(field, checked)}
            />
          </Space>
        </div>
      </Card>
    );
  };

  const renderComparison = () => {
    if (!result) {
      return null;
    }

    return (
      <Space direction="vertical" style={{ width: '100%', marginTop: token.marginMD }} size="middle">
        <Alert
          type={suggestionFields.length > 0 ? 'success' : 'warning'}
          showIcon
          message={suggestionFields.length > 0 ? '优化建议已生成' : '本轮没有可应用字段建议'}
          description={result.reply || 'AI 已返回结果，但没有提供额外说明。'}
        />

        {acceptedCount === 0 && suggestionFields.length > 0 && (
          <Alert
            type="warning"
            showIcon
            message="尚未接受任何字段"
            description="请至少打开一个字段的「接受」开关，才能应用优化结果。"
          />
        )}

        {suggestionFields.length > 0 && (
          <Card
            title={
              <Space wrap>
                <span>逐字段审阅</span>
                <Tag color="blue">{suggestionFields.length} 个建议</Tag>
                <Tag color={acceptedCount > 0 ? 'green' : 'orange'}>已接受 {acceptedCount}</Tag>
              </Space>
            }
            size="small"
          >
            <Space direction="vertical" style={{ width: '100%' }} size="middle">
              {suggestionFields.map(renderFieldReview)}
            </Space>
          </Card>
        )}

        <Card
          size="small"
          title={
            <Space wrap>
              <span>继续细化</span>
              {conversationHistory.length > 0 && (
                <Tag color="geekblue">临时对话 {Math.ceil(conversationHistory.length / 2)} 轮</Tag>
              )}
            </Space>
          }
        >
          <Form layout="vertical">
            <Form.Item
              label="追加诉求"
              tooltip="会携带当前已接受且编辑后的字段草稿，以及本弹窗内的临时对话历史再次请求。关闭弹窗后历史会清空。"
              style={{ marginBottom: token.marginSM }}
            >
              <TextArea
                rows={3}
                value={refineRequirement}
                maxLength={1000}
                showCount
                disabled={isBusy}
                placeholder="例如：标题更有网文爆点，但世界规则保持克制；主题更突出成长线..."
                onChange={event => setRefineRequirement(event.target.value)}
              />
            </Form.Item>
            <Button
              icon={<ReloadOutlined />}
              loading={isLoading}
              disabled={isApplying || !refineRequirement.trim()}
              onClick={() => runOptimizeRequest('refine')}
            >
              追加诉求并重新优化
            </Button>
          </Form>
        </Card>
      </Space>
    );
  };

  return (
    <Modal
      title={
        <Space>
          <EditOutlined style={{ color: token.colorPrimary }} />
          <span>AI 项目优化</span>
        </Space>
      }
      open={visible}
      onCancel={handleCancel}
      width={1080}
      centered
      maskClosable={!isBusy}
      footer={
        <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
          <Button icon={<CloseOutlined />} onClick={handleCancel} disabled={isApplying}>
            取消
          </Button>
          <Button
            type="primary"
            icon={<CheckOutlined />}
            loading={isApplying}
            disabled={!result || isLoading || acceptedCount === 0}
            onClick={handleApply}
          >
            应用已接受字段
          </Button>
        </Space>
      }
      styles={{
        body: {
          maxHeight: 'calc(100vh - 220px)',
          overflowY: 'auto',
        },
      }}
    >
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <Alert
          type="info"
          showIcon
          message="优化诉求可留空"
          description="留空时 AI 会按均衡改进处理。所有建议仅在本弹窗内审阅，不会直接落库；点击应用后只上抛已接受字段。"
        />

        <Card
          size="small"
          style={{
            borderRadius: token.borderRadiusLG,
            background: `linear-gradient(135deg, ${token.colorBgContainer} 0%, ${token.colorFillQuaternary} 100%)`,
          }}
        >
          <Form layout="vertical" disabled={isApplying}>
            <Form.Item
              label="优化诉求（可选）"
              tooltip="留空表示均衡改进；重新点击开始优化会开启一轮新的临时对话。"
              style={{ marginBottom: token.marginSM }}
            >
              <TextArea
                rows={3}
                value={requirement}
                maxLength={1000}
                showCount
                disabled={isBusy}
                placeholder="例如：强化悬疑张力，让设定更适合长篇连载；留空则进行均衡改进。"
                onChange={event => setRequirement(event.target.value)}
              />
            </Form.Item>
            <Space wrap>
              <Button
                type="primary"
                icon={isLoading ? <LoadingOutlined /> : <ThunderboltOutlined />}
                loading={isLoading}
                disabled={isApplying}
                onClick={() => runOptimizeRequest('initial')}
              >
                {result ? '重新开始优化' : '开始优化'}
              </Button>
              <Text type="secondary">
                白名单字段：标题、简介、主题、类型、世界观与叙事视角。
              </Text>
            </Space>
          </Form>
        </Card>

        {status === 'error' && errorMessage && (
          <Alert
            type="error"
            showIcon
            message="优化失败"
            description={errorMessage}
          />
        )}

        {renderProgressPanel()}

        {result && <Divider style={{ margin: `${token.marginSM}px 0` }} />}

        {result && (
          <div>
            <Title level={5} style={{ marginTop: 0 }}>
              建议审阅
            </Title>
            {renderComparison()}
          </div>
        )}
      </Space>
    </Modal>
  );
};

export default ProjectOptimizeModal;
