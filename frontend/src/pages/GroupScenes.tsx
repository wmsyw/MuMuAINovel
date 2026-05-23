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
  Popconfirm,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message as antdMessage,
  theme,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { CommentOutlined, DeleteOutlined, ReloadOutlined } from '@ant-design/icons';
import { useStore } from '../store';
import { groupSceneApi, voicePersonaApi } from '../services/api';
import type { Character, GroupScene, GroupSceneDraftRequest, VoicePersona } from '../types';

const { Paragraph, Title } = Typography;
const { TextArea } = Input;

interface GroupSceneFormValues {
  title: string;
  scenario: string;
  participant_character_ids: string[];
  selected_voice_persona_id?: string | null;
  selected_lore_ids_text?: string;
  prompt_context?: string;
  draft_text?: string;
}

function parseLoreIds(value?: string): string[] {
  return Array.from(new Set((value || '').split(/[,，\s]+/).map(item => item.trim()).filter(Boolean))).slice(0, 5);
}

function buildPayload(values: GroupSceneFormValues): GroupSceneDraftRequest {
  return {
    title: values.title.trim(),
    scenario: values.scenario.trim(),
    participant_character_ids: values.participant_character_ids,
    selected_voice_persona_id: values.selected_voice_persona_id || null,
    selected_lore_ids: parseLoreIds(values.selected_lore_ids_text),
    prompt_context: values.prompt_context?.trim() || '',
    draft_text: values.draft_text?.trim() || null,
  };
}

function characterNameMap(characters: Character[]): Map<string, string> {
  return new Map(characters.map(character => [character.id, character.name]));
}

