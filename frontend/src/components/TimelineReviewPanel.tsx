import { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Empty, InputNumber, Space, Table, Tabs, Tag, Typography, message, theme } from 'antd';
import type { TableColumnsType } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { timelineApi } from '../services/api';
import type {
  Career,
  Character,
  Organization,
  TimelineEvent,
  TimelineEventStatus,
  TimelineEventType,
  TimelineHistoryResponse,
  TimelineStateQuery,
  TimelineStateResponse,
} from '../types';

const { Paragraph, Text } = Typography;

interface TimelineReviewApiClient {
  getProjectState: typeof timelineApi.getProjectState;
  getProjectHistory: typeof timelineApi.getProjectHistory;
}

export interface TimelineReviewPanelProps {
  projectId?: string;
  title: string;
  eventTypes: TimelineEventType[];
  characters?: Pick<Character, 'id' | 'name'>[];
  organizationCharacters?: Pick<Character, 'id' | 'name'>[];
  organizations?: Array<Pick<Organization, 'id' | 'name' | 'character_id' | 'organization_entity_id'>>;
  careers?: Pick<Career, 'id' | 'name'>[];
  defaultChapterNumber?: number;
  defaultChapterOrder?: number;
  defaultMode?: 'current' | 'history';
  autoLoad?: boolean;
  apiClient?: TimelineReviewApiClient;
}

interface TimelineNameLookups {
  characterNameById: Map<string, string>;
  organizationNameById: Map<string, string>;
  careerNameById: Map<string, string>;
}

interface TimelineDescription {
  primary: string;
  secondary: string;
}

type TimelineViewMode = 'current' | 'history';

interface TimelineReviewPanelTestUtils {
  buildTimelineQueryParams: typeof buildTimelineQueryParams;
  filterTimelineEventsByTypes: typeof filterTimelineEventsByTypes;
  formatConfidence: typeof formatConfidence;
  formatEventStatus: typeof formatEventStatus;
  formatValidRange: typeof formatValidRange;
  getTimelineEventsForTypes: typeof getTimelineEventsForTypes;
  hasTimelineEnd: typeof hasTimelineEnd;
}

type TimelineReviewPanelComponent = ((props: TimelineReviewPanelProps) => JSX.Element) & {
  __testUtils: TimelineReviewPanelTestUtils;
};

const defaultApiClient: TimelineReviewApiClient = timelineApi;

const eventTypeConfig: Record<TimelineEventType, { label: string; color: string }> = {
  relationship: { label: '人物关系', color: 'geekblue' },
  affiliation: { label: '组织归属', color: 'cyan' },
  profession: { label: '职业变更', color: 'blue' },
  status: { label: '状态变化', color: 'purple' },
};

const eventStatusConfig: Record<TimelineEventStatus, { label: string; color: string }> = {
  active: { label: '生效中', color: 'success' },
  ended: { label: '已结束', color: 'warning' },
  superseded: { label: '已被替换', color: 'default' },
  rolled_back: { label: '已回滚', color: 'error' },
};

const currentEmptyState: TimelineStateResponse = {
  project_id: '',
  point: {
    chapter_id: null,
    chapter_number: 0,
    chapter_order: 0,
  },
  relationships: [],
  affiliations: [],
  professions: [],
};

function isNumber(value: number | null | undefined): value is number {
  return value !== null && value !== undefined;
}

function formatConfidence(confidence?: number | null): string {
  if (!isNumber(confidence)) {
    return '未记录';
  }
  return `${Math.round(Math.max(0, Math.min(1, confidence)) * 100)}%`;
}

function hasTimelineEnd(event: TimelineEvent): boolean {
  return event.event_status === 'ended' || isNumber(event.valid_to_chapter_order) || Boolean(event.valid_to_chapter_id);
}

function formatEventStatus(event: TimelineEvent, mode: TimelineViewMode = 'history'): { label: string; color: string } {
  if (mode === 'history' && event.event_status === 'active' && hasTimelineEnd(event)) {
    return eventStatusConfig.ended;
  }
  return eventStatusConfig[event.event_status] || { label: event.event_status, color: 'default' };
}

function formatValidRange(event: TimelineEvent): string {
  const from = event.valid_from_chapter_order ?? event.source_chapter_order;
  const to = event.valid_to_chapter_order;
  if (!isNumber(from) && !isNumber(to)) {
    return '未记录';
  }
  if (!isNumber(from)) {
    return `至第 ${to} 章前`;
  }
  return isNumber(to) ? `第 ${from} 章 → 第 ${to} 章前` : `第 ${from} 章起`;
}

