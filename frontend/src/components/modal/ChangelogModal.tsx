import { Modal, Timeline, Tag, Avatar, Empty, Spin, Button, Space } from 'antd';
import { useState, useEffect } from 'react';
import {
  BugOutlined,
  StarOutlined,
  FileTextOutlined,
  BgColorsOutlined,
  ThunderboltOutlined,
  ExperimentOutlined,
  ToolOutlined,
  QuestionCircleOutlined,
  GithubOutlined,
  ReloadOutlined,
  ClockCircleOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import {
  fetchChangelog,
  groupChangelogByDate,
  cacheChangelog,
  clearChangelogCache,
  type ChangelogEntry,
} from '../../services/changelogService';
import { sx } from '../../styles/sx';

interface ChangelogModalProps {
  visible: boolean;
  onClose: () => void;
}

// 提交类型图标和颜色配置
const typeConfig: Record<ChangelogEntry['type'], { icon: React.ReactNode; color: string; label: string }> = {
  feature: { icon: <StarOutlined />, color: 'green', label: '新功能' },
  update: { icon: <SyncOutlined />, color: 'geekblue', label: '更新' },
  fix: { icon: <BugOutlined />, color: 'red', label: '修复' },
  docs: { icon: <FileTextOutlined />, color: 'blue', label: '文档' },
  style: { icon: <BgColorsOutlined />, color: 'purple', label: '样式' },
  refactor: { icon: <ThunderboltOutlined />, color: 'orange', label: '重构' },
  perf: { icon: <ThunderboltOutlined />, color: 'gold', label: '性能' },
  test: { icon: <ExperimentOutlined />, color: 'cyan', label: '测试' },
  chore: { icon: <ToolOutlined />, color: 'default', label: '杂项' },
  other: { icon: <QuestionCircleOutlined />, color: 'default', label: '其他' },
};

export default function ChangelogModal({ visible, onClose }: ChangelogModalProps) {
  const [changelog, setChangelog] = useState<ChangelogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);

  // 加载更新日志
  // 每次用户打开窗口时才同步获取最新数据，不自动刷新
  const loadChangelog = async (pageNum: number = 1, append: boolean = false) => {
    setLoading(true);
    setError(null);

    try {
      // 每次打开都从网络获取最新数据
      const entries = await fetchChangelog(pageNum, 30);

      if (entries.length === 0) {
        setHasMore(false);
      } else {
        if (append) {
          setChangelog(prev => [...prev, ...entries]);
        } else {
          setChangelog(entries);
          // 缓存第一页数据（用于分页加载时的数据持久化）
          if (pageNum === 1) {
            cacheChangelog(entries);
          }
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '获取更新日志失败');
    } finally {
      setLoading(false);
    }
  };

  // 初始加载
  useEffect(() => {
    if (visible) {
      loadChangelog(1, false);
      setPage(1);
      setHasMore(true);
    }
  }, [visible]);

  // 加载更多
  const handleLoadMore = () => {
    const nextPage = page + 1;
    setPage(nextPage);
    loadChangelog(nextPage, true);
  };

  // 刷新（清除缓存并重新加载）
  const handleRefresh = () => {
    clearChangelogCache();
    setPage(1);
    setHasMore(true);
    loadChangelog(1, false);
  };

  // 按日期分组
  const groupedChangelog = groupChangelogByDate(changelog);
  const sortedDates = Array.from(groupedChangelog.keys()).sort((a, b) => b.localeCompare(a));

  // 格式化日期
  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return '今天';
    if (diffDays === 1) return '昨天';
    if (diffDays < 7) return `${diffDays} 天前`;

    return date.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' });
  };

  // 格式化时间
  const formatTime = (dateStr: string) => {
    return new Date(dateStr).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <Modal
      title={
        <Space>
          <GithubOutlined />
          <span>更新日志</span>
          <Button
            type="text"
            size="small"
            icon={<ReloadOutlined />}
            onClick={handleRefresh}
            loading={loading}
            title="刷新"
          />
        </Space>
      }
      open={visible}
      onCancel={onClose}
      footer={null}
      width={800}
      centered
      styles={{
        body: {
          maxHeight: '70vh',
          overflowY: 'auto',
          padding: '24px',
        },
      }}
    >
      {error && (
        <div className="u-1u2ziqe">
          {error}
        </div>
      )}

      {loading && changelog.length === 0 ? (
        <div className="u-xyu2f7">
          <Spin size="large" tip="加载更新日志中..." />
        </div>
      ) : changelog.length === 0 ? (
        <Empty description="暂无更新日志" />
      ) : (
        <>
          {sortedDates.map(date => {
            const entries = groupedChangelog.get(date) || [];

            return (
              <div key={date} className="u-yplvzz">
                <div className="u-19serfh">
                  <ClockCircleOutlined className="u-1vcwmpp" />
                  {formatDate(date)}
                </div>

                <Timeline>
                  {entries.map(entry => {
                    const config = typeConfig[entry.type] || typeConfig.other;

                    return (
                      <Timeline.Item
                        key={entry.id}
                        dot={
                          <div className={sx({
                            width: '24px',
                            height: '24px',
                            borderRadius: '50%',
                            background: 'var(--color-bg-container)',
                            border: `2px solid ${config.color === 'default' ? 'var(--color-border)' : config.color}`,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontSize: '12px',
                          })}>
                            {config.icon}
                          </div>
                        }
                      >
                        <div className="u-12ggiv4">
                          <Space size="small" wrap>
                            <Tag color={config.color} icon={config.icon}>
                              {config.label}
                            </Tag>
                            {entry.scope && (
                              <Tag color="blue">{entry.scope}</Tag>
                            )}
                            <span className="u-1f4syj3">
                              {formatTime(entry.date)}
                            </span>
                          </Space>

                          <div className="u-h4u2wc">
                            {entry.message}
                          </div>

                          <Space size="small" className="u-u35y5u">
                            {entry.author.avatar && (
                              <Avatar size="small" src={entry.author.avatar} />
                            )}
                            <span className="u-12wdqqg">
                              {entry.author.username || entry.author.name}
                            </span>
                            <a
                              href={entry.commitUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="u-1pw6xki"
                            >
                              查看提交
                            </a>
                          </Space>
                        </div>
                      </Timeline.Item>
                    );
                  })}
                </Timeline>
              </div>
            );
          })}

          {
            hasMore && (
              <div className="u-hpsvta">
                <Button
                  type="default"
                  onClick={handleLoadMore}
                  loading={loading}
                >
                  加载更多
                </Button>
              </div>
            )
          }

          {
            !hasMore && changelog.length > 0 && (
              <div className="u-k3kv3j">
                已显示所有更新日志
              </div>
            )
          }
        </>
      )}

      <div className="u-1yfyau8">
        💡 提示：每次打开窗口时自动获取最新更新日志，数据来源于 GitHub 提交历史
      </div>
    </Modal >
  );
}