export default function GroupScenes() {
  const { projectId } = useParams<{ projectId: string }>();
  const { token } = theme.useToken();
  const { characters } = useStore();
  const [form] = Form.useForm<GroupSceneFormValues>();

  const [items, setItems] = useState<GroupScene[]>([]);
  const [voicePersonas, setVoicePersonas] = useState<VoicePersona[]>([]);
  const [selectedScene, setSelectedScene] = useState<GroupScene | null>(null);
  const [loading, setLoading] = useState(false);
  const [drafting, setDrafting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const namesById = useMemo(() => characterNameMap(characters), [characters]);
  const characterOptions = useMemo(
    () => characters
      .filter(character => !character.is_organization)
      .map(character => ({ label: `${character.name}（${character.role_type || '角色'}）`, value: character.id })),
    [characters]
  );
  const voiceOptions = useMemo(
    () => voicePersonas.filter(persona => persona.enabled).map(persona => ({ label: persona.name, value: persona.id })),
    [voicePersonas]
  );

  const loadScenes = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const response = await groupSceneApi.list(projectId);
      setItems(response.items);
      setSelectedScene(current => current && response.items.some(item => item.id === current.id) ? current : response.items[0] || null);
    } catch (err) {
      console.error('加载群像场景失败:', err);
      setError('群像场景暂时不可用，可能是功能未启用或当前账号无权访问。');
      setItems([]);
      setSelectedScene(null);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  const loadVoicePersonas = useCallback(async () => {
    if (!projectId) return;
    try {
      const response = await voicePersonaApi.list(projectId, { enabled: true });
      setVoicePersonas(response.items);
    } catch (err) {
      console.warn('加载旁白声音画像失败，群像场景仍可不选择声音画像:', err);
      setVoicePersonas([]);
    }
  }, [projectId]);

  useEffect(() => {
    loadScenes();
    loadVoicePersonas();
  }, [loadScenes, loadVoicePersonas]);

  const handleDraft = async (values: GroupSceneFormValues) => {
    if (!projectId) return;
    const payload = buildPayload(values);
    if (payload.participant_character_ids.length < 2) {
      antdMessage.warning('请至少选择两个项目角色');
      return;
    }
    setDrafting(true);
    setError(null);
    try {
      const scene = await groupSceneApi.draft(projectId, payload);
      setItems(prev => [scene, ...prev.filter(item => item.id !== scene.id)]);
      setSelectedScene(scene);
      form.setFieldsValue({ draft_text: scene.draft_text });
      antdMessage.success('群像场景草稿已保存');
    } catch (err) {
      console.error('创建群像场景失败:', err);
      setError('创建失败：请确认参与者均为当前项目角色，且所选声音/Lore上下文有效。');
    } finally {
      setDrafting(false);
    }
  };

  const handleDelete = async (scene: GroupScene) => {
    try {
      await groupSceneApi.deleteScene(scene.id);
      setItems(prev => prev.filter(item => item.id !== scene.id));
      setSelectedScene(current => current?.id === scene.id ? null : current);
      antdMessage.success('群像场景已删除');
    } catch (err) {
      console.error('删除群像场景失败:', err);
      antdMessage.error('删除失败');
    }
  };

  const columns: ColumnsType<GroupScene> = [
    {
      title: '场景',
      dataIndex: 'title',
      width: 220,
      render: (title: string, scene) => (
        <Space direction="vertical" size={2}>
          <Button type="link" style={{ padding: 0 }} onClick={() => setSelectedScene(scene)}>{title}</Button>
          <Tag color="blue">writing_artifact_only</Tag>
        </Space>
      ),
    },
    {
      title: '参与角色',
      dataIndex: 'participant_character_ids',
      render: (ids: string[]) => (
        <Space wrap size={4}>
          {ids.map(id => <Tag key={id}>{namesById.get(id) || id}</Tag>)}
        </Space>
      ),
    },
    {
      title: '场景目标',
      dataIndex: 'scenario',
      render: (scenario: string) => (
        <Paragraph ellipsis={{ rows: 2, expandable: true, symbol: '展开' }} style={{ marginBottom: 0 }}>
          {scenario}
        </Paragraph>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 100,
      render: (_, scene) => (
        <Popconfirm title="删除群像场景？" description="仅删除这个写作草稿，不影响章节正文。" onConfirm={() => handleDelete(scene)}>
          <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
        </Popconfirm>
      ),
    },
  ];

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', gap: token.paddingMD }}>
      <Card>
        <Space align="start" style={{ width: '100%', justifyContent: 'space-between' }} wrap>
          <Space direction="vertical" size={4}>
            <Space>
              <CommentOutlined style={{ color: token.colorPrimary, fontSize: 24 }} />
              <Title level={3} style={{ margin: 0 }}>群像场景</Title>
            </Space>
            <Paragraph type="secondary" style={{ marginBottom: 0 }}>
              用当前项目角色、可选旁白声音、Lore ID 和提示上下文试写多角色对话。结果只保存为项目写作草稿，不创建聊天室、不自动轮询角色发言，也不改写章节正文。
            </Paragraph>
          </Space>
          <Space wrap>
            <Tag color="green">写作草稿</Tag>
            <Tag color="orange">无自动章节改写</Tag>
            <Button icon={<ReloadOutlined />} onClick={loadScenes} loading={loading}>刷新</Button>
          </Space>
        </Space>
      </Card>

      {error && <Alert type="warning" showIcon message={error} />}

      <Row gutter={[token.marginMD, token.marginMD]} style={{ flex: 1, minHeight: 0 }}>
        <Col xs={24} xl={10} style={{ minHeight: 0 }}>
          <Card title="创建场景草稿" style={{ height: '100%', overflow: 'hidden' }} bodyStyle={{ height: 'calc(100% - 57px)', overflow: 'auto' }}>
            <Form<GroupSceneFormValues>
              form={form}
              layout="vertical"
              onFinish={handleDraft}
              initialValues={{ participant_character_ids: [], selected_lore_ids_text: '', prompt_context: '', draft_text: '' }}
            >
              <Form.Item name="title" label="场景标题" rules={[{ required: true, message: '请输入场景标题' }]}>
                <Input maxLength={200} placeholder="例如：密诏摊牌" />
              </Form.Item>
              <Form.Item name="participant_character_ids" label="参与角色" rules={[{ required: true, message: '请至少选择两个角色' }]}>
                <Select mode="multiple" maxCount={8} options={characterOptions} placeholder="选择2-8个项目角色" />
              </Form.Item>
              <Form.Item name="scenario" label="场景目标" rules={[{ required: true, message: '请输入场景目标' }]}>
                <TextArea rows={4} maxLength={4000} showCount placeholder="描述冲突、场景、对话目的、需要保留的潜台词..." />
              </Form.Item>
              <Form.Item name="selected_voice_persona_id" label="旁白声音（可选）">
                <Select allowClear options={voiceOptions} placeholder="选择已有旁白声音画像" />
              </Form.Item>
              <Form.Item name="selected_lore_ids_text" label="Lore ID（可选，逗号或空格分隔，最多5条）">
                <Input placeholder="例如 lore-id-1, lore-id-2" />
              </Form.Item>
              <Form.Item name="prompt_context" label="额外提示上下文（可选）">
                <TextArea rows={3} maxLength={4000} showCount placeholder="粘贴要参考的章节尾句、节奏要求、场景限制..." />
              </Form.Item>
              <Form.Item name="draft_text" label="草稿正文（可选）">
                <TextArea rows={6} maxLength={12000} showCount placeholder="留空时服务端生成一个有角色台词位的写作骨架；填写则保存你的草稿并生成Trace。" />
              </Form.Item>
              <Button type="primary" htmlType="submit" loading={drafting} block>
                生成并保存场景草稿
              </Button>
            </Form>
          </Card>
        </Col>

        <Col xs={24} xl={14} style={{ minHeight: 0 }}>
          <Space direction="vertical" style={{ width: '100%', height: '100%' }} size={token.marginMD}>
            <Card title="已保存场景" style={{ flex: 1, minHeight: 0, overflow: 'hidden' }} bodyStyle={{ height: 360, overflow: 'auto' }}>
              <Table<GroupScene>
                rowKey="id"
                columns={columns}
                dataSource={items}
                loading={loading}
                pagination={false}
                locale={{ emptyText: <Empty description="暂无群像场景" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
              />
            </Card>

            <Card title="场景草稿与Trace" style={{ flex: 1, minHeight: 0, overflow: 'hidden' }} bodyStyle={{ maxHeight: 520, overflow: 'auto' }}>
              {selectedScene ? (
                <Space direction="vertical" style={{ width: '100%' }} size={token.marginSM}>
                  <Space wrap>
                    <Tag color="blue">trace_id={selectedScene.prompt_trace.trace_id}</Tag>
                    <Tag color="green">{selectedScene.prompt_trace.boundary_decision}</Tag>
                    <Tag>tokens≈{selectedScene.prompt_trace.budget_estimate.estimated_tokens}</Tag>
                  </Space>
                  <Card size="small" title="草稿正文">
                    <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: 0, fontSize: 13 }}>{selectedScene.draft_text}</pre>
                  </Card>
                  <Card size="small" title="Prompt Trace 预览">
                    <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: 0, fontSize: 13 }}>{selectedScene.prompt_trace.final_preview_text}</pre>
                  </Card>
                </Space>
              ) : (
                <Empty description="选择或创建一个群像场景" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              )}
            </Card>
          </Space>
        </Col>
      </Row>
    </div>
  );
}
