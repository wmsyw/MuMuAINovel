import { useEffect } from 'react';
import { Alert, Col, Form, Input, InputNumber, Modal, Row, Select, Typography, theme } from 'antd';
import type { Character, Goldfinger, GoldfingerCreate, GoldfingerStatus, GoldfingerUpdate } from '../../types';
import { goldfingerJsonFieldLabels, goldfingerStatusOptions, toEditorText } from './constants';

const { TextArea } = Input;
const { Text } = Typography;

type GoldfingerFormValues = {
  name: string;
  owner_character_id?: string;
  owner_character_name?: string;
  type?: string;
  status: GoldfingerStatus;
  summary?: string;
  confidence?: number;
  last_source_chapter_id?: string;
  rules?: string;
  tasks?: string;
  rewards?: string;
  limits?: string;
  trigger_conditions?: string;
  cooldown?: string;
  aliases?: string;
  metadata?: string;
};

interface GoldfingerEditorProps {
  open: boolean;
  mode: 'create' | 'edit';
  goldfinger?: Goldfinger | null;
  characters: Pick<Character, 'id' | 'name'>[];
  confirmLoading?: boolean;
  onCancel: () => void;
  onSubmit: (payload: GoldfingerCreate | GoldfingerUpdate) => Promise<void> | void;
}

function parseFlexibleField(value?: string): unknown {
  const text = value?.trim();
  if (!text) return undefined;
  try {
    return JSON.parse(text);
  } catch {
    const lines = text.split('\n').map(line => line.trim()).filter(Boolean);
    return lines.length > 1 ? lines : text;
  }
}

function parseMetadata(value?: string): Record<string, unknown> | undefined {
  const text = value?.trim();
  if (!text) return undefined;
  const parsed = JSON.parse(text) as unknown;
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('元数据必须是 JSON 对象，例如 {"key":"value"}');
  }
  return parsed as Record<string, unknown>;
}

function buildInitialValues(goldfinger?: Goldfinger | null): Partial<GoldfingerFormValues> {
  if (!goldfinger) {
    return { status: 'unknown' };
  }
  return {
    name: goldfinger.name,
    owner_character_id: goldfinger.owner_character_id || undefined,
    owner_character_name: goldfinger.owner_character_name || undefined,
    type: goldfinger.type || undefined,
    status: goldfinger.status,
    summary: goldfinger.summary || undefined,
    confidence: goldfinger.confidence ?? undefined,
    last_source_chapter_id: goldfinger.last_source_chapter_id || undefined,
    rules: toEditorText(goldfinger.rules),
    tasks: toEditorText(goldfinger.tasks),
    rewards: toEditorText(goldfinger.rewards),
    limits: toEditorText(goldfinger.limits),
    trigger_conditions: toEditorText(goldfinger.trigger_conditions),
    cooldown: toEditorText(goldfinger.cooldown),
    aliases: toEditorText(goldfinger.aliases),
    metadata: toEditorText(goldfinger.metadata),
  };
}

