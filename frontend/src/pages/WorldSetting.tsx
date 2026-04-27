import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Empty,
  Flex,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
  message,
  theme,
} from 'antd';
import { CheckOutlined, CloseOutlined, EditOutlined, FormOutlined, GlobalOutlined, ReloadOutlined, RollbackOutlined, SyncOutlined } from '@ant-design/icons';
import { useStore } from '../store';
import { worldSettingCardStyles } from '../components/CardStyles';
import { projectApi, wizardStreamApi, worldSettingResultApi } from '../services/api';
import { SSELoadingOverlay } from '../components/SSELoadingOverlay';
import type {
  Project,
  ProjectWorldSnapshot,
  WorldBuildingDraftResponse,
  WorldSettingResult,
  WorldSettingResultOperationResponse,
  WorldSettingResultStatus,
} from '../types';

const { Title, Paragraph, Text } = Typography;
const { TextArea } = Input;

const WORLD_FIELD_CONFIG = [
  { key: 'world_time_period', draftKey: 'time_period', label: '时间设定' },
  { key: 'world_location', draftKey: 'location', label: '地点设定' },
  { key: 'world_atmosphere', draftKey: 'atmosphere', label: '氛围设定' },
  { key: 'world_rules', draftKey: 'rules', label: '规则设定' },
] as const;

type WorldFieldKey = typeof WORLD_FIELD_CONFIG[number]['key'];
type WorldSettingAction = 'accept' | 'reject' | 'rollback';

interface GeneratedWorldDraft {
  project_id: string;
  result_id?: string;
  world_time_period?: string | null;
  world_location?: string | null;
  world_atmosphere?: string | null;
  world_rules?: string | null;
  provider?: string | null;
  model?: string | null;
  reasoning_intensity?: string | null;
  source_type?: string | null;
  created_at?: string | null;
}

interface WorldSettingApiClient {
  listResults: typeof worldSettingResultApi.listResults;
  acceptResult: typeof worldSettingResultApi.acceptResult;
  rejectResult: typeof worldSettingResultApi.rejectResult;
  rollbackResult: typeof worldSettingResultApi.rollbackResult;
}

interface WorldSettingProps {
  apiClient?: WorldSettingApiClient;
}

interface WorldSettingActionContext {
  action: WorldSettingAction;
  result: WorldSettingResult;
  apiClient: WorldSettingApiClient;
  currentProject: Project;
  setCurrentProject: (project: Project) => void;
  refreshResults: () => Promise<void>;
}

const statusConfig: Record<WorldSettingResultStatus, { label: string; color: string }> = {
  pending: { label: '待评审', color: 'processing' },
  accepted: { label: '已生效', color: 'success' },
  rejected: { label: '已拒绝', color: 'error' },
  superseded: { label: '已被替换', color: 'default' },
};

const defaultApiClient: WorldSettingApiClient = worldSettingResultApi;

function getWorldValue(source: Partial<Record<WorldFieldKey, string | null | undefined>>, key: WorldFieldKey): string {
  return source[key]?.trim() || '';
}

function hasWorldSnapshot(source: Partial<Record<WorldFieldKey, string | null | undefined>>): boolean {
  return WORLD_FIELD_CONFIG.some(field => Boolean(getWorldValue(source, field.key)));
}

function applyActiveWorldSnapshot(project: Project, snapshot: ProjectWorldSnapshot): Project {
  return {
    ...project,
    world_time_period: snapshot.world_time_period || undefined,
    world_location: snapshot.world_location || undefined,
    world_atmosphere: snapshot.world_atmosphere || undefined,
    world_rules: snapshot.world_rules || undefined,
  };
}

function buildGeneratedWorldDraft(projectId: string, response: WorldBuildingDraftResponse): GeneratedWorldDraft {
  return {
    project_id: response.project_id || projectId,
    result_id: response.result_id,
    world_time_period: response.time_period || null,
    world_location: response.location || null,
    world_atmosphere: response.atmosphere || null,
    world_rules: response.rules || null,
    provider: response.provider,
    model: response.model,
    reasoning_intensity: response.reasoning_intensity,
    source_type: response.source_type || 'ai_generation_draft',
    created_at: response.created_at || new Date().toISOString(),
  };
}

