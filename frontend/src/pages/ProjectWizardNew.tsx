import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Form,
  Input,
  InputNumber,
  Radio,
  Row,
  Select,
  Space,
  Steps,
  Typography,
  message,
  theme,
} from 'antd';
import {
  ArrowLeftOutlined,
  BulbOutlined,
  CheckCircleOutlined,
  EditOutlined,
  RocketOutlined,
  SaveOutlined,
} from '@ant-design/icons';
import { AIProjectGenerator } from '../components/generation/AIProjectGenerator';
import type { GenerationConfig } from '../components/generation/types';
import type { InspirationGenerationContext, WizardBasicInfo } from '../types';
import {
  clearProjectWizardDraft,
  getProjectWizardDraftScope,
  loadInspirationDraft,
  loadProjectWizardDraft,
  moveProjectWizardDraft,
  saveProjectWizardDraft,
} from '../utils/inspirationDrafts';
import type { InspirationDraftRecord, ProjectWizardFormDraft } from '../utils/inspirationDrafts';
import { useIsMobile } from '../hooks/useMediaQuery';
import { sx } from '../styles/sx';

const { TextArea } = Input;
const { Title, Paragraph, Text } = Typography;

type WizardStep = 'entry' | 'form' | 'generating';

const DEFAULT_FORM_VALUES: WizardBasicInfo = {
  title: '',
  description: '',
  theme: '',
  genre: ['玄幻'],
  chapter_count: 3,
  narrative_perspective: '第三人称',
  character_count: 5,
  target_words: 100000,
  outline_mode: 'one-to-one',
};

function inspirationToFormValues(draft: InspirationDraftRecord): WizardBasicInfo {
  return {
    ...DEFAULT_FORM_VALUES,
    title: draft.title,
    description: draft.description,
    theme: draft.theme,
    genre: draft.genre,
    narrative_perspective: draft.narrative_perspective || DEFAULT_FORM_VALUES.narrative_perspective,
    outline_mode: draft.outline_mode || DEFAULT_FORM_VALUES.outline_mode,
  };
}

function buildInspirationContext(draft: InspirationDraftRecord): InspirationGenerationContext {
  return {
    source: 'inspiration_story_bible',
    initial_idea: draft.initial_idea,
    confirmed_fields: {
      initial_idea: draft.initial_idea,
      title: draft.title,
      description: draft.description,
      theme: draft.theme,
      genre: draft.genre,
      world_setting: draft.world_setting,
      core_conflict: draft.core_conflict,
      protagonist: draft.protagonist,
      golden_finger: draft.golden_finger,
    },
    story_bible_draft: draft.story_bible_draft,
  };
}

function restorePersistedInspirationContext(
  config: GenerationConfig,
  projectId: string,
  storage: Storage = localStorage,
): GenerationConfig {
  try {
    if (storage.getItem('wizard_project_id') !== projectId) return config;

    const raw = storage.getItem('wizard_generation_data');
    if (!raw) return config;

    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== 'object' || parsed === null) return config;

    const persisted = parsed as Partial<GenerationConfig>;
    const inspirationContext = persisted.inspiration_context;
    return inspirationContext && typeof inspirationContext === 'object'
      ? { ...config, inspiration_context: inspirationContext }
      : config;
  } catch (error) {
    console.warn('恢复生成上下文失败:', error);
    return config;
  }
}

