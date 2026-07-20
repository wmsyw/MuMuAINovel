import { useState, useMemo } from 'react';
import { Drawer, Input, List, Typography, Empty, Tag, theme } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import type { Chapter } from '../../types';
import { sx } from '../../styles/sx';

const { Link } = Typography;

interface GroupedChapters {
  outlineId: string | null;
  outlineTitle: string;
  chapters: Chapter[];
}

interface FloatingIndexPanelProps {
  visible: boolean;
  onClose: () => void;
  groupedChapters: GroupedChapters[];
  onChapterSelect: (chapterId: string) => void;
}

export default function FloatingIndexPanel({
  visible,
  onClose,
  groupedChapters,
  onChapterSelect,
}: FloatingIndexPanelProps) {
  const { token } = theme.useToken();
  const [searchTerm, setSearchTerm] = useState('');

  const filteredGroups = useMemo(() => {
    if (!searchTerm) {
      return groupedChapters;
    }
    return groupedChapters
      .map(group => {
        const filteredChapters = group.chapters.filter(chapter =>
          chapter.title.toLowerCase().includes(searchTerm.toLowerCase())
        );
        return { ...group, chapters: filteredChapters };
      })
      .filter(group => group.chapters.length > 0);
  }, [searchTerm, groupedChapters]);

  const handleChapterClick = (chapterId: string) => {
    onChapterSelect(chapterId);
    onClose();
  };

  return (
    <Drawer
      title="章节目录"
      placement="right"
      onClose={onClose}
      open={visible}
      width={320}
      styles={{
        body: { padding: 0 },
      }}
    >
      <div className={sx({ padding: '16px', borderBottom: `1px solid ${token.colorBorderSecondary}` })}>
        <Input
          placeholder="搜索章节标题"
          prefix={<SearchOutlined />}
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          allowClear
        />
      </div>

      {filteredGroups.length > 0 ? (
        <List
          dataSource={filteredGroups}
          renderItem={group => (
            <List.Item className="u-16uug4z">
              <div className="u-1yggm7h">
                <Tag color={group.outlineId ? 'blue' : 'default'}>
                  {group.outlineTitle}
                </Tag>
              </div>
              <List
                size="small"
                dataSource={group.chapters}
                renderItem={chapter => (
                  <List.Item className="u-92vjxl">
                    <Link onClick={() => handleChapterClick(chapter.id)}>
                      {`第${chapter.chapter_number}章: ${chapter.title}`}
                    </Link>
                  </List.Item>
                )}
                split={false}
              />
            </List.Item>
          )}
          className="u-1uvallh"
        />
      ) : (
        <Empty description="没有找到匹配的章节" className="u-1oa24s4" />
      )}
    </Drawer>
  );
}
