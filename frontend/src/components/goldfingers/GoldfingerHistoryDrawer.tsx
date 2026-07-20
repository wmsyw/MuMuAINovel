import { Button, Drawer, Empty, Space, Spin, Tag, Timeline, Typography, theme } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import type { Goldfinger, GoldfingerHistoryEvent } from '../../types';
import { formatConfidence, stringifyGoldfingerValue } from './constants';
import { sx } from '../../styles/sx';

const { Paragraph, Text } = Typography;

interface GoldfingerHistoryDrawerProps {
  open: boolean;
  goldfinger?: Goldfinger | null;
  history: GoldfingerHistoryEvent[];
  loading?: boolean;
  onClose: () => void;
  onReload: () => void;
}

const eventLabels: Record<string, { label: string; color: string }> = {
  created: { label: '创建', color: 'success' },
  imported: { label: '导入', color: 'blue' },
  updated: { label: '更新', color: 'processing' },
  merged: { label: '正文合并', color: 'purple' },
};

function formatDate(value?: string | null): string {
  if (!value) return '未记录时间';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false });
}

function renderSnapshot(title: string, value: unknown, borderColor: string) {
  if (value === null || value === undefined) return null;
  return (
    <div className={sx({ borderLeft: `3px solid ${borderColor}`, paddingLeft: 10 })}>
      <Text type="secondary">{title}</Text>
      <pre className="u-64z7j1">
        {stringifyGoldfingerValue(value)}
      </pre>
    </div>
  );
}

export default function GoldfingerHistoryDrawer({
  open,
  goldfinger,
  history,
  loading = false,
  onClose,
  onReload,
}: GoldfingerHistoryDrawerProps) {
  const { token } = theme.useToken();

  return (
    <Drawer
      title={goldfinger ? `历史记录：${goldfinger.name}` : '金手指历史'}
      open={open}
      width={720}
      onClose={onClose}
      extra={<Button icon={<ReloadOutlined />} onClick={onReload} loading={loading}>刷新</Button>}
    >
      {loading ? (
        <div className="u-1j6dug5"><Spin tip="加载历史中..." /></div>
      ) : history.length === 0 ? (
        <Empty description="暂无历史事件" />
      ) : (
        <Timeline
          items={history.map(event => {
            const meta = eventLabels[event.event_type] || { label: event.event_type, color: 'default' };
            return {
              color: meta.color === 'default' ? token.colorBorder : meta.color,
              children: (
                <Space direction="vertical" size="small" className="u-1f3r3s">
                  <Space wrap>
                    <Tag color={meta.color}>{meta.label}</Tag>
                    <Text>{formatDate(event.created_at)}</Text>
                    {event.source_type && <Tag>{event.source_type}</Tag>}
                    <Text type="secondary">置信度：{formatConfidence(event.confidence)}</Text>
                    {event.chapter_id && <Tag color="cyan">来源章节 {event.chapter_id}</Tag>}
                  </Space>
                  {event.evidence_excerpt && (
                    <Paragraph
                      className={sx({
                        marginBottom: 0,
                        padding: '8px 10px',
                        background: token.colorFillTertiary,
                        borderRadius: token.borderRadius,
                      })}
                    >
                      {event.evidence_excerpt}
                    </Paragraph>
                  )}
                  <Space direction="vertical" size="small" className="u-1f3r3s">
                    {renderSnapshot('旧值', event.old_value, token.colorWarning)}
                    {renderSnapshot('新值', event.new_value, token.colorPrimary)}
                  </Space>
                </Space>
              ),
            };
          })}
        />
      )}
    </Drawer>
  );
}
