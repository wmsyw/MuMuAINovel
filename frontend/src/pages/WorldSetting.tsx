import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  Flex,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
  message,
  theme,
} from 'antd';
import { AppstoreOutlined, CheckOutlined, CloseOutlined, DeleteOutlined, EditOutlined, FormOutlined, GlobalOutlined, PlusOutlined, ReloadOutlined, RollbackOutlined, SyncOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { useStore } from '../store';
import { useIsMobile } from '../hooks/useMediaQuery';
import { useProjectSync } from '../store/hooks';
import { worldSettingCardStyles } from '../components/common/CardStyles';
import ProjectOptimizeModal from '../components/ProjectOptimizeModal';
import { projectApi, wizardStreamApi, worldSettingResultApi, worldSettingTemplateApi } from '../services/api';
import { SSELoadingOverlay } from '../components/progress/SSELoadingOverlay';
import type {
  OptimizableField,
  Project,
  ProjectWorldSnapshot,
  ProjectWorldSettingData,
  WorldBuildingDraftResponse,
  WorldSettingResult,
  WorldSettingResultOperationResponse,
  WorldSettingResultStatus,
  WorldSettingFieldDefinition,
  WorldSettingTemplate,
} from '../types';
import { sx } from '../styles/sx';

const { Title, Paragraph, Text } = Typography;
const { TextArea } = Input;

const WORLD_FIELD_CONFIG = [
  { key: 'world_time_period', draftKey: 'time_period', label: '时间设定' },
  { key: 'world_location', draftKey: 'location', label: '地点设定' },
  { key: 'world_atmosphere', draftKey: 'atmosphere', label: '氛围设定' },
  { key: 'world_rules', draftKey: 'rules', label: '规则设定' },
] as const;

const LEGACY_DYNAMIC_FIELDS: Record<string, WorldSettingFieldDefinition> = {
  time_period: { label: '时间设定', type: 'textarea', required: false },
  location: { label: '地点设定', type: 'textarea', required: false },
  atmosphere: { label: '氛围设定', type: 'textarea', required: false },
  rules: { label: '规则设定', type: 'textarea', required: false },
};

function getProjectWorldSettingData(project: Project): ProjectWorldSettingData {
  const legacyValues = {
    time_period: project.world_time_period || '',
    location: project.world_location || '',
    atmosphere: project.world_atmosphere || '',
    rules: project.world_rules || '',
  };
  const existing = project.world_setting_data;
  if (existing?.fields) {
    return {
      ...existing,
      fields: { ...existing.fields },
      values: { ...legacyValues, ...(existing.values || {}) },
    };
  }
  return {
    template_id: null,
    template_name: '基础世界设定',
    fields: { ...LEGACY_DYNAMIC_FIELDS },
    values: legacyValues,
  };
}

function normalizeDynamicValues(
  values: ProjectWorldSettingData['values'],
  fields: Record<string, WorldSettingFieldDefinition>,
): ProjectWorldSettingData['values'] {
  const normalized: ProjectWorldSettingData['values'] = {};
  for (const [key, definition] of Object.entries(fields)) {
    const value = values[key];
    if (definition.type === 'list') {
      const items = Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string').map(item => item.trim()).filter(Boolean) : [];
      if (definition.required && items.length === 0) throw new Error(`字段 ${definition.label} 不能为空`);
      normalized[key] = items;
      continue;
    }
    const text = typeof value === 'string' ? value.trim() : value == null ? '' : String(value).trim();
    if (definition.required && !text) throw new Error(`字段 ${definition.label} 不能为空`);
    normalized[key] = text || null;
  }
  return normalized;
}

function dynamicValuesToLegacy(values: ProjectWorldSettingData['values']) {
  const textValue = (key: string) => {
    const value = values[key];
    return typeof value === 'string' && value.trim() ? value.trim() : undefined;
  };
  return {
    world_time_period: textValue('time_period'),
    world_location: textValue('location'),
    world_atmosphere: textValue('atmosphere'),
    world_rules: textValue('rules'),
  };
}

type WorldFieldKey = typeof WORLD_FIELD_CONFIG[number]['key'];
type WorldSettingAction = 'accept' | 'reject' | 'rollback';
type OptimizableProject = Pick<Project, OptimizableField>;

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

interface DynamicWorldCandidate {
  template_id?: string | null;
  template_name?: string | null;
  fields?: Record<string, WorldSettingFieldDefinition>;
  values?: Record<string, unknown>;
}

function extractDynamicWorldCandidate(rawResult: WorldSettingResult['raw_result'], action: WorldSettingAction): DynamicWorldCandidate | undefined {
  if (!rawResult || typeof rawResult !== 'object' || Array.isArray(rawResult)) return undefined;
  const raw = rawResult as Record<string, unknown>;
  const keys = action === 'rollback'
    ? ['world_setting_data_before', 'world_setting_data_after', 'world_setting_data', 'dynamic_values', 'values']
    : ['world_setting_data_after', 'world_setting_data', 'dynamic_world_setting_data', 'dynamic_values', 'values'];
  for (const key of keys) {
    const candidate = raw[key];
    if (!candidate || typeof candidate !== 'object' || Array.isArray(candidate)) continue;
    if (key === 'dynamic_values' || key === 'values') return { values: candidate as Record<string, unknown> };
    return candidate as DynamicWorldCandidate;
  }
  return undefined;
}

function applyActiveWorldSnapshot(
  project: Project,
  snapshot: ProjectWorldSnapshot,
  candidate?: DynamicWorldCandidate,
): Project {
  const data = getProjectWorldSettingData(project);
  const legacyValues = {
    time_period: snapshot.world_time_period ?? null,
    location: snapshot.world_location ?? null,
    atmosphere: snapshot.world_atmosphere ?? null,
    rules: snapshot.world_rules ?? null,
  };
  const candidateFields = candidate?.fields && typeof candidate.fields === 'object' ? candidate.fields : data.fields;
  const values: ProjectWorldSettingData['values'] = {
    ...data.values,
    ...legacyValues,
    ...(candidate?.values as ProjectWorldSettingData['values'] | undefined || {}),
  };
  return {
    ...project,
    world_time_period: snapshot.world_time_period?.trim() || undefined,
    world_location: snapshot.world_location?.trim() || undefined,
    world_atmosphere: snapshot.world_atmosphere?.trim() || undefined,
    world_rules: snapshot.world_rules?.trim() || undefined,
    world_setting_data: {
      template_id: candidate?.template_id ?? data.template_id ?? null,
      template_name: candidate?.template_name ?? data.template_name ?? '基础世界设定',
      fields: candidateFields,
      values,
    },
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
function worldProjectFingerprint(project: Project | null | undefined): string {
  if (!project) return '';
  return JSON.stringify({
    updated_at: project.updated_at,
    world_time_period: project.world_time_period || null,
    world_location: project.world_location || null,
    world_atmosphere: project.world_atmosphere || null,
    world_rules: project.world_rules || null,
    world_setting_data: project.world_setting_data || null,
  });
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

  setCurrentProject(applyActiveWorldSnapshot(currentProject, response.active_world, extractDynamicWorldCandidate(response.result.raw_result, action)));
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
  const { updateProject: updateProjectSync } = useProjectSync();
  const [isEditModalVisible, setIsEditModalVisible] = useState(false);
  const [editForm] = Form.useForm();
  const [isSaving, setIsSaving] = useState(false);
  const [isEditProjectModalVisible, setIsEditProjectModalVisible] = useState(false);
  const [editProjectForm] = Form.useForm();
  const [isSavingProject, setIsSavingProject] = useState(false);
  const [isOptimizeModalVisible, setIsOptimizeModalVisible] = useState(false);
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [regenerateProgress, setRegenerateProgress] = useState(0);
  const [regenerateMessage, setRegenerateMessage] = useState('');
  const [isPreviewModalVisible, setIsPreviewModalVisible] = useState(false);
  const [generatedDraft, setGeneratedDraft] = useState<GeneratedWorldDraft | null>(null);
  const [worldResults, setWorldResults] = useState<WorldSettingResult[]>([]);
  const [resultsLoading, setResultsLoading] = useState(false);
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);
  const [modal, contextHolder] = Modal.useModal();
  const [templates, setTemplates] = useState<WorldSettingTemplate[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [templateApplyingId, setTemplateApplyingId] = useState<string | null>(null);
  const [isTemplateModalVisible, setIsTemplateModalVisible] = useState(false);
  const [worldFieldDefinitions, setWorldFieldDefinitions] = useState<Record<string, WorldSettingFieldDefinition>>(LEGACY_DYNAMIC_FIELDS);
  const [activeTemplate, setActiveTemplate] = useState<{ id?: string | null; name?: string | null }>({});
  const [customFieldLabel, setCustomFieldLabel] = useState('');
  const [customFieldType, setCustomFieldType] = useState<WorldSettingFieldDefinition['type']>('textarea');
  const { token } = theme.useToken();

  const isMobile = useIsMobile();
  const currentProjectRef = useRef(currentProject);
  const worldEditBaseRef = useRef<string | null>(null);

  useEffect(() => {
    currentProjectRef.current = currentProject;
  }, [currentProject]);

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

  const populateWorldEditForm = (data: ProjectWorldSettingData) => {
    setWorldFieldDefinitions(data.fields);
    setActiveTemplate({ id: data.template_id, name: data.template_name });
    editForm.setFieldsValue({ dynamic_values: data.values });
  };

  const openWorldEditModal = () => {
    if (!currentProject) return;
    populateWorldEditForm(getProjectWorldSettingData(currentProject));
    worldEditBaseRef.current = worldProjectFingerprint(currentProject);
    setIsEditModalVisible(true);
  };

  const openTemplateModal = async () => {
    setIsTemplateModalVisible(true);
    if (templates.length > 0) return;
    setTemplatesLoading(true);
    try {
      const response = await worldSettingTemplateApi.listTemplates();
      setTemplates(response.items);
    } catch (error) {
      console.error('加载世界设定模板失败:', error);
      message.error('加载世界设定模板失败');
    } finally {
      setTemplatesLoading(false);
    }
  };

  const applyWorldTemplate = async (template: WorldSettingTemplate) => {
    if (!currentProject) return;
    setTemplateApplyingId(template.id);
    try {
      const response = await worldSettingTemplateApi.applyTemplate({
        project_id: currentProject.id,
        template_id: template.id,
      });
      const updatedProject = await projectApi.getProject(currentProject.id);
      setCurrentProject(updatedProject);
      populateWorldEditForm(response.world_setting_data);
      worldEditBaseRef.current = worldProjectFingerprint(updatedProject);
      setIsTemplateModalVisible(false);
      setIsEditModalVisible(true);
      message.success(`已应用「${template.name}」模板，可继续修改后保存`);
    } catch (error) {
      console.error('应用世界设定模板失败:', error);
      message.error('应用世界设定模板失败');
    } finally {
      setTemplateApplyingId(null);
    }
  };

  const addCustomWorldField = () => {
    const label = customFieldLabel.trim();
    if (!label) {
      message.warning('请输入自定义字段名称');
      return;
    }
    const key = `custom_${Date.now().toString(36)}`;
    setWorldFieldDefinitions(previous => ({
      ...previous,
      [key]: { label, type: customFieldType, required: false },
    }));
    setCustomFieldLabel('');
  };

  const removeCustomWorldField = (key: string) => {
    setWorldFieldDefinitions(previous => {
      const next = { ...previous };
      delete next[key];
      return next;
    });
    editForm.setFieldValue(['dynamic_values', key], undefined);
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
      setIsSaving(true);
      const baseFingerprint = worldEditBaseRef.current || worldProjectFingerprint(currentProject);
      const latestInStore = currentProjectRef.current;
      if (baseFingerprint && worldProjectFingerprint(latestInStore) !== baseFingerprint) {
        if (latestInStore) {
          populateWorldEditForm(getProjectWorldSettingData(latestInStore));
        }
        message.warning('世界观已更新，请基于最新生效快照重新编辑后保存');
        return;
      }

      // Confirm the server revision as well: an accepted result may have been
      // committed in another tab while this modal remained open.
      const latestProject = await projectApi.getProject(currentProject.id);
      if (baseFingerprint && worldProjectFingerprint(latestProject) !== baseFingerprint) {
        setCurrentProject(latestProject);
        populateWorldEditForm(getProjectWorldSettingData(latestProject));
        message.warning('世界观已更新，请基于最新生效快照重新编辑后保存');
        return;
      }

      const formValues = await editForm.validateFields();
      const dynamicValues = normalizeDynamicValues(formValues.dynamic_values || {}, worldFieldDefinitions);
      const worldSettingData: ProjectWorldSettingData = {
        template_id: activeTemplate.id || null,
        template_name: activeTemplate.name || '自定义世界设定',
        fields: worldFieldDefinitions,
        values: dynamicValues,
      };
      const updatedProject = await projectApi.updateProject(currentProject.id, {
        ...dynamicValuesToLegacy(dynamicValues),
        world_setting_data: worldSettingData,
      });

      setCurrentProject(updatedProject);
      worldEditBaseRef.current = worldProjectFingerprint(updatedProject);
      message.success('动态世界设定已保存');
      setIsEditModalVisible(false);
      editForm.resetFields();
    } catch (error) {
      console.error('更新世界观失败:', error);
      message.error(error instanceof Error ? error.message : '更新失败，请重试');
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

  const handleOptimizeApply = async (acceptedFields: Partial<Record<OptimizableField, string>>) => {
    if (!currentProject) return;

    const updatedProject = await updateProjectSync(currentProject.id, acceptedFields);
    setCurrentProject(updatedProject);
    setIsOptimizeModalVisible(false);
    message.success('项目优化应用成功');
  };

  const handleCopyDraftToManualEdit = () => {
    if (!generatedDraft || !currentProject) return;
    const data = getProjectWorldSettingData(currentProject);
    populateWorldEditForm({
      ...data,
      values: {
        ...data.values,
        time_period: generatedDraft.world_time_period || '',
        location: generatedDraft.world_location || '',
        atmosphere: generatedDraft.world_atmosphere || '',
        rules: generatedDraft.world_rules || '',
      },
    });
    setIsPreviewModalVisible(false);
    setIsEditModalVisible(true);
    message.info('已复制到动态编辑表单，保存前不会修改当前世界观');
  };

  const getFieldAccent = (fieldKey: WorldFieldKey): string => {
    if (fieldKey === 'world_location') return token.colorSuccess;
    if (fieldKey === 'world_atmosphere') return token.colorWarning;
    if (fieldKey === 'world_rules') return token.colorError;
    return token.colorPrimary;
  };

  const renderWorldFieldBlock = (field: typeof WORLD_FIELD_CONFIG[number], value: string, muted = false) => (
    <div key={field.key} className="u-6srbul">
      <Title level={5} className={sx({ color: getFieldAccent(field.key), marginBottom: 8 })}>
        {field.label}
      </Title>
      <Paragraph
        className={sx({
          marginBottom: 0,
          fontSize: 15,
          lineHeight: 1.8,
          padding: 16,
          background: muted ? token.colorFillQuaternary : token.colorBgLayout,
          borderRadius: token.borderRadius,
          borderLeft: `4px solid ${getFieldAccent(field.key)}`,
          whiteSpace: 'pre-wrap',
        })}
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
      <div className="u-15tlmef">
        {WORLD_FIELD_CONFIG.map(field => renderWorldFieldBlock(field, getWorldValue(source, field.key)))}
      </div>
    );
  };

  const renderDynamicSnapshot = (data: ProjectWorldSettingData) => {
    const entries = Object.entries(data.fields);
    if (entries.length === 0) return <Empty description="暂无当前生效世界观" />;
    return (
      <div className="u-15tlmef">
        {data.template_name && <Tag color="blue" className="u-6srbul">模板：{data.template_name}</Tag>}
        {entries.map(([key, definition]) => {
          const value = data.values[key];
          const displayValue = Array.isArray(value) ? value.join('、') : value || '未设定';
          return (
            <div key={key} className="u-6srbul">
              <Title level={5} className={sx({ color: token.colorPrimary, marginBottom: 8 })}>{definition.label}</Title>
              <Paragraph className={sx({ marginBottom: 0, fontSize: 15, lineHeight: 1.8, padding: 16, background: token.colorBgLayout, borderRadius: token.borderRadius, borderLeft: `4px solid ${token.colorPrimary}`, whiteSpace: 'pre-wrap' })}>
                {displayValue}
              </Paragraph>
            </div>
          );
        })}
      </div>
    );
  };

  const renderResultDiff = (result: WorldSettingResult | GeneratedWorldDraft) => (
    <div className="u-1tlo4ox">
      {WORLD_FIELD_CONFIG.map(field => {
        const activeValue = currentProject ? getWorldValue(currentProject, field.key) : '';
        const candidateValue = getWorldValue(result, field.key);
        const changed = activeValue !== candidateValue;
        return (
          <div
            key={`${result.project_id}-${field.key}`}
            className={sx({
              display: 'grid',
              gridTemplateColumns: isMobile ? '1fr' : '120px 1fr 1fr',
              gap: 10,
              padding: 12,
              border: `1px solid ${changed ? token.colorPrimaryBorder : token.colorBorderSecondary}`,
              borderRadius: token.borderRadiusLG,
              background: changed ? token.colorPrimaryBg : token.colorFillQuaternary,
            })}
          >
            <Space direction="vertical" size={4}>
              <Text strong>{field.label}</Text>
              <Tag color={changed ? 'blue' : 'default'}>{changed ? '有变化' : '无变化'}</Tag>
            </Space>
            <div>
              <Text type="secondary" className="u-187isz9">当前生效</Text>
              <Paragraph className="u-19o9sm6" ellipsis={{ rows: 3, expandable: true, symbol: '展开' }}>
                {activeValue || '未设定'}
              </Paragraph>
            </div>
            <div>
              <Text type="secondary" className="u-187isz9">候选结果</Text>
              <Paragraph className="u-19o9sm6" ellipsis={{ rows: 3, expandable: true, symbol: '展开' }}>
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
        className={sx({
          marginBottom: 12,
          borderRadius: token.borderRadiusLG,
          borderColor: result.status === 'pending' ? token.colorPrimaryBorder : token.colorBorderSecondary,
        })}
        title={(
          <Space wrap>
            <Tag color={status.color}>{status.label}</Tag>
            <Text strong>结果 {result.id.slice(0, 8)}</Text>
            {result.accepted_at && <Text type="secondary">接受：{formatDate(result.accepted_at)}</Text>}
          </Space>
        )}
        extra={renderResultMetadata(result)}
      >
        <Space direction="vertical" size="middle" className="u-1f3r3s">
          {renderResultDiff(result)}
          <Space wrap className="u-vu04oz">
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
      return <div className="u-1ntu15k"><Spin tip="加载世界观结果..." /></div>;
    }

    if (worldResults.length === 0) {
      return <Empty description="暂无世界观生成结果。使用 AI 生成后，将在这里评审再接受。" />;
    }

    return <div>{worldResults.map(renderWorldResultCard)}</div>;
  };

  if (!currentProject) return null;

  const optimizeCurrentProject: OptimizableProject = {
    title: currentProject.title || '',
    description: currentProject.description || '',
    theme: currentProject.theme || '',
    genre: currentProject.genre || '',
    world_time_period: currentProject.world_time_period || '',
    world_location: currentProject.world_location || '',
    world_atmosphere: currentProject.world_atmosphere || '',
    world_rules: currentProject.world_rules || '',
    narrative_perspective: currentProject.narrative_perspective || '',
  };

  return (
    <div className="u-14esoxf">
      {contextHolder}
      <div className={sx({
        position: 'sticky',
        top: 0,
        zIndex: 10,
        backgroundColor: token.colorBgContainer,
        padding: '16px 0',
        marginBottom: 24,
        borderBottom: `1px solid ${token.colorBorderSecondary}`,
      })}>
        <Flex justify="space-between" align="flex-start" gap={12} wrap="wrap">
          <div className="u-1v6xesu">
            <GlobalOutlined className={sx({ fontSize: 24, marginRight: 12, color: token.colorPrimary })} />
            <div>
              <h2 className="u-472fwd">世界设定</h2>
              <Text type="secondary">当前生效快照与 AI 候选结果分开管理</Text>
            </div>
          </div>
          <Flex gap={8} wrap="wrap" className="u-1cdsmfx">
            <Button icon={<AppstoreOutlined />} onClick={() => void openTemplateModal()}>
              选择模板
            </Button>
            <Button icon={<ReloadOutlined />} onClick={loadWorldResults} loading={resultsLoading}>刷新结果</Button>
            <Button icon={<ThunderboltOutlined />} onClick={() => setIsOptimizeModalVisible(true)}>
              AI 优化项目
            </Button>
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

      <div className="u-250t5n">
        <Alert
          type="info"
          showIcon
          message="世界观采用结果评审流"
          description="AI生成内容先进入待评审结果；只有点击“接受结果”后才会更新当前生效世界观。手动编辑仍可直接维护当前快照，两条路径相互独立。"
          className="u-6srbul"
        />

        <Card
          className={sx({ ...worldSettingCardStyles.sectionCard, marginBottom: 16 })}
          title={(
            <Space>
              <GlobalOutlined />
              <span className="u-s424pl">当前生效世界观</span>
              {(currentProject.world_setting_data || hasWorldSnapshot(currentProject)) ? <Tag color="success">Active</Tag> : <Tag>空快照</Tag>}
            </Space>
          )}
          extra={<Button size="small" icon={<EditOutlined />} onClick={openWorldEditModal}>手动编辑</Button>}
        >
          {currentProject.world_setting_data ? renderDynamicSnapshot(currentProject.world_setting_data) : renderSnapshotBlocks(currentProject)}
        </Card>

        <Card
          className={sx({ ...worldSettingCardStyles.sectionCard, marginBottom: 16 })}
          title={(
            <Space>
              <span className="u-s424pl">AI结果评审</span>
              <Tag color={pendingCount > 0 ? 'processing' : 'default'}>待评审 {pendingCount}</Tag>
            </Space>
          )}
          extra={<Button size="small" onClick={loadWorldResults} loading={resultsLoading}>刷新</Button>}
        >
          {renderWorldResultList()}
        </Card>

        <Card
          className={sx({ ...worldSettingCardStyles.sectionCard, marginBottom: 16 })}
          title={<span className="u-s424pl">基础信息</span>}
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
        title="选择世界设定模板"
        open={isTemplateModalVisible}
        centered
        width={900}
        footer={null}
        onCancel={() => setIsTemplateModalVisible(false)}
      >
        <Spin spinning={templatesLoading}>
          <Row gutter={[16, 16]}>
            {templates.map(template => (
              <Col xs={24} md={12} key={template.id}>
                <Card
                  size="small"
                  title={template.name}
                  extra={<Tag>{template.category}</Tag>}
                  actions={[
                    <Button
                      key="apply"
                      type="primary"
                      loading={templateApplyingId === template.id}
                      onClick={() => void applyWorldTemplate(template)}
                    >
                      应用并编辑
                    </Button>,
                  ]}
                >
                  <Space wrap>
                    {Object.values(template.fields).map(field => <Tag key={field.label}>{field.label}</Tag>)}
                  </Space>
                </Card>
              </Col>
            ))}
          </Row>
          {!templatesLoading && templates.length === 0 && <Empty description="暂无可用模板" />}
        </Spin>
      </Modal>

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
          message={activeTemplate.name ? `正在编辑：${activeTemplate.name}` : '这是手动生效路径'}
          description="保存后会直接更新当前项目世界观；模板字段和自定义字段会统一持久化。"
          className="u-6srbul"
        />
        <Form form={editForm} layout="vertical" className="u-1ir3dsh">
          {Object.entries(worldFieldDefinitions).map(([key, definition]) => (
            <Form.Item
              key={key}
              label={(
                <Space>
                  <span>{definition.label}</span>
                  {definition.required && <Tag color="red">必填</Tag>}
                  {key.startsWith('custom_') && (
                    <Button type="text" danger size="small" icon={<DeleteOutlined />} onClick={() => removeCustomWorldField(key)}>删除</Button>
                  )}
                </Space>
              )}
              name={['dynamic_values', key]}
              rules={definition.required ? [{ validator: (_, value) => {
                if (definition.type === 'list') {
                  return Array.isArray(value) && value.some(item => typeof item === 'string' && item.trim())
                    ? Promise.resolve()
                    : Promise.reject(new Error(`请输入${definition.label}`));
                }
                return typeof value === 'string' && value.trim()
                  ? Promise.resolve()
                  : Promise.reject(new Error(`请输入${definition.label}`));
              } }] : undefined}
            >
              {definition.type === 'list' ? (
                <Select mode="tags" tokenSeparators={[',', '，']} placeholder="输入后按回车添加多项" />
              ) : definition.type === 'text' ? (
                <Input placeholder={`请输入${definition.label}`} maxLength={1000} />
              ) : (
                <TextArea rows={4} placeholder={`请输入${definition.label}`} showCount maxLength={2000} />
              )}
            </Form.Item>
          ))}
          <Card size="small" title="添加自定义字段">
            <Space direction={isMobile ? 'vertical' : 'horizontal'} className="u-1f3r3s">
              <Input value={customFieldLabel} onChange={event => setCustomFieldLabel(event.target.value)} placeholder="字段名称，如：货币体系" maxLength={100} />
              <Select
                value={customFieldType}
                onChange={setCustomFieldType}
                className="u-um21xv"
                options={[
                  { label: '单行文本', value: 'text' },
                  { label: '多行文本', value: 'textarea' },
                  { label: '列表', value: 'list' },
                ]}
              />
              <Button icon={<PlusOutlined />} onClick={addCustomWorldField}>添加字段</Button>
            </Space>
          </Card>
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
        <Form form={editProjectForm} layout="vertical" className="u-1ir3dsh">
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
            <InputNumber className="u-1f3r3s" placeholder="请输入目标字数（选填，最大21亿字）" min={0} max={2147483647} step={1000} addonAfter="字" />
          </Form.Item>
        </Form>
      </Modal>

      <ProjectOptimizeModal
        visible={isOptimizeModalVisible}
        onCancel={() => setIsOptimizeModalVisible(false)}
        onApply={handleOptimizeApply}
        projectId={currentProject.id}
        currentProject={optimizeCurrentProject}
      />

      <SSELoadingOverlay loading={isRegenerating} progress={regenerateProgress} message={regenerateMessage} />

      <Modal
        title="AI生成结果草稿（未生效）"
        open={isPreviewModalVisible}
        centered
        width={900}
        onCancel={() => setIsPreviewModalVisible(false)}
        footer={(
          <Space className="u-1qyyh4r">
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
          <Space direction="vertical" size="middle" className="u-1f3r3s">
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
