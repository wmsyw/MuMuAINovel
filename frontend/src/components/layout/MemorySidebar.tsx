import React, { useMemo, useEffect, useRef } from 'react';
import { Card, Tag, Badge, Empty, Collapse, Divider, theme } from 'antd';
import {
  FireOutlined,
  StarOutlined,
  ThunderboltOutlined,
  UserOutlined,
} from '@ant-design/icons';
import type { MemoryAnnotation } from '../common/AnnotatedText';
import { sx } from '../../styles/sx';

const { Panel } = Collapse;

interface MemorySidebarProps {
  annotations: MemoryAnnotation[];
  activeAnnotationId?: string;
  onAnnotationClick?: (annotation: MemoryAnnotation) => void;
  scrollToAnnotation?: string;
}

// 类型配置
const TYPE_CONFIG = {
  hook: {
    label: '钩子',
    icon: <FireOutlined />,
  },
  foreshadow: {
    label: '伏笔',
    icon: <StarOutlined />,
  },
  plot_point: {
    label: '情节点',
    icon: <ThunderboltOutlined />,
  },
  character_event: {
    label: '角色事件',
    icon: <UserOutlined />,
  },
};

/**
 * 记忆侧边栏组件
 * 展示章节的所有记忆标注
 */
const MemorySidebar: React.FC<MemorySidebarProps> = ({
  annotations,
  activeAnnotationId,
  onAnnotationClick,
  scrollToAnnotation,
}) => {
  const { token } = theme.useToken();
  const cardRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const typeColors: Record<keyof typeof TYPE_CONFIG, string> = {
    hook: token.colorError,
    foreshadow: token.colorInfo,
    plot_point: token.colorSuccess,
    character_event: token.colorWarning,
  };

  // 当需要滚动到特定标注卡片时
  useEffect(() => {
    if (scrollToAnnotation && cardRefs.current[scrollToAnnotation]) {
      const element = cardRefs.current[scrollToAnnotation];
      element?.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      });
    }
  }, [scrollToAnnotation]);
  // 按类型分组
  const groupedAnnotations = useMemo(() => {
    const groups: Record<string, MemoryAnnotation[]> = {
      hook: [],
      foreshadow: [],
      plot_point: [],
      character_event: [],
    };

    annotations.forEach((annotation) => {
      if (groups[annotation.type]) {
        groups[annotation.type].push(annotation);
      }
    });

    // 每组按重要性排序
    Object.keys(groups).forEach((type) => {
      groups[type].sort((a, b) => b.importance - a.importance);
    });

    return groups;
  }, [annotations]);

  // 统计信息
  const stats = useMemo(() => {
    return {
      total: annotations.length,
      hooks: groupedAnnotations.hook.length,
      foreshadows: groupedAnnotations.foreshadow.length,
      plotPoints: groupedAnnotations.plot_point.length,
      characterEvents: groupedAnnotations.character_event.length,
    };
  }, [annotations, groupedAnnotations]);

  // 渲染单个记忆卡片
  const renderMemoryCard = (annotation: MemoryAnnotation) => {
    const config = TYPE_CONFIG[annotation.type];
    const color = typeColors[annotation.type];
    const isActive = activeAnnotationId === annotation.id;

    return (
      <div
        key={annotation.id}
        ref={(el) => {
          cardRefs.current[annotation.id] = el;
        }}
      >
        <Card
          size="small"
          hoverable
          onClick={() => onAnnotationClick?.(annotation)}
          className={sx({
            marginBottom: 12,
            borderLeft: `4px solid ${color}`,
            backgroundColor: isActive ? `color-mix(in srgb, ${color} 8%, transparent)` : 'transparent',
            cursor: 'pointer',
            transition: 'all 0.2s',
          })}
          bodyStyle={{ padding: 12 }}
        >
        <div className="u-1jeouum">
          <Badge
            count={`${(annotation.importance * 10).toFixed(1)}`}
            className={sx({
              backgroundColor: color,
              float: 'right',
            })}
          />
          <div className="u-16li5vt">
            {config.icon} {annotation.title}
          </div>
        </div>

        <div
          className={sx({
            fontSize: 13,
            color: token.colorTextSecondary,
            lineHeight: 1.6,
            marginBottom: 8,
          })}
        >
          {annotation.content.length > 100
            ? `${annotation.content.slice(0, 100)}...`
            : annotation.content}
        </div>

        {annotation.tags && annotation.tags.length > 0 && (
          <div>
            {annotation.tags.map((tag, index) => (
              <Tag key={index} className="u-1wqmcpx">
                {tag}
              </Tag>
            ))}
          </div>
        )}

        {/* 特殊元数据 */}
        {annotation.metadata.strength && (
          <div className={sx({ marginTop: 4, fontSize: 11, color: token.colorTextTertiary })}>
            强度: {annotation.metadata.strength}/10
          </div>
        )}
        {annotation.metadata.foreshadowType && (
          <Tag
            color={annotation.metadata.foreshadowType === 'planted' ? 'blue' : 'green'}
            className="u-vataou"
          >
            {annotation.metadata.foreshadowType === 'planted' ? '已埋下' : '已回收'}
          </Tag>
        )}
        </Card>
      </div>
    );
  };

  if (annotations.length === 0) {
    return (
      <div className="u-1lb6cvx">
        <Empty description="暂无分析数据" />
      </div>
    );
  }

  return (
    <div className="u-jgk8qc">
      {/* 统计概览 */}
      <Card size="small" className="u-6srbul">
        <div className="u-1y1vc8n">📊 分析概览</div>
        <div className="u-1apgu3n">
          <div>
            <div className={sx({ fontSize: 12, color: token.colorTextTertiary })}>钩子</div>
            <div className={sx({ fontSize: 20, fontWeight: 600, color: typeColors.hook })}>
              {stats.hooks}
            </div>
          </div>
          <div>
            <div className={sx({ fontSize: 12, color: token.colorTextTertiary })}>伏笔</div>
            <div className={sx({ fontSize: 20, fontWeight: 600, color: typeColors.foreshadow })}>
              {stats.foreshadows}
            </div>
          </div>
          <div>
            <div className={sx({ fontSize: 12, color: token.colorTextTertiary })}>情节点</div>
            <div className={sx({ fontSize: 20, fontWeight: 600, color: typeColors.plot_point })}>
              {stats.plotPoints}
            </div>
          </div>
          <div>
            <div className={sx({ fontSize: 12, color: token.colorTextTertiary })}>角色事件</div>
            <div
              className={sx({ fontSize: 20, fontWeight: 600, color: typeColors.character_event })}
            >
              {stats.characterEvents}
            </div>
          </div>
        </div>
      </Card>

      <Divider className="u-1ys5lhf" />

      {/* 分类展示 */}
      <Collapse defaultActiveKey={['hook', 'foreshadow', 'plot_point']} ghost>
        {Object.entries(groupedAnnotations).map(([type, items]) => {
          if (items.length === 0) return null;

          const config = TYPE_CONFIG[type as keyof typeof TYPE_CONFIG];

          return (
            <Panel
              key={type}
              header={
                <span className="u-63i2du">
                  {config.icon} {config.label} ({items.length})
                </span>
              }
            >
              {items.map((annotation) => renderMemoryCard(annotation))}
            </Panel>
          );
        })}
      </Collapse>
    </div>
  );
};

export default MemorySidebar;