export default function GoldfingerEditor({
  open,
  mode,
  goldfinger,
  characters,
  confirmLoading = false,
  onCancel,
  onSubmit,
}: GoldfingerEditorProps) {
  const [form] = Form.useForm<GoldfingerFormValues>();
  const { token } = theme.useToken();

  useEffect(() => {
    if (open) {
      form.setFieldsValue(buildInitialValues(goldfinger));
    }
  }, [form, goldfinger, open]);

  const handleFinish = async (values: GoldfingerFormValues) => {
    const selectedOwner = characters.find(character => character.id === values.owner_character_id);
    const payload: GoldfingerCreate | GoldfingerUpdate = {
      name: values.name?.trim(),
      owner_character_id: values.owner_character_id || null,
      owner_character_name: selectedOwner?.name || values.owner_character_name?.trim() || null,
      type: values.type?.trim() || null,
      status: values.status,
      summary: values.summary?.trim() || null,
      confidence: values.confidence ?? null,
      last_source_chapter_id: values.last_source_chapter_id?.trim() || null,
      rules: parseFlexibleField(values.rules),
      tasks: parseFlexibleField(values.tasks),
      rewards: parseFlexibleField(values.rewards),
      limits: parseFlexibleField(values.limits),
      trigger_conditions: parseFlexibleField(values.trigger_conditions),
      cooldown: parseFlexibleField(values.cooldown),
      aliases: parseFlexibleField(values.aliases),
      metadata: parseMetadata(values.metadata),
    };

    await onSubmit(payload);
    form.resetFields();
  };

  return (
    <Modal
      title={mode === 'create' ? '新建金手指' : '编辑金手指'}
      open={open}
      onCancel={() => {
        form.resetFields();
        onCancel();
      }}
      onOk={() => form.submit()}
      okText={mode === 'create' ? '创建' : '保存'}
      cancelText="取消"
      confirmLoading={confirmLoading}
      width={820}
      destroyOnClose
    >
      <Alert
        type="info"
        showIcon
        message="字段支持 JSON 或多行文本"
        description="规则、任务、奖励、限制等字段会优先按 JSON 解析；不是合法 JSON 时，多行文本会保存为列表，单行文本会保存为字符串。"
        style={{ marginBottom: token.marginMD }}
      />
      <Form form={form} layout="vertical" onFinish={handleFinish} initialValues={{ status: 'unknown' }}>
        <Row gutter={16}>
          <Col xs={24} md={12}>
            <Form.Item label="名称" name="name" rules={[{ required: true, message: '请输入金手指名称' }]}>
              <Input placeholder="如：天命系统、万界商城、祖龙血脉" />
            </Form.Item>
          </Col>
          <Col xs={24} md={6}>
            <Form.Item label="类型" name="type">
              <Input placeholder="系统 / 血脉 / 神器" />
            </Form.Item>
          </Col>
          <Col xs={24} md={6}>
            <Form.Item label="状态" name="status" rules={[{ required: true, message: '请选择状态' }]}>
              <Select options={goldfingerStatusOptions.map(item => ({ value: item.value, label: item.label }))} />
            </Form.Item>
          </Col>
        </Row>

        <Row gutter={16}>
          <Col xs={24} md={12}>
            <Form.Item label="拥有者角色" name="owner_character_id">
              <Select
                allowClear
                showSearch
                placeholder="选择已有角色（可选）"
                optionFilterProp="label"
                options={characters.map(character => ({ value: character.id, label: character.name }))}
              />
            </Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item label="拥有者快照" name="owner_character_name" tooltip="未选择角色时可手动填写名称快照">
              <Input placeholder="如：林墨" />
            </Form.Item>
          </Col>
        </Row>

        <Form.Item label="概要" name="summary">
          <TextArea rows={3} placeholder="概括金手指来源、当前能力、使用代价和故事定位" />
        </Form.Item>

        <Row gutter={16}>
          <Col xs={24} md={12}>
            <Form.Item label="置信度" name="confidence" tooltip="手动维护可留空；正文同步候选会写入置信度">
              <InputNumber min={0} max={1} step={0.01} style={{ width: '100%' }} placeholder="0.00 - 1.00" />
            </Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item label="最后来源章节ID" name="last_source_chapter_id">
              <Input placeholder="可选，通常由正文同步自动写入" />
            </Form.Item>
          </Col>
        </Row>

        <Row gutter={16}>
          {(['rules', 'tasks', 'rewards', 'limits', 'trigger_conditions', 'cooldown', 'aliases', 'metadata'] as const).map(field => (
            <Col xs={24} md={12} key={field}>
              <Form.Item
                label={goldfingerJsonFieldLabels[field]}
                name={field}
                tooltip={field === 'metadata' ? '必须是 JSON 对象' : '支持 JSON、单行文本或多行列表'}
                rules={field === 'metadata' ? [{
                  validator: async (_, value?: string) => {
                    if (!value?.trim()) return;
                    parseMetadata(value);
                  },
                }] : undefined}
              >
                <TextArea rows={4} placeholder={field === 'metadata' ? '{"来源":"手动整理"}' : `填写${goldfingerJsonFieldLabels[field]}，可用 JSON 或每行一条`} />
              </Form.Item>
            </Col>
          ))}
        </Row>

        <Text type="secondary">提示：导入导出的版本号固定为 goldfinger-card.v1，前端不会写入后端不存在的字段。</Text>
      </Form>
    </Modal>
  );
}
