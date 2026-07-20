import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  Alert,
  Button,
  Card,
  Empty,
  Input,
  List,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
  message as antdMessage,
  theme,
} from 'antd';
import {
  FileSearchOutlined,
  MessageOutlined,
  PlusOutlined,
  ReloadOutlined,
  SendOutlined,
  SnippetsOutlined,
} from '@ant-design/icons';
import { creativeSessionApi, quickReplyApi } from '../services/api';
import type {
  CreativeSession,
  CreativeSessionDetail,
  CreativeSessionMessage,
  CreativeSessionRole,
  CreativeSessionSearchResult,
  QuickReply,
} from '../types';
import { sx } from '../styles/sx';

const { Text, Title, Paragraph } = Typography;
const { TextArea } = Input;

const ROLE_LABELS: Record<string, string> = {
  user: '创作想法',
  assistant: '整理回应',
  system: '系统备注',
  note: '写作笔记',
};

const ROLE_COLORS: Record<string, string> = {
  user: 'blue',
  assistant: 'green',
  system: 'default',
  note: 'gold',
};

function formatDate(value?: string | null): string {
  if (!value) return '刚刚';
  return new Date(value).toLocaleString('zh-CN');
}

function sortMessages(messages: CreativeSessionMessage[]): CreativeSessionMessage[] {
  return [...messages].sort((left, right) => left.position - right.position);
}