function buildTimelineQueryParams(chapterNumber?: number, chapterOrder?: number): TimelineStateQuery {
  const params: TimelineStateQuery = {};
  if (isNumber(chapterNumber)) {
    params.chapter_number = chapterNumber;
  }
  if (isNumber(chapterOrder)) {
    params.chapter_order = chapterOrder;
  }
  return params;
}

function filterTimelineEventsByTypes(events: TimelineEvent[], eventTypes: TimelineEventType[]): TimelineEvent[] {
  if (eventTypes.length === 0) {
    return events;
  }
  const allowedTypes = new Set<TimelineEventType>(eventTypes);
  return events.filter(event => allowedTypes.has(event.event_type));
}

function getTimelineEventsForTypes(state: TimelineStateResponse, eventTypes: TimelineEventType[]): TimelineEvent[] {
  const eventsByType: Record<TimelineEventType, TimelineEvent[]> = {
    relationship: state.relationships,
    affiliation: state.affiliations,
    profession: state.professions,
    status: [],
  };
  return eventTypes.flatMap(eventType => eventsByType[eventType] || []);
}

function getShortId(id?: string | null): string | undefined {
  if (!id) return undefined;
  return id.length > 12 ? id.slice(0, 12) : id;
}

function resolveName(id: string | null | undefined, names: Map<string, string>, fallback: string): string {
  if (!id) {
    return fallback;
  }
  return names.get(id) || id;
}

function describeTimelineEvent(event: TimelineEvent, lookups: TimelineNameLookups): TimelineDescription {
  if (event.event_type === 'relationship') {
    const left = resolveName(event.character_id, lookups.characterNameById, '未知角色');
    const right = event.related_character_id
      ? resolveName(event.related_character_id, lookups.characterNameById, '未知对象')
      : resolveName(event.organization_entity_id, lookups.organizationNameById, '未知对象');
    return {
      primary: `${left} ↔ ${right}`,
      secondary: event.relationship_name || '未命名关系',
    };
  }

  if (event.event_type === 'affiliation') {
    const characterName = resolveName(event.character_id, lookups.characterNameById, '未知角色');
    const organizationName = resolveName(event.organization_entity_id, lookups.organizationNameById, '未知组织');
    return {
      primary: `${characterName} → ${organizationName}`,
      secondary: [event.position, isNumber(event.rank) ? `等级 ${event.rank}` : undefined].filter(Boolean).join(' · ') || '组织成员',
    };
  }

  if (event.event_type === 'profession') {
    const characterName = resolveName(event.character_id, lookups.characterNameById, '未知角色');
    const careerName = resolveName(event.career_id, lookups.careerNameById, '未知职业');
    return {
      primary: `${characterName} → ${careerName}`,
      secondary: isNumber(event.career_stage) ? `第 ${event.career_stage} 阶` : '职业分配',
    };
  }

  return {
    primary: resolveName(event.character_id, lookups.characterNameById, '未知角色'),
    secondary: event.relationship_name || event.position || '状态变化',
  };
}

function semanticTagsForEvent(event: TimelineEvent, mode: TimelineViewMode): Array<{ key: string; label: string; color: string }> {
  const tags: Array<{ key: string; label: string; color: string }> = [];
  if (event.supersedes_event_id) {
    tags.push({ key: 'changed', label: '变更', color: 'processing' });
  }
  if (mode === 'history' && hasTimelineEnd(event)) {
    tags.push({ key: 'ended', label: '结束', color: 'warning' });
  }
  if (event.event_status === 'rolled_back') {
    tags.push({ key: 'rolled_back', label: '回滚', color: 'error' });
  }
  if (event.event_status === 'superseded') {
    tags.push({ key: 'superseded', label: '被替换', color: 'default' });
  }
  if (tags.length === 0) {
    tags.push({ key: 'started', label: '开始', color: 'success' });
  }
  return tags;
}

