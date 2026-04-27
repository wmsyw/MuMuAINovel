import { Button, Empty, Popconfirm, Space, Table, Tag, Tooltip, Typography, theme } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { DeleteOutlined, EditOutlined, HistoryOutlined, ThunderboltOutlined, EyeOutlined } from '@ant-design/icons';
import type { Goldfinger } from '../../types';
import { formatConfidence, getGoldfingerStatusMeta } from './constants';

const { Paragraph, Text } = Typography;

interface GoldfingerListProps {
  goldfingers: Goldfinger[];
  loading?: boolean;
  selectedId?: string;
  onSelect: (goldfinger: Goldfinger) => void;
  onEdit: (goldfinger: Goldfinger) => void;
  onDelete: (goldfinger: Goldfinger) => void;
  onHistory: (goldfinger: Goldfinger) => void;
}

function formatDate(value?: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', { hour12: false });
}

export default function GoldfingerList({
  goldfingers,
  loading = false,
  selectedId,
  onSelect,
  onEdit,
  onDelete,
  onHistory,
}: GoldfingerListProps) {
  const { token } = theme.useToken();

  const columns: ColumnsType<Goldfinger> = [
    {
      title: '名称',
      dataIndex: 'name',
      width: 220,
      fixed: 'left',
      render: (_: string, record) => {
        const status = getGoldfingerStatusMeta(record.status);
        return (
          <Space direction="vertical" size={2}>
            <Space wrap size={6}>
              <ThunderboltOutlined style={{ color: token.colorWarning }} />
              <Text strong>{record.name}</Text>
              <Tag color={status.color}>{status.label}</Tag>
            </Space>
            <Text type="secondary" style={{ fontSize: token.fontSizeSM }}>
              {record.normalized_name || '未记录规范名'}
            </Text>
          </Space>
        );
      },
    },
    {
      title: '类型 / 拥有者',
      key: 'type-owner',
      width: 190,
      render: (_: unknown, record) => (
        <Space direction="vertical" size={2}>
          <Tag color="geekblue">{record.type || '未分类'}</Tag>
          <Text type="secondary">{record.owner_character_name || '未指定拥有者'}</Text>
        </Space>
      ),
    },
    {
      title: '概要',
      dataIndex: 'summary',
      render: (summary?: string | null) => (
        <Paragraph style={{ marginBottom: 0 }} ellipsis={{ rows: 2, tooltip: summary || undefined }}>
          {summary || '暂无概要'}
        </Paragraph>
      ),
    },
    {
      title: '来源',
      dataIndex: 'source',
      width: 110,
      render: (source?: string) => <Tag>{source || 'manual'}</Tag>,
    },
    {
      title: '置信度',
      dataIndex: 'confidence',
      width: 110,
      render: (confidence?: number | null) => formatConfidence(confidence),
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      width: 170,
      render: formatDate,
    },
    {
      title: '操作',
      key: 'actions',
      width: 250,
      fixed: 'right',
      render: (_: unknown, record) => (
        <Space wrap size={4}>
          <Tooltip title="查看详情">
            <Button size="small" icon={<EyeOutlined />} onClick={() => onSelect(record)}>详情</Button>
          </Tooltip>
          <Button size="small" icon={<EditOutlined />} onClick={() => onEdit(record)}>编辑</Button>
          <Button size="small" icon={<HistoryOutlined />} onClick={() => onHistory(record)}>历史</Button>
          <Popconfirm
            title="确认删除金手指？"
            description={`删除「${record.name}」后不可恢复。`}
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
            onConfirm={() => onDelete(record)}
          >
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  if (!loading && goldfingers.length === 0) {
    return <Empty description="还没有金手指，点击「新建金手指」开始维护。" />;
  }

  return (
    <Table<Goldfinger>
      rowKey="id"
      columns={columns}
      dataSource={goldfingers}
      loading={loading}
      size="middle"
      scroll={{ x: 1120 }}
      pagination={goldfingers.length > 10 ? { pageSize: 10, showTotal: total => `共 ${total} 个金手指` } : false}
      rowClassName={record => record.id === selectedId ? 'goldfinger-row-selected' : ''}
      onRow={record => ({
        onDoubleClick: () => onSelect(record),
      })}
    />
  );
}