export default function CreativeSessions() {
  const { projectId } = useParams<{ projectId: string }>();
  const { token } = theme.useToken();
  const alphaColor = (color: string, alpha: number) => `color-mix(in srgb, ${color} ${(alpha * 100).toFixed(0)}%, transparent)`;

  const [sessions, setSessions] = useState<CreativeSession[]>([]);
  const [selectedSession, setSelectedSession] = useState<CreativeSessionDetail | null>(null);
  const [sessionTitle, setSessionTitle] = useState('');
  const [draftContent, setDraftContent] = useState('');
  const [draftRole, setDraftRole] = useState<CreativeSessionRole>('note');
  const [quickReplies, setQuickReplies] = useState<QuickReply[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<CreativeSessionSearchResult[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [loadingQuickReplies, setLoadingQuickReplies] = useState(false);
  const [creating, setCreating] = useState(false);
  const [appending, setAppending] = useState(false);
  const [applyingQuickReplyId, setApplyingQuickReplyId] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const messages = useMemo(
    () => sortMessages(selectedSession?.messages || []),
    [selectedSession?.messages],
  );

  const openSession = useCallback(async (sessionId: string) => {
    setLoadingDetail(true);
    setError(null);
    try {
      const detail = await creativeSessionApi.getSession(sessionId);
      setSelectedSession(detail);
    } catch (err) {
      console.error('重新打开创作会话失败:', err);
      setError('无法打开该创作会话，请确认项目权限或稍后重试。');
      setSelectedSession(null);
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  const loadSessions = useCallback(async () => {
    if (!projectId) return;
    setLoadingSessions(true);
    setError(null);
    try {
      const response = await creativeSessionApi.listSessions(projectId);
      setSessions(response.items);

      const selectedStillExists = selectedSession
        ? response.items.some(item => item.id === selectedSession.id)
        : false;

      if (selectedStillExists && selectedSession) {
        await openSession(selectedSession.id);
      } else if (response.items.length === 1) {
        await openSession(response.items[0].id);
      } else if (response.items.length === 0) {
        setSelectedSession(null);
      }
    } catch (err) {
      console.error('加载创作会话失败:', err);
      setError('创作会话暂时不可用，可能是功能未启用或当前账号无权访问。');
      setSessions([]);
      setSelectedSession(null);
    } finally {
      setLoadingSessions(false);
    }
  }, [openSession, projectId, selectedSession]);

  const loadQuickReplies = useCallback(async () => {
    if (!projectId) return;
    setLoadingQuickReplies(true);
    try {
      const response = await quickReplyApi.list(projectId, { enabled: true });
      setQuickReplies(response.items);
    } catch (err) {
      console.error('加载快捷片段失败:', err);
      setQuickReplies([]);
      setError('快捷片段暂时不可用，可能是功能未启用或当前账号无权访问。');
    } finally {
      setLoadingQuickReplies(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadSessions();
    // selectedSession 变化时不重新拉取列表，避免打开会话后循环请求。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const handleCreateSession = async () => {
    if (!projectId) return;
    const title = sessionTitle.trim();
    if (!title) {
      antdMessage.warning('请输入会话标题');
      return;
    }

    setCreating(true);
    setError(null);
    try {
      const created = await creativeSessionApi.createSession(projectId, {
        title,
        metadata: { source: 'creative-session-page' },
      });
      setSessionTitle('');
      setSessions(prev => [created, ...prev.filter(item => item.id !== created.id)]);
      setSelectedSession({ ...created, messages: [] });
      antdMessage.success('创作会话已创建');
    } catch (err) {
      console.error('创建创作会话失败:', err);
      setError('创建失败，请稍后重试。');
    } finally {
      setCreating(false);
    }
  };

  const handleAppendMessage = async () => {
    const content = draftContent.trim();
    if (!selectedSession) {
      antdMessage.warning('请先创建或选择一个创作会话');
      return;
    }
    if (!content) {
      antdMessage.warning('请输入要记录的创作内容');
      return;
    }

    setAppending(true);
    setError(null);
    try {
      const appended = await creativeSessionApi.appendMessage(selectedSession.id, {
        role: draftRole,
        content,
        metadata: { source: 'creative-session-page' },
      });
      setSelectedSession(prev => prev ? { ...prev, messages: [...prev.messages, appended] } : prev);
      setDraftContent('');
      antdMessage.success('已写入会话记录');
    } catch (err) {
      console.error('写入创作会话失败:', err);
      setError('写入失败，请确认该会话仍可访问。');
    } finally {
      setAppending(false);
    }
  };

  const handleApplyQuickReply = async (reply: QuickReply) => {
    if (!selectedSession) {
      antdMessage.warning('请先创建或选择一个创作会话');
      return;
    }

    setApplyingQuickReplyId(reply.id);
    setError(null);
    try {
      const applied = await quickReplyApi.apply(reply.id, { session_id: selectedSession.id });
      setSelectedSession(prev => prev ? { ...prev, messages: [...prev.messages, applied.emitted_message] } : prev);
      antdMessage.success(`已写入快捷片段：${applied.trace_label}`);
    } catch (err) {
      console.error('应用快捷片段失败:', err);
      setError('快捷片段写入失败：仅支持已启用的安全片段。');
    } finally {
      setApplyingQuickReplyId(null);
    }
  };

  const handleSearch = async () => {
    if (!projectId) return;
    const query = searchQuery.trim();
    if (!query) {
      antdMessage.warning('请输入检索关键词');
      return;
    }

    setSearching(true);
    setError(null);
    try {
      const response = await creativeSessionApi.searchMessages(projectId, query);
      setSearchResults(response.items);
    } catch (err) {
      console.error('检索创作会话失败:', err);
      setError('检索失败，请确认项目权限或稍后重试。');
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="u-io72pt">
      <Space direction="vertical" size="middle" className="u-1ddf7dt">
        <Card>
          <Space align="start" className="u-1qos3j5" wrap>
            <Space direction="vertical" size={4}>
              <Space>
                <MessageOutlined className={sx({ color: token.colorPrimary, fontSize: 24 })} />
                <Title level={3} className="u-avalr8">创作会话</Title>
              </Space>
              <Paragraph type="secondary" className="u-1sezbee">
                按项目保存临时灵感、片段试写与讨论笔记；这里只沉淀工作台记录，不自动写入章节、记忆或世界观。
              </Paragraph>
            </Space>
            <Button icon={<ReloadOutlined />} onClick={loadSessions} loading={loadingSessions}>刷新</Button>
          </Space>
        </Card>

        {error && <Alert type="warning" showIcon message={error} />}

        <div
          className={sx({
            flex: 1,
            minHeight: 0,
            display: 'grid',
            gridTemplateColumns: 'minmax(260px, 320px) minmax(0, 1fr)',
            gap: token.paddingMD,
          })}
        >
          <Space direction="vertical" size="middle" className="u-17jj7fk">
            <Card size="small" title="新建会话">
              <Space.Compact className="u-1f3r3s">
                <Input
                  aria-label="会话标题"
                  value={sessionTitle}
                  onChange={event => setSessionTitle(event.target.value)}
                  onPressEnter={handleCreateSession}
                  placeholder="例如：雨夜开篇推演"
                  maxLength={200}
                />
                <Button type="primary" icon={<PlusOutlined />} onClick={handleCreateSession} loading={creating}>
                  创建
                </Button>
              </Space.Compact>
            </Card>

            <Card
              size="small"
              title="会话列表"
              className="u-1tqrzca"
              bodyStyle={{ height: 'calc(100% - 38px)', overflowY: 'auto', padding: token.paddingSM }}
            >
              <Spin spinning={loadingSessions}>
                {sessions.length === 0 ? (
                  <Empty description="暂无创作会话，先创建一个草稿房间" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                ) : (
                  <List
                    dataSource={sessions}
                    renderItem={item => (
                      <List.Item
                        key={item.id}
                        onClick={() => openSession(item.id)}
                        className={sx({
                          cursor: 'pointer',
                          borderRadius: token.borderRadius,
                          padding: token.paddingSM,
                          background: selectedSession?.id === item.id ? alphaColor(token.colorPrimary, 0.1) : undefined,
                        })}
                      >
                        <List.Item.Meta
                          title={<Text strong>{item.title}</Text>}
                          description={<Text type="secondary">更新于 {formatDate(item.updated_at)}</Text>}
                        />
                      </List.Item>
                    )}
                  />
                )}
              </Spin>
            </Card>
          </Space>

          <Space direction="vertical" size="middle" className="u-17jj7fk">
            <Card
              size="small"
              title={selectedSession ? `会话记录：${selectedSession.title}` : '会话记录'}
              className="u-1tqrzca"
              bodyStyle={{ height: 'calc(100% - 38px)', overflowY: 'auto' }}
            >
              <Spin spinning={loadingDetail}>
                {!selectedSession ? (
                  <Empty description="选择或创建会话后，在这里记录写作片段" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                ) : messages.length === 0 ? (
                  <Empty description="这个会话还没有记录，写下第一条创作笔记吧" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                ) : (
                  <Space direction="vertical" size="middle" className="u-1f3r3s">
                    {messages.map(item => (
                      <Card
                        key={item.id}
                        size="small"
                        className={sx({ borderColor: token.colorBorderSecondary })}
                        title={
                          <Space>
                            <Tag color={ROLE_COLORS[item.role] || 'default'}>{ROLE_LABELS[item.role] || item.role}</Tag>
                            <Text type="secondary">#{item.position + 1}</Text>
                          </Space>
                        }
                        extra={<Text type="secondary">{formatDate(item.created_at)}</Text>}
                      >
                        <Paragraph className="u-8lck0q">{item.content}</Paragraph>
                      </Card>
                    ))}
                  </Space>
                )}
              </Spin>
            </Card>

            <Card size="small" title="追加记录">
              <Space direction="vertical" className="u-1f3r3s">
                <Space.Compact className="u-1f3r3s">
                  <Select
                    aria-label="记录类型"
                    value={draftRole}
                    onChange={value => setDraftRole(value)}
                    options={[
                      { value: 'note', label: '写作笔记' },
                      { value: 'user', label: '创作想法' },
                      { value: 'assistant', label: '整理回应' },
                    ]}
                    className="u-1tmu4p8"
                  />
                  <Button
                    type="primary"
                    icon={<SendOutlined />}
                    onClick={handleAppendMessage}
                    loading={appending}
                    disabled={!selectedSession}
                  >
                    写入
                  </Button>
                </Space.Compact>
                <TextArea
                  aria-label="创作记录内容"
                  value={draftContent}
                  onChange={event => setDraftContent(event.target.value)}
                  placeholder="记录片段、开场钩子、人物动机或下一章推演……"
                  autoSize={{ minRows: 3, maxRows: 6 }}
                  disabled={!selectedSession}
                />
              </Space>
            </Card>

            <Card size="small" title={<Space><SnippetsOutlined />快捷片段</Space>}>
              <Space direction="vertical" className="u-1f3r3s">
                <Paragraph type="secondary" className="u-1sezbee">
                  仅将已启用的 safe_snippet 写入当前会话备注；不会执行脚本或暗改提示词。
                </Paragraph>
                <Space wrap>
                  <Button icon={<ReloadOutlined />} onClick={loadQuickReplies} loading={loadingQuickReplies}>加载快捷片段</Button>
                  {quickReplies.map(reply => (
                    <Button
                      key={reply.id}
                      onClick={() => handleApplyQuickReply(reply)}
                      disabled={!selectedSession}
                      loading={applyingQuickReplyId === reply.id}
                    >
                      {reply.label}
                    </Button>
                  ))}
                </Space>
                {quickReplies.length === 0 && !loadingQuickReplies && (
                  <Text type="secondary">暂无已加载片段，可在“快捷片段”页面创建后再加载。</Text>
                )}
              </Space>
            </Card>

            <Card
              size="small"
              title={<Space><FileSearchOutlined />会话检索</Space>}
              data-testid="creative-session-search-results"
            >
              <Space direction="vertical" className="u-1f3r3s">
                <Space.Compact className="u-1f3r3s">
                  <Input
                    aria-label="检索关键词"
                    value={searchQuery}
                    onChange={event => setSearchQuery(event.target.value)}
                    onPressEnter={handleSearch}
                    placeholder="搜索创作记录中的关键词"
                  />
                  <Button icon={<FileSearchOutlined />} onClick={handleSearch} loading={searching}>搜索</Button>
                </Space.Compact>
                {searchResults.length === 0 ? (
                  <Empty description="暂无检索结果" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                ) : (
                  <List
                    size="small"
                    dataSource={searchResults}
                    renderItem={item => (
                      <List.Item key={item.message_id}>
                        <List.Item.Meta
                          title={<Space><Text strong>{item.session_title}</Text><Tag>{ROLE_LABELS[item.role] || item.role}</Tag></Space>}
                          description={<Text>{item.content}</Text>}
                        />
                      </List.Item>
                    )}
                  />
                )}
              </Space>
            </Card>
          </Space>
        </div>
      </Space>
    </div>
  );
}