export default function ProjectWizardNew() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [form] = Form.useForm<WizardBasicInfo>();
  const isMobile = useIsMobile();
  const { token } = theme.useToken();
  const resumeProjectIdParam = searchParams.get('project_id');
  const wizardDraftScope = getProjectWizardDraftScope(resumeProjectIdParam || undefined);
  const [currentStep, setCurrentStep] = useState<WizardStep>('entry');
  const [generationConfig, setGenerationConfig] = useState<GenerationConfig | null>(null);
  const [resumeProjectId, setResumeProjectId] = useState<string | null>(null);
  const [inspirationDraft, setInspirationDraft] = useState<InspirationDraftRecord>();
  const [inspirationHandoffDismissed, setInspirationHandoffDismissed] = useState(false);
  const [savedFormDraft, setSavedFormDraft] = useState<ProjectWizardFormDraft | undefined>(() =>
    loadProjectWizardDraft(localStorage, wizardDraftScope),
  );


  const handleResumeGeneration = async (projectId: string) => {
    try {
      const response = await fetch(`/api/projects/${projectId}`, { credentials: 'include' });
      if (!response.ok) throw new Error('获取项目信息失败');
      const project = await response.json();
      const config = restorePersistedInspirationContext({
        title: project.title,
        description: project.description || '',
        theme: project.theme || '',
        genre: project.genre || '',
        narrative_perspective: project.narrative_perspective || '第三人称',
        target_words: project.target_words || 100000,
        chapter_count: project.chapter_count || 3,
        character_count: project.character_count || 5,
        outline_mode: project.outline_mode || 'one-to-many',
      }, projectId);
      setGenerationConfig(config);
      setCurrentStep('generating');
    } catch (error) {
      console.error('恢复生成失败:', error);
      message.error('恢复生成失败，请重试');
      navigate('/');
    }
  };

  useEffect(() => {
    const projectId = resumeProjectIdParam;
    if (projectId) {
      setResumeProjectId(projectId);
      void handleResumeGeneration(projectId);
      return;
    }

    const inspirationId = searchParams.get('from_inspiration');
    if (!inspirationId) return;

    const draft = loadInspirationDraft(inspirationId);
    if (!draft) {
      message.error('未找到选中的灵感草稿，请重新选择');
      setCurrentStep('entry');
      return;
    }

    const values = inspirationToFormValues(draft);
    setInspirationDraft(draft);
    setInspirationHandoffDismissed(false);
    form.setFieldsValue(values);
    const nextDraft: ProjectWizardFormDraft = {
      values,
      inspiration: draft,
      inspiration_handoff_dismissed: false,
      scope: wizardDraftScope,
      updated_at: new Date().toISOString(),
    };
    saveProjectWizardDraft(nextDraft);
    setSavedFormDraft(nextDraft);
    setCurrentStep('form');
    message.success('已将灵感内容回填到项目表单');
    // URL参数是一次性交接标识，后续由本地草稿负责恢复。
    navigate('/wizard', { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const saveFormProgress = (
    values: Partial<WizardBasicInfo>,
    draftInspiration: InspirationDraftRecord | null = inspirationDraft ?? null,
    handoffDismissed = inspirationHandoffDismissed,
  ) => {
    const draft: ProjectWizardFormDraft = {
      values: { ...DEFAULT_FORM_VALUES, ...values },
      inspiration: draftInspiration ?? undefined,
      inspiration_handoff_dismissed: handoffDismissed || undefined,
      scope: wizardDraftScope,
      updated_at: new Date().toISOString(),
    };
    saveProjectWizardDraft(draft);
    setSavedFormDraft(draft);
  };

  const openBlankForm = () => {
    clearProjectWizardDraft(localStorage, wizardDraftScope);
    setSavedFormDraft(undefined);
    setInspirationDraft(undefined);
    setInspirationHandoffDismissed(false);
    form.setFieldsValue(DEFAULT_FORM_VALUES);
    setCurrentStep('form');
  };

  const continueSavedDraft = () => {
    if (!savedFormDraft) return;
    const handoffDismissed = savedFormDraft.inspiration_handoff_dismissed === true;
    setInspirationHandoffDismissed(handoffDismissed);
    setInspirationDraft(handoffDismissed ? undefined : savedFormDraft.inspiration);
    form.setFieldsValue({ ...DEFAULT_FORM_VALUES, ...savedFormDraft.values });
    setCurrentStep('form');
  };

  const handleAutoGenerate = () => {
    const values = form.getFieldsValue(true) as WizardBasicInfo;
    saveFormProgress(values);
    const config: GenerationConfig = {
      title: values.title,
      description: values.description,
      theme: values.theme,
      genre: values.genre,
      narrative_perspective: values.narrative_perspective || '第三人称',
      target_words: values.target_words || 100000,
      chapter_count: 3,
      character_count: values.character_count || 5,
      outline_mode: values.outline_mode || 'one-to-many',
      ...(inspirationDraft ? { inspiration_context: buildInspirationContext(inspirationDraft) } : {}),
    };
    setGenerationConfig(config);
    setCurrentStep('generating');
  };

  const handleProjectCreated = (projectId: string) => {
    const movedDraft = moveProjectWizardDraft(
      localStorage,
      wizardDraftScope,
      { project_id: projectId },
    );
    if (movedDraft) {
      setSavedFormDraft(movedDraft);
    }
  };

  const handleComplete = (projectId: string) => {
    clearProjectWizardDraft(localStorage, { project_id: projectId });
    if (!resumeProjectId) {
      clearProjectWizardDraft(localStorage, wizardDraftScope);
    }
    setSavedFormDraft(undefined);
  };

  const handleBack = () => {
    setCurrentStep('form');
    setGenerationConfig(null);
  };

  const saveForLater = () => {
    saveFormProgress(form.getFieldsValue(true) as WizardBasicInfo);
    message.success('创建进度已保存，下次打开向导可继续');
    navigate('/');
  };

  const renderEntry = () => (
    <Card>
      <Title level={isMobile ? 4 : 3}>选择开始方式</Title>
      <Paragraph type="secondary">已有想法可直接填写；还在构思时，可以先用灵感模式生成并比较故事方向。</Paragraph>
      <Row gutter={[16, 16]}>
        <Col xs={24} md={12}>
          <Card hoverable onClick={() => navigate('/inspiration')} className="u-j7izwl">
            <Space direction="vertical" size="small">
              <BulbOutlined className={sx({ color: token.colorWarning, fontSize: 30 })} />
              <Title level={4} className="u-avalr8">从灵感开始</Title>
              <Text type="secondary">按平台、题材和关键词探索方向，选定后自动回填。</Text>
              <Button type="primary" icon={<BulbOutlined />}>进入灵感模式</Button>
            </Space>
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card hoverable onClick={openBlankForm} className="u-j7izwl">
            <Space direction="vertical" size="small">
              <EditOutlined className={sx({ color: token.colorPrimary, fontSize: 30 })} />
              <Title level={4} className="u-avalr8">直接填写</Title>
              <Text type="secondary">已有清晰设定，直接填写书名、简介、主题和类型。</Text>
              <Button icon={<EditOutlined />}>填写基本信息</Button>
            </Space>
          </Card>
        </Col>
      </Row>
      {savedFormDraft && (
        <Alert
          className="u-oxf0ga"
          type="info"
          showIcon
          message="发现未完成的创建草稿"
          description={`保存于 ${new Date(savedFormDraft.updated_at).toLocaleString()}`}
          action={<Button onClick={continueSavedDraft}>继续上次填写</Button>}
        />
      )}
    </Card>
  );

  const renderForm = () => (
    <Card>
      <Title level={isMobile ? 4 : 3}>填写基本信息</Title>
      <Paragraph type="secondary">确认核心创意后，AI 将生成世界观、角色和大纲节点。</Paragraph>
      {inspirationDraft && (
        <Alert
          type="success"
          showIcon
          closable
          className="u-1ccse9a"
          message={`已载入灵感：${inspirationDraft.title}`}
          description="灵感中的核心冲突、世界设定和故事圣经会随项目生成请求一并传递。"
          onClose={() => {
            setInspirationDraft(undefined);
            setInspirationHandoffDismissed(true);
            saveFormProgress(form.getFieldsValue(true) as WizardBasicInfo, null, true);
          }}
        />
      )}
      <Form<WizardBasicInfo>
        form={form}
        layout="vertical"
        onFinish={handleAutoGenerate}
        onValuesChange={() => saveFormProgress(form.getFieldsValue(true))}
        initialValues={DEFAULT_FORM_VALUES}
      >
        <Form.Item label="书名" name="title" rules={[{ required: true, message: '请输入书名' }]}>
          <Input placeholder="输入你的小说标题" size="large" />
        </Form.Item>
        <Form.Item label="小说简介" name="description" rules={[{ required: true, message: '请输入小说简介' }]}>
          <TextArea rows={3} placeholder="用一段话介绍故事主角、目标和冲突" showCount />
        </Form.Item>
        <Form.Item label="主题" name="theme" rules={[{ required: true, message: '请输入主题' }]}>
          <TextArea rows={3} placeholder="例如：在权力与亲情之间寻找自我" showCount />
        </Form.Item>
        <Form.Item label="类型" name="genre" rules={[{ required: true, message: '请选择小说类型' }]}>
          <Select mode="tags" placeholder="选择或输入类型标签" size="large" tokenSeparators={[',', '，']} maxTagCount={5}
            options={['玄幻', '都市', '历史', '科幻', '武侠', '仙侠', '奇幻', '悬疑', '言情', '修仙'].map(value => ({ value, label: value }))}
          />
        </Form.Item>
        <Collapse
          ghost
          items={[{
            key: 'advanced',
            label: '高级设置（可选）',
            forceRender: true,
            children: (
              <>
                <Row gutter={16}>
                  <Col xs={24} sm={12}>
                    <Form.Item label="叙事视角" name="narrative_perspective">
                      <Select size="large" options={['第一人称', '第三人称', '全知视角'].map(value => ({ value, label: value }))} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12}>
                    <Form.Item label="角色数量" name="character_count">
                      <InputNumber min={3} max={20} className="u-1f3r3s" size="large" addonAfter="个" />
                    </Form.Item>
                  </Col>
                </Row>
                <Form.Item label="目标字数" name="target_words">
                  <InputNumber min={10000} className="u-1f3r3s" size="large" addonAfter="字" />
                </Form.Item>
                <Form.Item label="大纲章节模式" name="outline_mode">
                  <Radio.Group>
                    <Space direction={isMobile ? 'vertical' : 'horizontal'}>
                      <Radio value="one-to-one"><CheckCircleOutlined /> 传统模式（1 个大纲对应 1 章）</Radio>
                      <Radio value="one-to-many"><CheckCircleOutlined /> 细化模式（1 个大纲展开多章）</Radio>
                    </Space>
                  </Radio.Group>
                </Form.Item>
              </>
            ),
          }]}
        />
        <Space direction="vertical" className="u-11kth" size={12}>
          <Button type="primary" htmlType="submit" size="large" block icon={<RocketOutlined />}>开始 AI 生成</Button>
          <Row gutter={12}>
            <Col span={12}><Button block onClick={() => setCurrentStep('entry')}>上一步</Button></Col>
            <Col span={12}><Button block icon={<SaveOutlined />} onClick={saveForLater}>稍后继续</Button></Col>
          </Row>
        </Space>
      </Form>
    </Card>
  );

  const progressIndex = currentStep === 'entry' ? 0 : currentStep === 'form' ? 1 : 2;

  return (
    <div className={sx({ minHeight: '100dvh', background: token.colorBgBase })}>
      <div className={sx({ position: 'sticky', top: 0, zIndex: 100, background: token.colorPrimary, boxShadow: `0 6px 20px color-mix(in srgb, ${token.colorPrimary} 30%, transparent)` })}>
        <div className={sx({ maxWidth: 1100, margin: '0 auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: isMobile ? '10px 12px' : '14px 24px' })}>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/')} size={isMobile ? 'middle' : 'large'} disabled={currentStep === 'generating'}>
            {isMobile ? '返回' : '返回首页'}
          </Button>
          <Title level={isMobile ? 5 : 2} className={sx({ margin: 0, color: token.colorWhite })}><RocketOutlined /> 项目创建向导</Title>
          <div className={sx({ width: isMobile ? 64 : 120 })} />
        </div>
      </div>
      <div className={sx({ maxWidth: 900, margin: '0 auto', padding: isMobile ? '14px 10px 20px' : '20px 24px 32px' })}>
        <Steps
          current={progressIndex}
          responsive
          size={isMobile ? 'small' : 'default'}
          className={sx({ marginBottom: isMobile ? 16 : 24 })}
          items={[
            { title: '灵感探索', description: isMobile ? undefined : '可选' },
            { title: '基本信息' },
            { title: 'AI 生成' },
          ]}
        />
        {currentStep === 'entry' && renderEntry()}
        {currentStep === 'form' && renderForm()}
        {currentStep === 'generating' && generationConfig && (
          <AIProjectGenerator
            config={generationConfig}
            storagePrefix="wizard"
            onComplete={handleComplete}
            onProjectCreated={handleProjectCreated}
            onBack={handleBack}
            isMobile={isMobile}
            resumeProjectId={resumeProjectId || undefined}
          />
        )}
      </div>
    </div>
  );
}
