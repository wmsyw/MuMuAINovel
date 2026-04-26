import { useCallback, useEffect, useMemo, useState } from 'react';
import { Empty, Space, Table, Tag, Typography, message, theme } from 'antd';
import { timelineApi } from '../services/api';
import type { Career, Character, TimelineEvent } from '../types';

const { Paragraph, Text } = Typography;

interface ProfessionTimelinePanelProps {
  projectId?: string;
  careers: Career[];
  characters: Character[];
}

export default function ProfessionTimelinePanel({ projectId, careers, characters }: ProfessionTimelinePanelProps) {
  const { token } = theme.useToken();
  const [loading, setLoading] = useState(false);
  const [events, setEvents] = useState<TimelineEvent[]>([]);

  const careerNameById = useMemo(() => new Map(careers.map(career => [career.id, career.name])), [careers]);
  const characterNameById = useMemo(() => new Map(characters.map(character => [character.id, character.name])), [characters]);

  const loadTimeline = useCallback(async () => {
    if (!projectId) {
      setEvents([]);
      return;
    }
    setLoading(true);
    try {
      const response = await timelineApi.getProjectHistory(projectId, { event_type: 'profession' });
      setEvents(response.items || []);
    } catch (error) {
      console.error('加载职业时间线失败:', error);
      message.error('加载职业时间线失败');
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void loadTimeline();
  }, [loadTimeline]);

  return (
    <Table<TimelineEvent>
      rowKey="id"
      loading={loading}
      dataSource={events}
      size="small"
      locale={{ emptyText: <Empty description="暂无职业时间线记录" /> }}
      pagination={events.length > 8 ? { pageSize: 8, showSizeChanger: false } : false}
      columns={[
        {
          title: '角色',
          dataIndex: 'character_id',
          render: (characterId: string | null) => characterId ? characterNameById.get(characterId) || characterId : '-',
        },
        {
          title: '职业',
          dataIndex: 'career_id',
          render: (careerId: string | null) => careerId ? careerNameById.get(careerId) || careerId : '-',
        },
        {
          title: '阶段',
          dataIndex: 'career_stage',
          width: 88,
          render: (stage: number | null) => stage ? <Tag color="blue">第 {stage} 阶</Tag> : '-',
        },
        {
          title: '有效章节',
          key: 'valid_range',
          render: (_: unknown, record: TimelineEvent) => {
            const from = record.valid_from_chapter_order ?? record.source_chapter_order;
            const to = record.valid_to_chapter_order;
            return from ? `${from}${to ? ` → ${to}` : ' 起'}` : '-';
          },
        },
        {
          title: '状态',
          dataIndex: 'event_status',
          width: 96,
          render: (status: TimelineEvent['event_status']) => (
            <Tag color={status === 'active' ? 'success' : status === 'rolled_back' ? 'error' : 'default'}>
              {status === 'active' ? '生效中' : status === 'rolled_back' ? '已回滚' : status}
            </Tag>
          ),
        },
        {
          title: '证据',
          dataIndex: 'evidence_text',
          render: (evidence: string | null, record) => (
            <Space direction="vertical" size={2} style={{ maxWidth: 360 }}>
              <Paragraph style={{ marginBottom: 0 }} ellipsis={{ rows: 2, tooltip: evidence || undefined }}>
                {evidence || '暂无证据片段'}
              </Paragraph>
              <Text type="secondary" style={{ fontSize: 12 }}>
                置信度：{record.confidence !== null && record.confidence !== undefined ? `${Math.round(record.confidence * 100)}%` : '未记录'}
              </Text>
            </Space>
          ),
        },
      ]}
      style={{
        border: `1px solid ${token.colorBorderSecondary}`,
        borderRadius: token.borderRadiusLG,
        overflow: 'hidden',
      }}
    />
  );
}