const TimelineReviewPanelImpl = ({
  projectId,
  title,
  eventTypes,
  characters = [],
  organizationCharacters = [],
  organizations = [],
  careers = [],
  defaultChapterNumber,
  defaultChapterOrder,
  defaultMode = 'current',
  autoLoad = true,
  apiClient = defaultApiClient,
}: TimelineReviewPanelProps) => {
  const { token } = theme.useToken();
  const [loading, setLoading] = useState(false);
  const [currentState, setCurrentState] = useState<TimelineStateResponse | null>(null);
  const [historyEvents, setHistoryEvents] = useState<TimelineEvent[]>([]);
  const [chapterNumber, setChapterNumber] = useState<number | undefined>(defaultChapterNumber);
  const [chapterOrder, setChapterOrder] = useState<number | undefined>(defaultChapterOrder ?? defaultChapterNumber);

  const lookups = useMemo<TimelineNameLookups>(() => {
    const characterNameById = new Map<string, string>();
    const organizationNameById = new Map<string, string>();
    const careerNameById = new Map<string, string>();

    characters.forEach(character => {
      characterNameById.set(character.id, character.name);
    });
    organizationCharacters.forEach(organization => {
      characterNameById.set(organization.id, organization.name);
      organizationNameById.set(organization.id, organization.name);
    });
    organizations.forEach(organization => {
      organizationNameById.set(organization.id, organization.name);
      organizationNameById.set(organization.character_id, organization.name);
      if (organization.organization_entity_id) {
        organizationNameById.set(organization.organization_entity_id, organization.name);
      }
    });
    careers.forEach(career => {
      careerNameById.set(career.id, career.name);
    });

    return { characterNameById, organizationNameById, careerNameById };
  }, [careers, characters, organizationCharacters, organizations]);

  const loadTimeline = useCallback(async () => {
    if (!projectId) {
      setCurrentState(null);
      setHistoryEvents([]);
      return;
    }

    setLoading(true);
    try {
      const params = buildTimelineQueryParams(chapterNumber, chapterOrder);
      const statePromise = apiClient.getProjectState(projectId, params);
      const historyPromise: Promise<TimelineHistoryResponse> = eventTypes.length === 1
        ? apiClient.getProjectHistory(projectId, { event_type: eventTypes[0] })
        : apiClient.getProjectHistory(projectId);
      const [state, history] = await Promise.all([statePromise, historyPromise]);
      setCurrentState(state);
      setHistoryEvents(filterTimelineEventsByTypes(history.items || [], eventTypes));
    } catch (error) {
      console.error('加载时间线失败:', error);
      message.error('加载时间线失败');
    } finally {
      setLoading(false);
    }
  }, [apiClient, chapterNumber, chapterOrder, eventTypes, projectId]);

  useEffect(() => {
    if (autoLoad) {
      void loadTimeline();
    }
  }, [autoLoad, loadTimeline]);

  const currentEvents = useMemo(
    () => getTimelineEventsForTypes(currentState || currentEmptyState, eventTypes),
    [currentState, eventTypes],
  );

  const renderEvidence = (event: TimelineEvent) => (
    <Space direction="vertical" size={2} style={{ maxWidth: 420 }}>
      <Paragraph style={{ marginBottom: 0 }} ellipsis={{ rows: 2, tooltip: event.evidence_text || undefined }}>
        {event.evidence_text || '暂无证据片段'}
      </Paragraph>
      <Space size={4} wrap>
        <Text type="secondary" style={{ fontSize: token.fontSizeSM }}>置信度：{formatConfidence(event.confidence)}</Text>
        {isNumber(event.source_chapter_order) && <Tag>来源第 {event.source_chapter_order} 章</Tag>}
        {isNumber(event.source_start_offset) && isNumber(event.source_end_offset) && (
          <Text type="secondary" style={{ fontSize: token.fontSizeSM }}>位置：{event.source_start_offset}–{event.source_end_offset}</Text>
        )}
      </Space>
    </Space>
  );

  const buildColumns = (mode: TimelineViewMode): TableColumnsType<TimelineEvent> => [
    {
      title: '类型',
      dataIndex: 'event_type',
      width: 112,
      render: (eventType: TimelineEventType) => (
        <Tag color={eventTypeConfig[eventType]?.color || 'default'}>
          {eventTypeConfig[eventType]?.label || eventType}
        </Tag>
      ),
    },
    {
      title: '对象',
      key: 'entity',
      width: 220,
      render: (_: unknown, event) => {
        const description = describeTimelineEvent(event, lookups);
        return (
          <Space direction="vertical" size={2}>
            <Text strong>{description.primary}</Text>
            <Text type="secondary" style={{ fontSize: token.fontSizeSM }}>{description.secondary}</Text>
          </Space>
        );
      },
    },
    {
      title: '事件',
      key: 'semantics',
      width: 150,
      render: (_: unknown, event) => (
        <Space direction="vertical" size={4}>
          <Space size={4} wrap>
            {semanticTagsForEvent(event, mode).map(tag => <Tag key={tag.key} color={tag.color}>{tag.label}</Tag>)}
          </Space>
          {event.supersedes_event_id && (
            <Text type="secondary" style={{ fontSize: token.fontSizeSM }}>替换事件 {getShortId(event.supersedes_event_id)}</Text>
          )}
        </Space>
      ),
    },
    {
      title: '有效范围',
      key: 'valid_range',
      width: 150,
      render: (_: unknown, event) => <Text>{formatValidRange(event)}</Text>,
    },
    {
      title: '状态',
      key: 'event_status',
      width: 112,
      render: (_: unknown, event) => {
        const status = formatEventStatus(event, mode);
        return <Tag color={status.color}>{status.label}</Tag>;
      },
    },
    {
      title: '证据',
      key: 'evidence',
      render: (_: unknown, event) => renderEvidence(event),
    },
  ];

  const renderTable = (events: TimelineEvent[], emptyText: string, mode: TimelineViewMode) => (
    <Table<TimelineEvent>
      rowKey="id"
      columns={buildColumns(mode)}
      dataSource={events}
      loading={loading}
      size="small"
      locale={{ emptyText: <Empty description={emptyText} /> }}
      pagination={events.length > 6 ? { pageSize: 6, showSizeChanger: false } : false}
      scroll={{ x: 920 }}
    />
  );

  if (!projectId) {
    return <Empty description="请选择项目后查看时间线" />;
  }

  return (
    <Card
      size="small"
      title={title}
      style={{ borderColor: token.colorBorderSecondary, borderRadius: token.borderRadiusLG }}
      styles={{ body: { padding: token.paddingMD } }}
    >
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <Alert
          type="info"
          showIcon
          message="按章节/顺序查询当前投影"
          description="当前投影只显示该章节节点仍然生效的关系；历史模式保留已结束、被替换、被回滚的记录与证据。"
        />

        <Space wrap align="end">
          <Space direction="vertical" size={2}>
            <Text type="secondary">章节</Text>
            <InputNumber
              aria-label="时间线章节过滤"
              min={0}
              value={chapterNumber}
              placeholder="最新"
              onChange={(value) => setChapterNumber(isNumber(value) ? value : undefined)}
            />
          </Space>
          <Space direction="vertical" size={2}>
            <Text type="secondary">章内/故事顺序</Text>
            <InputNumber
              aria-label="时间线顺序过滤"
              min={0}
              value={chapterOrder}
              placeholder="同章节"
              onChange={(value) => setChapterOrder(isNumber(value) ? value : undefined)}
            />
          </Space>
          <Button type="primary" icon={<SearchOutlined />} loading={loading} onClick={loadTimeline}>
            查询投影
          </Button>
          <Space size={4} wrap>
            {eventTypes.map(eventType => (
              <Tag key={eventType} color={eventTypeConfig[eventType]?.color || 'default'}>
                {eventTypeConfig[eventType]?.label || eventType}
              </Tag>
            ))}
          </Space>
        </Space>

        {currentState && (
          <Text type="secondary">
            当前坐标：第 {currentState.point.chapter_number} 章 / 顺序 {currentState.point.chapter_order}
          </Text>
        )}

        <Tabs
          defaultActiveKey={defaultMode}
          destroyOnHidden={false}
          items={[
            {
              key: 'current',
              label: `当前投影 (${currentEvents.length})`,
              children: renderTable(currentEvents, '当前章节没有生效记录', 'current'),
            },
            {
              key: 'history',
              label: `历史记录 (${historyEvents.length})`,
              children: renderTable(historyEvents, '暂无历史时间线记录', 'history'),
            },
          ]}
        />
      </Space>
    </Card>
  );
};

export const TimelineReviewPanel = TimelineReviewPanelImpl as TimelineReviewPanelComponent;

TimelineReviewPanel.__testUtils = {
  buildTimelineQueryParams,
  filterTimelineEventsByTypes,
  formatConfidence,
  formatEventStatus,
  formatValidRange,
  getTimelineEventsForTypes,
  hasTimelineEnd,
};

export default TimelineReviewPanel;