function formatWorldResultStatus(status: WorldSettingResultStatus): string {
  return statusConfig[status]?.label || status;
}

function formatDate(value?: string | null): string {
  if (!value) return '未记录';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN');
}

async function runWorldSettingResultAction({
  action,
  result,
  apiClient,
  currentProject,
  setCurrentProject,
  refreshResults,
}: WorldSettingActionContext): Promise<WorldSettingResultOperationResponse> {
  const response = action === 'accept'
    ? await apiClient.acceptResult(result.id)
    : action === 'reject'
      ? await apiClient.rejectResult(result.id, { reason: '前端评审拒绝' })
      : await apiClient.rollbackResult(result.id, { reason: '前端评审回滚' });

  setCurrentProject(applyActiveWorldSnapshot(currentProject, response.active_world));
  await refreshResults();
  return response;
}

interface WorldSettingTestUtils {
  applyActiveWorldSnapshot: typeof applyActiveWorldSnapshot;
  buildGeneratedWorldDraft: typeof buildGeneratedWorldDraft;
  formatWorldResultStatus: typeof formatWorldResultStatus;
  hasWorldSnapshot: typeof hasWorldSnapshot;
  runWorldSettingResultAction: typeof runWorldSettingResultAction;
}

type WorldSettingComponent = ((props: WorldSettingProps) => JSX.Element | null) & {
  __testUtils: WorldSettingTestUtils;
};

