import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message as antdMessage,
  theme,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  DeleteOutlined,
  EditOutlined,
  EyeOutlined,
  PlusOutlined,
  ReloadOutlined,
  SoundOutlined,
} from '@ant-design/icons';
import { creativeSessionApi, voicePersonaApi } from '../services/api';
import type {
  CreativeSession,
  VoicePersona,
  VoicePersonaCreate,
  VoicePersonaPromptPreviewResponse,
} from '../types';
import { sx } from '../styles/sx';

const { Paragraph, Text, Title } = Typography;
const { TextArea } = Input;

interface VoicePersonaFormValues {
  name: string;
  tone?: string;
  style?: string;
  point_of_view?: string;
  constraints?: string;
  session_id?: string | null;
  sort_order?: number;
  enabled?: boolean;
}

function buildPayload(values: VoicePersonaFormValues): VoicePersonaCreate {
  return {
    name: values.name.trim(),
    tone: values.tone?.trim() || '',
    style: values.style?.trim() || '',
    point_of_view: values.point_of_view?.trim() || '',
    constraints: values.constraints?.trim() || '',
    session_id: values.session_id || null,
    sort_order: values.sort_order ?? 0,
    enabled: values.enabled ?? true,
  };
}

export default function VoicePersonas() {
  const { projectId } = useParams<{ projectId: string }>();
  const { token } = theme.useToken();
  const [form] = Form.useForm<VoicePersonaFormValues>();

  const [items, setItems] = useState<VoicePersona[]>([]);
  const [sessions, setSessions] = useState<CreativeSession[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<VoicePersona | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [previewPersonaId, setPreviewPersonaId] = useState<string | undefined>();
  const [previewSessionId, setPreviewSessionId] = useState<string | undefined>();
  const [previewBasePrompt, setPreviewBasePrompt] = useState('原始章节提示词');
  const [previewInjectionEnabled, setPreviewInjectionEnabled] = useState(true);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [preview, setPreview] = useState<VoicePersonaPromptPreviewResponse | null>(null);

  const sessionOptions = useMemo(
    () => sessions.map(session => ({ label: session.title, value: session.id })),
    [sessions]
  );
  const enabledCount = useMemo(() => items.filter(item => item.enabled).length, [items]);

  const loadPersonas = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const response = await voicePersonaApi.list(projectId, selectedSessionId ? { session_id: selectedSessionId } : undefined);
      setItems(response.items);
      setPreviewPersonaId(current => current && response.items.some(item => item.id === current) ? current : response.items[0]?.id);
    } catch (err) {
      console.error('加载旁白声音画像失败:', err);
      setError('旁白声音画像暂时不可用，可能是功能未启用或当前账号无权访问。');
      setItems([]);
      setPreviewPersonaId(undefined);
    } finally {
      setLoading(false);
    }
  }, [projectId, selectedSessionId]);

  const loadSessions = useCallback(async () => {
    if (!projectId) return;
    try {
      const response = await creativeSessionApi.listSessions(projectId);
      setSessions(response.items);
    } catch (err) {
      console.warn('加载创作会话失败，旁白声音画像仍可按项目使用:', err);
      setSessions([]);
    }
  }, [projectId]);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  useEffect(() => {
    loadPersonas();
  }, [loadPersonas]);

  const openCreateModal = () => {
    setEditing(null);
    form.setFieldsValue({
      name: '',
      tone: '',
      style: '',
      point_of_view: '',
      constraints: '',
      session_id: selectedSessionId || null,
      sort_order: items.length + 1,
      enabled: true,
    });
    setModalOpen(true);
  };

  const openEditModal = (item: VoicePersona) => {
    setEditing(item);
    form.setFieldsValue({
      name: item.name,
      tone: item.tone,
      style: item.style,
      point_of_view: item.point_of_view,
      constraints: item.constraints,
      session_id: item.session_id || null,
      sort_order: item.sort_order,
      enabled: item.enabled,
    });
    setModalOpen(true);
  };

  const handleSubmit = async (values: VoicePersonaFormValues) => {
    if (!projectId) return;
    const payload = buildPayload(values);
    if (!payload.tone && !payload.style && !payload.point_of_view && !payload.constraints) {
      antdMessage.warning('请至少填写语气、文风、视角或约束中的一项');
      return;
    }

    setSaving(true);
    setError(null);
    try {
      if (editing) {
        await voicePersonaApi.update(editing.id, payload);
        antdMessage.success('旁白声音画像已更新');
      } else {
        await voicePersonaApi.create(projectId, payload);
        antdMessage.success('旁白声音画像已创建');
      }
      setModalOpen(false);
      setEditing(null);
      await loadPersonas();
    } catch (err) {
      console.error('保存旁白声音画像失败:', err);
      setError('保存失败：请确认项目/会话权限正确，并至少填写一个作者声音字段。');
    } finally {
      setSaving(false);
    }
  };

  const handleToggleEnabled = async (item: VoicePersona, enabled: boolean) => {
    try {
      await voicePersonaApi.update(item.id, { enabled });
      setItems(prev => prev.map(persona => persona.id === item.id ? { ...persona, enabled } : persona));
    } catch (err) {
      console.error('切换旁白声音画像状态失败:', err);
      antdMessage.error('状态更新失败');
    }
  };

  const handleDelete = async (item: VoicePersona) => {
    try {
      await voicePersonaApi.deletePersona(item.id);
      setItems(prev => prev.filter(persona => persona.id !== item.id));
      setPreviewPersonaId(current => current === item.id ? undefined : current);
      antdMessage.success('旁白声音画像已删除');
    } catch (err) {
      console.error('删除旁白声音画像失败:', err);
      antdMessage.error('删除失败');
    }
  };

  const handlePreview = async (personaId?: string) => {
    if (!projectId) return;
    const targetPersonaId = personaId || previewPersonaId;
    if (!targetPersonaId) {
      antdMessage.warning('请先选择一个旁白声音画像');
      return;
    }
    const persona = items.find(item => item.id === targetPersonaId);
    const sessionId = previewSessionId || selectedSessionId || persona?.session_id || undefined;

    setPreviewLoading(true);
    try {
      const response = await voicePersonaApi.previewPromptTrace(projectId, {
        persona_id: targetPersonaId,
        session_id: sessionId || null,
        base_prompt: previewBasePrompt,
        injection_enabled: previewInjectionEnabled,
      });
      setPreview(response);
      setPreviewPersonaId(targetPersonaId);
      antdMessage.success('旁白声音 Trace 已更新');
    } catch (err) {
      console.error('生成旁白声音 Trace 失败:', err);
      antdMessage.error('生成 Trace 失败，请确认画像和会话属于当前项目');
    } finally {
      setPreviewLoading(false);
    }
  };

  const columns: ColumnsType<VoicePersona> = [
    {
      title: '顺序',
      dataIndex: 'sort_order',
      width: 80,
      sorter: (left, right) => left.sort_order - right.sort_order,
    },
    {
      title: '名称',
      dataIndex: 'name',
      width: 180,
      render: (name: string, item) => (
        <Space direction="vertical" size={2}>
          <Text strong>{name}</Text>
          <Space size={4} wrap>
            <Tag color={item.scope === 'session' ? 'purple' : 'blue'}>{item.scope === 'session' ? '会话级' : '项目级'}</Tag>
            {item.session_id && <Tag>{item.session_id}</Tag>}
          </Space>
        </Space>
      ),
    },
    {
      title: '语气 / 视角',
      key: 'voice',
      render: (_, item) => (
        <Space direction="vertical" size={2}>
          <Text>{item.tone || '未设置语气'}</Text>
          <Text type="secondary">{item.point_of_view || '未设置视角'}</Text>
        </Space>
      ),
    },
    {
      title: '文风与约束',
      key: 'style_constraints',
      render: (_, item) => (
        <Paragraph ellipsis={{ rows: 2, expandable: true, symbol: '展开' }} className="u-19o9sm6">
          {[item.style, item.constraints].filter(Boolean).join('\n') || '未设置'}
        </Paragraph>
      ),
    },
    {
      title: '启用',
      dataIndex: 'enabled',
      width: 100,
      render: (enabled: boolean, item) => (
        <Switch checked={enabled} onChange={checked => handleToggleEnabled(item, checked)} />
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 210,
      render: (_, item) => (
        <Space wrap>
          <Button size="small" icon={<EyeOutlined />} onClick={() => handlePreview(item.id)}>Trace</Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEditModal(item)}>编辑</Button>
          <Popconfirm title="删除旁白声音画像？" description="已生成的历史 Trace 不会被修改。" onConfirm={() => handleDelete(item)}>
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const renderPreview = () => {
    const trace = preview?.trace;
    return (
      <Card title="Prompt Trace 预览" className={sx({ borderRadius: token.borderRadiusLG, border: `1px solid ${token.colorBorderSecondary}` })}>
        <Space direction="vertical" className="u-1f3r3s" size={token.marginSM}>
          <Row gutter={[token.marginSM, token.marginSM]}>
            <Col xs={24} md={8}>
              <Text strong>选择声音画像</Text>
              <Select
                className={sx({ width: '100%', marginTop: token.marginXS })}
                placeholder="选择画像"
                value={previewPersonaId}
                onChange={setPreviewPersonaId}
                options={items.map(item => ({ label: item.name, value: item.id }))}
              />
            </Col>
            <Col xs={24} md={8}>
              <Text strong>应用会话（可选）</Text>
              <Select
                allowClear
                className={sx({ width: '100%', marginTop: token.marginXS })}
                placeholder="项目级或选择会话"
                value={previewSessionId || selectedSessionId}
                onChange={value => setPreviewSessionId(value)}
                options={sessionOptions}
              />
            </Col>
            <Col xs={24} md={8}>
              <Text strong>应用到预览 Prompt</Text>
              <div className={sx({ marginTop: token.marginXS })}>
                <Switch
                  checked={previewInjectionEnabled}
                  onChange={setPreviewInjectionEnabled}
                  checkedChildren="注入预览"
                  unCheckedChildren="仅 Trace"
                />
              </div>
            </Col>
          </Row>
          <TextArea
            rows={4}
            value={previewBasePrompt}
            onChange={event => setPreviewBasePrompt(event.target.value)}
            placeholder="输入基础提示词，用于查看声音画像显式应用后的 prompt 片段..."
          />
          <Space wrap>
            <Tag color="blue">source_type=voice_persona</Tag>
            <Tag color="green">authoring-profile-only</Tag>
            <Button type="primary" loading={previewLoading} onClick={() => handlePreview()}>
              生成 Trace
            </Button>
          </Space>

          {trace ? (
            <Space direction="vertical" className="u-1f3r3s" size={token.marginSM}>
              <Card size="small" title="Trace 摘要">
                <Space direction="vertical" className="u-1f3r3s">
                  <div><Text type="secondary">Trace ID：</Text><Tag>{trace.trace_id}</Tag></div>
                  <div><Text type="secondary">画像 ID：</Text><Tag>{trace.selected_voice_persona_id}</Tag></div>
                  <div><Text type="secondary">顺序：</Text><Tag>order {trace.items[0]?.order}</Tag><Tag>source_order {trace.source_order}</Tag></div>
                  <div><Text type="secondary">范围：</Text><Tag color={trace.applied_scope === 'session' ? 'purple' : 'blue'}>{trace.applied_scope}</Tag></div>
                </Space>
              </Card>
              <Card size="small" title="最终声音画像文本">
                <pre className="u-1kda7dj">
                  {trace.final_preview_text}
                </pre>
              </Card>
              <Card size="small" title="预览 Prompt">
                <pre className="u-1kda7dj">
                  {preview.preview_prompt || '未启用注入预览，基础提示词保持不变。'}
                </pre>
              </Card>
            </Space>
          ) : (
            <Empty description="选择画像后生成确定性 Trace" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          )}
        </Space>
      </Card>
    );
  };

  return (
    <div className={sx({ height: '100%', display: 'flex', flexDirection: 'column', gap: token.paddingMD })}>
      <Card>
        <Space align="start" className="u-1qos3j5" wrap>
          <Space direction="vertical" size={4}>
            <Space>
              <SoundOutlined className={sx({ color: token.colorPrimary, fontSize: 24 })} />
              <Title level={3} className="u-avalr8">旁白声音画像</Title>
            </Space>
            <Paragraph type="secondary" className="u-1sezbee">
              记录项目或单个创作会话的叙述语气、文风、视角和写作约束。它只作为作者侧声音 Profile 进入 Prompt Trace，不承载对话身份或互动状态。
            </Paragraph>
          </Space>
          <Space wrap>
            <Select
              allowClear
              placeholder="按会话查看"
              value={selectedSessionId}
              className="u-1376ovb"
              onChange={value => {
                setSelectedSessionId(value);
                setPreviewSessionId(value);
                setPreview(null);
              }}
              options={sessionOptions}
            />
            <Tag color="blue">启用 {enabledCount}/{items.length}</Tag>
            <Button icon={<ReloadOutlined />} onClick={loadPersonas} loading={loading}>刷新</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>新建声音画像</Button>
          </Space>
        </Space>
      </Card>

      {error && <Alert type="warning" showIcon message={error} />}

      <Card className="u-1tqrzca" bodyStyle={{ height: '100%', overflow: 'auto' }}>
        <Table<VoicePersona>
          rowKey="id"
          columns={columns}
          dataSource={items}
          loading={loading}
          pagination={false}
          locale={{ emptyText: <Empty description="暂无旁白声音画像" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
        />
      </Card>

      {renderPreview()}

      <Modal
        title={editing ? '编辑旁白声音画像' : '新建旁白声音画像'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={saving}
        okText="保存"
        cancelText="取消"
        destroyOnClose
        width={760}
      >
        <Alert
          type="info"
          showIcon
          className={sx({ marginBottom: token.marginMD })}
          message="作者侧声音 Profile"
          description="只保存旁白创作指令：语气、文风、POV 和约束。服务端会按项目/会话校验，避免扩散成全局可变状态。"
        />
        <Form<VoicePersonaFormValues>
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          preserve={false}
        >
          <Row gutter={token.marginMD}>
            <Col xs={24} md={12}>
              <Form.Item name="name" label="画像名称" rules={[{ required: true, message: '请输入画像名称' }]}>
                <Input maxLength={120} placeholder="例如：冷峻雨夜旁白" />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item name="session_id" label="作用域（可选会话）">
                <Select allowClear placeholder="不选择则为项目级画像" options={sessionOptions} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={token.marginMD}>
            <Col xs={24} md={12}>
              <Form.Item name="sort_order" label="显示顺序">
                <InputNumber className="u-1f3r3s" min={0} precision={0} />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item name="enabled" label="启用状态" valuePropName="checked">
                <Switch checkedChildren="启用" unCheckedChildren="停用" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="tone" label="叙述语气">
            <TextArea rows={2} maxLength={2000} showCount placeholder="例如：克制、冷峻、带轻微悬疑压迫感" />
          </Form.Item>
          <Form.Item name="style" label="文风特征">
            <TextArea rows={2} maxLength={2000} showCount placeholder="例如：短句推进，环境细节服务人物行动" />
          </Form.Item>
          <Form.Item name="point_of_view" label="POV / 叙事视角">
            <Input maxLength={1000} placeholder="例如：第三人称限知" />
          </Form.Item>
          <Form.Item name="constraints" label="写作约束">
            <TextArea rows={4} maxLength={4000} showCount placeholder="例如：避免作者评论；不要替角色解释动机，只呈现可观察行为。" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
