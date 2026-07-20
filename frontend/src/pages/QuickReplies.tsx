import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  Alert,
  Button,
  Card,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
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
  PlusOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SnippetsOutlined,
} from '@ant-design/icons';
import { quickReplyApi } from '../services/api';
import type { QuickReply, QuickReplyCreate } from '../types';
import { sx } from '../styles/sx';

const { Paragraph, Text, Title } = Typography;
const { TextArea } = Input;

interface QuickReplyFormValues {
  label: string;
  snippet: string;
  sort_order?: number;
  enabled?: boolean;
}

function buildPayload(values: QuickReplyFormValues): QuickReplyCreate {
  return {
    label: values.label.trim(),
    action_type: 'safe_snippet',
    snippet: values.snippet.trim(),
    sort_order: values.sort_order ?? 0,
    enabled: values.enabled ?? true,
  };
}

export default function QuickReplies() {
  const { projectId } = useParams<{ projectId: string }>();
  const { token } = theme.useToken();
  const [form] = Form.useForm<QuickReplyFormValues>();

  const [items, setItems] = useState<QuickReply[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<QuickReply | null>(null);
  const [error, setError] = useState<string | null>(null);

  const enabledCount = useMemo(() => items.filter(item => item.enabled).length, [items]);

  const loadReplies = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const response = await quickReplyApi.list(projectId);
      setItems(response.items);
    } catch (err) {
      console.error('加载快捷片段失败:', err);
      setError('快捷片段暂时不可用，可能是功能未启用或当前账号无权访问。');
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadReplies();
  }, [loadReplies]);

  const openCreateModal = () => {
    setEditing(null);
    form.setFieldsValue({ label: '', snippet: '', sort_order: items.length + 1, enabled: true });
    setModalOpen(true);
  };

  const openEditModal = (item: QuickReply) => {
    setEditing(item);
    form.setFieldsValue({
      label: item.label,
      snippet: item.snippet,
      sort_order: item.sort_order,
      enabled: item.enabled,
    });
    setModalOpen(true);
  };

  const handleSubmit = async (values: QuickReplyFormValues) => {
    if (!projectId) return;
    setSaving(true);
    setError(null);
    try {
      const payload = buildPayload(values);
      if (editing) {
        await quickReplyApi.update(editing.id, payload);
        antdMessage.success('快捷片段已更新');
      } else {
        await quickReplyApi.create(projectId, payload);
        antdMessage.success('快捷片段已创建');
      }
      setModalOpen(false);
      setEditing(null);
      await loadReplies();
    } catch (err) {
      console.error('保存快捷片段失败:', err);
      setError('保存失败：仅支持安全静态片段，不能包含脚本、命令、网络请求或宏模板语法。');
    } finally {
      setSaving(false);
    }
  };

  const handleToggleEnabled = async (item: QuickReply, enabled: boolean) => {
    try {
      await quickReplyApi.update(item.id, { enabled });
      setItems(prev => prev.map(reply => reply.id === item.id ? { ...reply, enabled } : reply));
    } catch (err) {
      console.error('切换快捷片段状态失败:', err);
      antdMessage.error('状态更新失败');
    }
  };

  const handleDelete = async (item: QuickReply) => {
    try {
      await quickReplyApi.deleteReply(item.id);
      setItems(prev => prev.filter(reply => reply.id !== item.id));
      antdMessage.success('快捷片段已删除');
    } catch (err) {
      console.error('删除快捷片段失败:', err);
      antdMessage.error('删除失败');
    }
  };

  const columns: ColumnsType<QuickReply> = [
    {
      title: '顺序',
      dataIndex: 'sort_order',
      width: 80,
      sorter: (left, right) => left.sort_order - right.sort_order,
    },
    {
      title: '标签',
      dataIndex: 'label',
      width: 180,
      render: (label: string) => <Text strong>{label}</Text>,
    },
    {
      title: '动作',
      dataIndex: 'action_type',
      width: 130,
      render: () => <Tag color="green">safe_snippet</Tag>,
    },
    {
      title: '片段内容',
      dataIndex: 'snippet',
      render: (snippet: string) => (
        <Paragraph ellipsis={{ rows: 2, expandable: true, symbol: '展开' }} className="u-19o9sm6">
          {snippet}
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
      width: 150,
      render: (_, item) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEditModal(item)}>编辑</Button>
          <Popconfirm title="删除快捷片段？" description="历史会话记录会保留已写入文本。" onConfirm={() => handleDelete(item)}>
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div className={sx({ height: '100%', display: 'flex', flexDirection: 'column', gap: token.paddingMD })}>
      <Card>
        <Space align="start" className="u-1qos3j5" wrap>
          <Space direction="vertical" size={4}>
            <Space>
              <SnippetsOutlined className={sx({ color: token.colorPrimary, fontSize: 24 })} />
              <Title level={3} className="u-avalr8">快捷片段</Title>
            </Space>
            <Paragraph type="secondary" className="u-1sezbee">
              项目内快捷回复只保存静态安全片段。应用时会显式写入创作会话记录，并附带 trace 标签；不会执行脚本、命令、网络请求，也不会暗改提示词。
            </Paragraph>
          </Space>
          <Space wrap>
            <Tag icon={<SafetyCertificateOutlined />} color="green">启用 {enabledCount}/{items.length}</Tag>
            <Button icon={<ReloadOutlined />} onClick={loadReplies} loading={loading}>刷新</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>新建片段</Button>
          </Space>
        </Space>
      </Card>

      {error && <Alert type="warning" showIcon message={error} />}

      <Card className="u-1tqrzca" bodyStyle={{ height: '100%', overflow: 'auto' }}>
        <Table<QuickReply>
          rowKey="id"
          columns={columns}
          dataSource={items}
          loading={loading}
          pagination={false}
          locale={{ emptyText: <Empty description="暂无快捷片段" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
        />
      </Card>

      <Modal
        title={editing ? '编辑快捷片段' : '新建快捷片段'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={saving}
        okText="保存"
        cancelText="取消"
        destroyOnClose
      >
        <Alert
          type="info"
          showIcon
          className={sx({ marginBottom: token.marginMD })}
          message="安全边界"
          description="只允许普通文本片段。包含 STscript/Slash 命令、脚本、Shell/网络命令或模板宏的内容会被后端拒绝。"
        />
        <Form<QuickReplyFormValues>
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          preserve={false}
        >
          <Form.Item name="label" label="按钮标签" rules={[{ required: true, message: '请输入按钮标签' }]}>
            <Input maxLength={100} placeholder="例如：雨夜氛围" />
          </Form.Item>
          <Form.Item name="sort_order" label="显示顺序">
            <InputNumber className="u-1f3r3s" min={0} precision={0} />
          </Form.Item>
          <Form.Item name="enabled" label="启用状态" valuePropName="checked">
            <Switch checkedChildren="启用" unCheckedChildren="停用" />
          </Form.Item>
          <Form.Item name="snippet" label="安全片段" rules={[{ required: true, message: '请输入要插入的静态片段' }]}>
            <TextArea rows={6} maxLength={4000} showCount placeholder="输入普通文本片段，不要包含脚本、命令或宏语法" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