const WorldSettingImpl = ({ apiClient = defaultApiClient }: WorldSettingProps) => {
  const { currentProject, setCurrentProject } = useStore();
  const [isEditModalVisible, setIsEditModalVisible] = useState(false);
  const [editForm] = Form.useForm();
  const [isSaving, setIsSaving] = useState(false);
  const [isEditProjectModalVisible, setIsEditProjectModalVisible] = useState(false);
  const [editProjectForm] = Form.useForm();
  const [isSavingProject, setIsSavingProject] = useState(false);
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [regenerateProgress, setRegenerateProgress] = useState(0);
  const [regenerateMessage, setRegenerateMessage] = useState('');
  const [isPreviewModalVisible, setIsPreviewModalVisible] = useState(false);
  const [generatedDraft, setGeneratedDraft] = useState<GeneratedWorldDraft | null>(null);
  const [worldResults, setWorldResults] = useState<WorldSettingResult[]>([]);
  const [resultsLoading, setResultsLoading] = useState(false);
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);
  const [modal, contextHolder] = Modal.useModal();
  const { token } = theme.useToken();

  const isMobile = typeof window !== 'undefined' && window.innerWidth <= 768;

  const loadWorldResults = useCallback(async () => {
    if (!currentProject?.id) {
      setWorldResults([]);
      return;
    }

    setResultsLoading(true);
    try {
      const response = await apiClient.listResults(currentProject.id, { limit: 100 });
      setWorldResults(response.items || []);
    } catch (error) {
      console.error('加载世界观结果失败:', error);
      message.error('加载世界观结果失败');
    } finally {
      setResultsLoading(false);
    }
  }, [apiClient, currentProject?.id]);

  useEffect(() => {
    void loadWorldResults();
  }, [loadWorldResults]);

  const pendingCount = useMemo(
    () => worldResults.filter(result => result.status === 'pending').length,
    [worldResults],
  );

  const openWorldEditModal = () => {
    if (!currentProject) return;
    editForm.setFieldsValue({
      world_time_period: currentProject.world_time_period || '',
      world_location: currentProject.world_location || '',
      world_atmosphere: currentProject.world_atmosphere || '',
      world_rules: currentProject.world_rules || '',
    });
    setIsEditModalVisible(true);
  };

  const openProjectEditModal = () => {
    if (!currentProject) return;
    editProjectForm.setFieldsValue({
      title: currentProject.title || '',
      description: currentProject.description || '',
      theme: currentProject.theme || '',
      genre: currentProject.genre || '',
      narrative_perspective: currentProject.narrative_perspective || '',
      target_words: currentProject.target_words || 0,
    });
    setIsEditProjectModalVisible(true);
  };

  const handleRegenerate = async () => {
    if (!currentProject) return;

    modal.confirm({
      title: '生成新的世界观结果',
      content: 'AI会生成一个待评审的世界观结果或页面草稿；不会直接替换当前生效世界观。请在结果评审中接受后再生效。',
      centered: true,
      okText: '开始生成',
      cancelText: '取消',
      onOk: async () => {
        setIsRegenerating(true);
        setRegenerateProgress(0);
        setRegenerateMessage('准备重新生成世界观...');
        setGeneratedDraft(null);

        try {
          await wizardStreamApi.regenerateWorldBuildingStream(
            currentProject.id,
            {},
            {
              onProgress: (msg: string, progress: number) => {
                setRegenerateProgress(progress);
                setRegenerateMessage(msg);
              },
              onChunk: (chunk: string) => {
                console.log('生成片段:', chunk);
              },
              onResult: (result) => {
                setGeneratedDraft(buildGeneratedWorldDraft(currentProject.id, result));
              },
              onError: (errorMsg: string) => {
                console.error('重新生成失败:', errorMsg);
                message.error(errorMsg || '重新生成失败，请重试');
              },
              onComplete: () => {
                setIsRegenerating(false);
                setRegenerateProgress(0);
                setRegenerateMessage('');
                setIsPreviewModalVisible(true);
                void loadWorldResults();
              },
            },
          );
        } catch (error) {
          console.error('重新生成出错:', error);
          message.error('重新生成出错，请重试');
          setIsRegenerating(false);
          setRegenerateProgress(0);
          setRegenerateMessage('');
        }
      },
    });
  };

  const handleWorldResultAction = async (action: WorldSettingAction, result: WorldSettingResult) => {
    if (!currentProject) return;
    setActionLoadingId(result.id);
    try {
      await runWorldSettingResultAction({
        action,
        result,
        apiClient,
        currentProject,
        setCurrentProject,
        refreshResults: loadWorldResults,
      });
      message.success(action === 'accept' ? '世界观结果已接受并生效' : action === 'reject' ? '世界观结果已拒绝' : '世界观已回滚到上一版本');
    } catch (error: unknown) {
      const err = error as { message?: string; response?: { data?: { detail?: string | { message?: string } } } };
      const detail = err.response?.data?.detail;
      const fallback = action === 'accept' ? '接受失败' : action === 'reject' ? '拒绝失败' : '回滚失败';
      message.error(typeof detail === 'string' ? detail : detail?.message || err.message || fallback);
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleManualWorldSave = async () => {
    if (!currentProject) return;
    try {
      const values = await editForm.validateFields();
      setIsSaving(true);

      const updatedProject = await projectApi.updateProject(currentProject.id, {
        world_time_period: values.world_time_period,
        world_location: values.world_location,
        world_atmosphere: values.world_atmosphere,
        world_rules: values.world_rules,
      });

      setCurrentProject(updatedProject);
      message.success('当前生效世界观已手动更新');
      setIsEditModalVisible(false);
      editForm.resetFields();
    } catch (error) {
      console.error('更新世界观失败:', error);
      message.error('更新失败，请重试');
    } finally {
      setIsSaving(false);
    }
  };

  const handleProjectInfoSave = async () => {
    if (!currentProject) return;
    try {
      const values = await editProjectForm.validateFields();
      setIsSavingProject(true);

      const updatedProject = await projectApi.updateProject(currentProject.id, {
        title: values.title,
        description: values.description,
        theme: values.theme,
        genre: values.genre,
        narrative_perspective: values.narrative_perspective,
        target_words: values.target_words,
      });

      setCurrentProject(updatedProject);
      message.success('项目基础信息更新成功');
      setIsEditProjectModalVisible(false);
      editProjectForm.resetFields();
    } catch (error) {
      console.error('更新项目基础信息失败:', error);
      message.error('更新失败，请重试');
    } finally {
      setIsSavingProject(false);
    }
  };

  const handleCopyDraftToManualEdit = () => {
    if (!generatedDraft) return;
    editForm.setFieldsValue({
      world_time_period: generatedDraft.world_time_period || '',
      world_location: generatedDraft.world_location || '',
      world_atmosphere: generatedDraft.world_atmosphere || '',
      world_rules: generatedDraft.world_rules || '',
    });
    setIsPreviewModalVisible(false);
    setIsEditModalVisible(true);
    message.info('已复制到手动编辑表单，保存前不会修改当前世界观');
  };

  const getFieldAccent = (fieldKey: WorldFieldKey): string => {
    if (fieldKey === 'world_location') return token.colorSuccess;
    if (fieldKey === 'world_atmosphere') return token.colorWarning;
    if (fieldKey === 'world_rules') return token.colorError;
    return token.colorPrimary;
  };

  const renderWorldFieldBlock = (field: typeof WORLD_FIELD_CONFIG[number], value: string, muted = false) => (
    <div key={field.key} style={{ marginBottom: 16 }}>
      <Title level={5} style={{ color: getFieldAccent(field.key), marginBottom: 8 }}>
        {field.label}
      </Title>
      <Paragraph
        style={{
          marginBottom: 0,
          fontSize: 15,
          lineHeight: 1.8,
          padding: 16,
          background: muted ? token.colorFillQuaternary : token.colorBgLayout,
          borderRadius: token.borderRadius,
          borderLeft: `4px solid ${getFieldAccent(field.key)}`,
          whiteSpace: 'pre-wrap',
        }}
      >
        {value || '未设定'}
      </Paragraph>
    </div>
  );

  const renderSnapshotBlocks = (source: Partial<Record<WorldFieldKey, string | null | undefined>>) => {
    if (!hasWorldSnapshot(source)) {
      return <Empty description="暂无当前生效世界观" />;
    }

    return (
      <div style={{ padding: '8px 0' }}>
        {WORLD_FIELD_CONFIG.map(field => renderWorldFieldBlock(field, getWorldValue(source, field.key)))}
      </div>
    );
  };

  const renderResultDiff = (result: WorldSettingResult | GeneratedWorldDraft) => (
    <div style={{ display: 'grid', gap: 10 }}>
      {WORLD_FIELD_CONFIG.map(field => {
        const activeValue = currentProject ? getWorldValue(currentProject, field.key) : '';
        const candidateValue = getWorldValue(result, field.key);
        const changed = activeValue !== candidateValue;
        return (
          <div
            key={`${result.project_id}-${field.key}`}
            style={{
              display: 'grid',
              gridTemplateColumns: isMobile ? '1fr' : '120px 1fr 1fr',
              gap: 10,
              padding: 12,
              border: `1px solid ${changed ? token.colorPrimaryBorder : token.colorBorderSecondary}`,
              borderRadius: token.borderRadiusLG,
              background: changed ? token.colorPrimaryBg : token.colorFillQuaternary,
            }}
          >
            <Space direction="vertical" size={4}>
              <Text strong>{field.label}</Text>
              <Tag color={changed ? 'blue' : 'default'}>{changed ? '有变化' : '无变化'}</Tag>
            </Space>
            <div>
              <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>当前生效</Text>
              <Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }} ellipsis={{ rows: 3, expandable: true, symbol: '展开' }}>
                {activeValue || '未设定'}
              </Paragraph>
            </div>
            <div>
              <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>候选结果</Text>
              <Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }} ellipsis={{ rows: 3, expandable: true, symbol: '展开' }}>
                {candidateValue || '未设定'}
              </Paragraph>
            </div>
          </div>
        );
      })}
    </div>
  );

  const renderResultMetadata = (result: WorldSettingResult | GeneratedWorldDraft) => (
    <Space wrap size={[8, 6]}>
      <Text type="secondary">来源：{result.source_type || '未记录'}</Text>
      {'run_id' in result && result.run_id && <Text type="secondary">运行：{result.run_id}</Text>}
      {result.provider && <Text type="secondary">Provider：{result.provider}</Text>}
      {result.model && <Text type="secondary">模型：{result.model}</Text>}
      {result.reasoning_intensity && <Text type="secondary">推理强度：{result.reasoning_intensity}</Text>}
      <Text type="secondary">创建：{formatDate(result.created_at)}</Text>
    </Space>
  );

  const renderWorldResultCard = (result: WorldSettingResult) => {
    const status = statusConfig[result.status] || statusConfig.pending;
    return (
      <Card
        key={result.id}
        size="small"
        style={{
          marginBottom: 12,
          borderRadius: token.borderRadiusLG,
          borderColor: result.status === 'pending' ? token.colorPrimaryBorder : token.colorBorderSecondary,
        }}
        title={(
          <Space wrap>
            <Tag color={status.color}>{status.label}</Tag>
            <Text strong>结果 {result.id.slice(0, 8)}</Text>
            {result.accepted_at && <Text type="secondary">接受：{formatDate(result.accepted_at)}</Text>}
          </Space>
        )}
        extra={renderResultMetadata(result)}
      >
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          {renderResultDiff(result)}
          <Space wrap style={{ justifyContent: 'flex-end', width: '100%' }}>
            {result.status === 'pending' && (
              <>
                <Button
                  type="primary"
                  icon={<CheckOutlined />}
                  loading={actionLoadingId === result.id}
                  onClick={() => handleWorldResultAction('accept', result)}
                >
                  接受结果
                </Button>
                <Popconfirm
                  title="拒绝这个世界观结果？"
                  okText="拒绝"
                  cancelText="取消"
                  okButtonProps={{ danger: true }}
                  onConfirm={() => handleWorldResultAction('reject', result)}
                >
                  <Button danger icon={<CloseOutlined />} loading={actionLoadingId === result.id}>拒绝</Button>
                </Popconfirm>
              </>
            )}
            {result.status === 'accepted' && (
              <Popconfirm
                title="回滚当前世界观到上一已接受版本？"
                okText="回滚"
                cancelText="取消"
                onConfirm={() => handleWorldResultAction('rollback', result)}
              >
                <Button icon={<RollbackOutlined />} loading={actionLoadingId === result.id}>回滚</Button>
              </Popconfirm>
            )}
          </Space>
        </Space>
      </Card>
    );
  };

  const renderWorldResultList = () => {
    if (resultsLoading) {
      return <div style={{ padding: 32, textAlign: 'center' }}><Spin tip="加载世界观结果..." /></div>;
    }

    if (worldResults.length === 0) {
      return <Empty description="暂无世界观生成结果。使用 AI 生成后，将在这里评审再接受。" />;
    }

    return <div>{worldResults.map(renderWorldResultCard)}</div>;
  };

  if (!currentProject) return null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {contextHolder}
      <div style={{
        position: 'sticky',
        top: 0,
        zIndex: 10,
        backgroundColor: token.colorBgContainer,
        padding: '16px 0',
        marginBottom: 24,
        borderBottom: `1px solid ${token.colorBorderSecondary}`,
      }}>
        <Flex justify="space-between" align="flex-start" gap={12} wrap="wrap">
          <div style={{ display: 'flex', alignItems: 'center', minWidth: 'fit-content' }}>
            <GlobalOutlined style={{ fontSize: 24, marginRight: 12, color: token.colorPrimary }} />
            <div>
              <h2 style={{ margin: 0, whiteSpace: 'nowrap' }}>世界设定</h2>
              <Text type="secondary">当前生效快照与 AI 候选结果分开管理</Text>
            </div>
          </div>
          <Flex gap={8} wrap="wrap" style={{ flex: '0 1 auto' }}>
            <Button icon={<ReloadOutlined />} onClick={loadWorldResults} loading={resultsLoading}>刷新结果</Button>
            <Button icon={<SyncOutlined />} onClick={handleRegenerate} disabled={isRegenerating}>
              AI生成结果
            </Button>
            <Button type="primary" icon={<FormOutlined />} onClick={openProjectEditModal}>
              编辑基础信息
            </Button>
            <Button type="primary" icon={<EditOutlined />} onClick={openWorldEditModal}>
              手动编辑生效快照
            </Button>
          </Flex>
        </Flex>
      </div>

      <div style={{ flex: 1, overflowY: 'auto' }}>
        <Alert
          type="info"
          showIcon
          message="世界观采用结果评审流"
          description="AI生成内容先进入待评审结果；只有点击“接受结果”后才会更新当前生效世界观。手动编辑仍可直接维护当前快照，两条路径相互独立。"
          style={{ marginBottom: 16 }}
        />

        <Card
          style={{ ...worldSettingCardStyles.sectionCard, marginBottom: 16 }}
          title={(
            <Space>
              <GlobalOutlined />
              <span style={{ fontSize: 18, fontWeight: 500 }}>当前生效世界观</span>
              {hasWorldSnapshot(currentProject) ? <Tag color="success">Active</Tag> : <Tag>空快照</Tag>}
            </Space>
          )}
          extra={<Button size="small" icon={<EditOutlined />} onClick={openWorldEditModal}>手动编辑</Button>}
        >
          {renderSnapshotBlocks(currentProject)}
        </Card>

        <Card
          style={{ ...worldSettingCardStyles.sectionCard, marginBottom: 16 }}
          title={(
            <Space>
              <span style={{ fontSize: 18, fontWeight: 500 }}>AI结果评审</span>
              <Tag color={pendingCount > 0 ? 'processing' : 'default'}>待评审 {pendingCount}</Tag>
            </Space>
          )}
          extra={<Button size="small" onClick={loadWorldResults} loading={resultsLoading}>刷新</Button>}
        >
          {renderWorldResultList()}
        </Card>

        <Card
          style={{ ...worldSettingCardStyles.sectionCard, marginBottom: 16 }}
          title={<span style={{ fontSize: 18, fontWeight: 500 }}>基础信息</span>}
        >
          <Descriptions bordered column={1} styles={{ label: { width: 120, fontWeight: 500 } }}>
            <Descriptions.Item label="小说名称">{currentProject.title}</Descriptions.Item>
            {currentProject.description && <Descriptions.Item label="小说简介">{currentProject.description}</Descriptions.Item>}
            <Descriptions.Item label="小说主题">{currentProject.theme || '未设定'}</Descriptions.Item>
            <Descriptions.Item label="小说类型">{currentProject.genre || '未设定'}</Descriptions.Item>
            <Descriptions.Item label="叙事视角">{currentProject.narrative_perspective || '未设定'}</Descriptions.Item>
            <Descriptions.Item label="目标字数">
              {currentProject.target_words ? `${currentProject.target_words.toLocaleString()} 字` : '未设定'}
            </Descriptions.Item>
          </Descriptions>
        </Card>
      </div>

      <Modal
        title="手动编辑当前生效世界观"
        open={isEditModalVisible}
        centered
        onCancel={() => {
          setIsEditModalVisible(false);
          editForm.resetFields();
        }}
        onOk={handleManualWorldSave}
        confirmLoading={isSaving}
        width={800}
        okText="保存到当前快照"
        cancelText="取消"
      >
        <Alert
          type="warning"
          showIcon
          message="这是手动生效路径"
          description="保存后会直接更新当前项目世界观；如需评审 AI 生成内容，请返回“AI结果评审”接受对应结果。"
          style={{ marginBottom: 16 }}
        />
        <Form form={editForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item label="时间设定" name="world_time_period" rules={[{ required: true, message: '请输入时间设定' }]}>
            <TextArea rows={4} placeholder="描述故事发生的时代背景..." showCount maxLength={1000} />
          </Form.Item>
          <Form.Item label="地点设定" name="world_location" rules={[{ required: true, message: '请输入地点设定' }]}>
            <TextArea rows={4} placeholder="描述故事发生的地理位置和环境..." showCount maxLength={1000} />
          </Form.Item>
          <Form.Item label="氛围设定" name="world_atmosphere" rules={[{ required: true, message: '请输入氛围设定' }]}>
            <TextArea rows={4} placeholder="描述故事的整体氛围和基调..." showCount maxLength={1000} />
          </Form.Item>
          <Form.Item label="规则设定" name="world_rules" rules={[{ required: true, message: '请输入规则设定' }]}>
            <TextArea rows={4} placeholder="描述这个世界的特殊规则和设定..." showCount maxLength={1000} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="编辑项目基础信息"
        open={isEditProjectModalVisible}
        centered
        onCancel={() => {
          setIsEditProjectModalVisible(false);
          editProjectForm.resetFields();
        }}
        onOk={handleProjectInfoSave}
        confirmLoading={isSavingProject}
        width={800}
        okText="保存"
        cancelText="取消"
      >
        <Form form={editProjectForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item label="小说名称" name="title" rules={[{ required: true, message: '请输入小说名称' }, { max: 200, message: '名称不能超过200字' }]}>
            <Input placeholder="请输入小说名称" showCount maxLength={200} />
          </Form.Item>
          <Form.Item label="小说简介" name="description" rules={[{ max: 1000, message: '简介不能超过1000字' }]}>
            <TextArea rows={4} placeholder="请输入小说简介（选填）" showCount maxLength={1000} />
          </Form.Item>
          <Form.Item label="小说主题" name="theme" rules={[{ max: 500, message: '主题不能超过500字' }]}>
            <TextArea rows={3} placeholder="请输入小说主题（选填）" showCount maxLength={500} />
          </Form.Item>
          <Form.Item label="小说类型" name="genre" rules={[{ max: 100, message: '类型不能超过100字' }]}>
            <Input placeholder="请输入小说类型，如：玄幻、都市、科幻等（选填）" showCount maxLength={100} />
          </Form.Item>
          <Form.Item label="叙事视角" name="narrative_perspective">
            <Select
              placeholder="请选择叙事视角（选填）"
              allowClear
              options={[
                { label: '第一人称', value: '第一人称' },
                { label: '第三人称', value: '第三人称' },
                { label: '全知视角', value: '全知视角' },
              ]}
            />
          </Form.Item>
          <Form.Item label="目标字数" name="target_words" rules={[{ type: 'number', min: 0, message: '目标字数不能为负数' }, { type: 'number', max: 2147483647, message: '目标字数超出范围' }]}>
            <InputNumber style={{ width: '100%' }} placeholder="请输入目标字数（选填，最大21亿字）" min={0} max={2147483647} step={1000} addonAfter="字" />
          </Form.Item>
        </Form>
      </Modal>

      <SSELoadingOverlay loading={isRegenerating} progress={regenerateProgress} message={regenerateMessage} />

      <Modal
        title="AI生成结果草稿（未生效）"
        open={isPreviewModalVisible}
        centered
        width={900}
        onCancel={() => setIsPreviewModalVisible(false)}
        footer={(
          <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
            <Button onClick={() => setIsPreviewModalVisible(false)}>保留草稿</Button>
            {generatedDraft?.result_id ? (
              <Button type="primary" onClick={() => {
                setIsPreviewModalVisible(false);
                void loadWorldResults();
              }}>
                查看结果列表
              </Button>
            ) : (
              <Button type="primary" onClick={handleCopyDraftToManualEdit}>复制到手动编辑</Button>
            )}
          </Space>
        )}
      >
        {generatedDraft ? (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Alert
              type={generatedDraft.result_id ? 'success' : 'info'}
              showIcon
              message={generatedDraft.result_id ? '已生成待评审结果' : '本次生成仅为页面草稿'}
              description={generatedDraft.result_id
                ? '请在结果列表中审阅差异并点击“接受结果”后生效。'
                : '当前后端未返回结果编号，因此不会写入版本结果表，也不会修改当前生效快照。可复制到手动编辑表单后自行保存。'}
            />
            {renderResultMetadata(generatedDraft)}
            {renderResultDiff(generatedDraft)}
          </Space>
        ) : (
          <Empty description="暂无生成结果" />
        )}
      </Modal>
    </div>
  );
};

const WorldSetting = WorldSettingImpl as WorldSettingComponent;

WorldSetting.__testUtils = {
  applyActiveWorldSnapshot,
  buildGeneratedWorldDraft,
  formatWorldResultStatus,
  hasWorldSnapshot,
  runWorldSettingResultAction,
};

export default WorldSetting;
