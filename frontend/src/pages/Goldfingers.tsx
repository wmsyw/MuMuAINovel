import { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Card, Descriptions, Drawer, Space, Statistic, Tabs, Tag, Typography, message, theme } from 'antd';
import { PlusOutlined, ReloadOutlined, ThunderboltOutlined, UploadOutlined } from '@ant-design/icons';
import { useParams } from 'react-router-dom';
import type { Character, Goldfinger, GoldfingerCreate, GoldfingerHistoryEvent, GoldfingerUpdate } from '../types';
import { characterApi, goldfingerApi } from '../services/api';
import { useStore } from '../store';
import GoldfingerEditor from '../components/goldfingers/GoldfingerEditor';
import GoldfingerHistoryDrawer from '../components/goldfingers/GoldfingerHistoryDrawer';
import GoldfingerImportExportModal from '../components/goldfingers/GoldfingerImportExportModal';
import GoldfingerList from '../components/goldfingers/GoldfingerList';
import GoldfingerPendingReviewPanel from '../components/goldfingers/GoldfingerPendingReviewPanel';
import { formatConfidence, getGoldfingerStatusMeta, stringifyGoldfingerValue } from '../components/goldfingers/constants';

const { Title, Paragraph, Text } = Typography;

const detailFields: Array<[keyof Goldfinger, string]> = [
  ['rules', '规则'],
  ['tasks', '任务'],
  ['rewards', '奖励'],
  ['limits', '限制'],
  ['trigger_conditions', '触发条件'],
  ['cooldown', '冷却'],
  ['aliases', '别名'],
  ['metadata', '元数据'],
];

export default function Goldfingers() {
  const { projectId } = useParams<{ projectId: string }>();
  const { currentProject, characters: storeCharacters } = useStore();
  const { token } = theme.useToken();

  const [goldfingers, setGoldfingers] = useState<Goldfinger[]>([]);
  const [characters, setCharacters] = useState<Pick<Character, 'id' | 'name'>[]>(storeCharacters);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<Goldfinger | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editorMode, setEditorMode] = useState<'create' | 'edit'>('create');
  const [saving, setSaving] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyGoldfinger, setHistoryGoldfinger] = useState<Goldfinger | null>(null);
  const [history, setHistory] = useState<GoldfingerHistoryEvent[]>([]);
  const [importOpen, setImportOpen] = useState(false);

  const stats = useMemo(() => {
    const active = goldfingers.filter(item => item.status === 'active').length;
    const manual = goldfingers.filter(item => item.source === 'manual').length;
    const synced = goldfingers.length - manual;
    return { total: goldfingers.length, active, manual, synced };
  }, [goldfingers]);

  const loadGoldfingers = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const response = await goldfingerApi.listGoldfingers(projectId);
      setGoldfingers(response.items || []);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  const loadCharacters = useCallback(async () => {
    if (!projectId) return;
    if (storeCharacters.length > 0) {
      setCharacters(storeCharacters);
      return;
    }
    try {
      const items = await characterApi.getCharacters(projectId);
      setCharacters(items.map(character => ({ id: character.id, name: character.name })));
    } catch {
      setCharacters([]);
    }
  }, [projectId, storeCharacters]);

  useEffect(() => {
    loadGoldfingers();
    loadCharacters();
  }, [loadCharacters, loadGoldfingers]);

  useEffect(() => {
    if (storeCharacters.length > 0) setCharacters(storeCharacters);
  }, [storeCharacters]);

  const openCreate = () => {
    setSelected(null);
    setEditorMode('create');
    setEditorOpen(true);
  };

  const openEdit = (goldfinger: Goldfinger) => {
    setSelected(goldfinger);
    setEditorMode('edit');
    setEditorOpen(true);
  };

  const handleSubmit = async (payload: GoldfingerCreate | GoldfingerUpdate) => {
    if (!projectId) return;
    setSaving(true);
    try {
      if (editorMode === 'create') {
        await goldfingerApi.createGoldfinger(projectId, payload as GoldfingerCreate);
        message.success('金手指已创建');
      } else if (selected) {
        await goldfingerApi.updateGoldfinger(selected.id, payload as GoldfingerUpdate);
        message.success('金手指已更新');
      }
      setEditorOpen(false);
      await loadGoldfingers();
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (goldfinger: Goldfinger) => {
    await goldfingerApi.deleteGoldfinger(goldfinger.id);
    message.success(`已删除「${goldfinger.name}」`);
    if (selected?.id === goldfinger.id) {
      setSelected(null);
      setDetailOpen(false);
    }
    await loadGoldfingers();
  };

  const openDetail = async (goldfinger: Goldfinger) => {
    setSelected(goldfinger);
    setDetailOpen(true);
    try {
      const detail = await goldfingerApi.getGoldfinger(goldfinger.id);
      setSelected(detail);
    } catch {
      // 列表数据已足够展示，详情刷新失败由全局拦截器提示。
    }
  };

  const loadHistory = async (goldfinger: Goldfinger) => {
    setHistoryGoldfinger(goldfinger);
    setHistoryLoading(true);
    try {
      const response = await goldfingerApi.getHistory(goldfinger.id);
      setHistory(response.items || []);
    } finally {
      setHistoryLoading(false);
    }
  };

  const openHistory = async (goldfinger: Goldfinger) => {
    setHistoryOpen(true);
    await loadHistory(goldfinger);
  };

  const selectedStatus = selected ? getGoldfingerStatusMeta(selected.status) : null;

  return (
    <div style={{ height: '100%', overflow: 'auto', paddingRight: 4 }}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Card>
          <Space align="start" style={{ width: '100%', justifyContent: 'space-between' }} wrap>
            <Space direction="vertical" size={4}>
              <Space>
                <ThunderboltOutlined style={{ color: token.colorWarning, fontSize: 24 }} />
                <Title level={3} style={{ margin: 0 }}>金手指管理</Title>
              </Space>
              <Paragraph type="secondary" style={{ marginBottom: 0 }}>
                独立维护项目中的系统、神器、血脉、外挂能力等金手指设定，并审核正文同步产生的候选变更。
              </Paragraph>
            </Space>
            <Space wrap>
              <Button icon={<ReloadOutlined />} onClick={loadGoldfingers} loading={loading}>刷新</Button>
              <Button icon={<UploadOutlined />} onClick={() => setImportOpen(true)}>导入 / 导出</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建金手指</Button>
            </Space>
          </Space>
        </Card>

        <Space wrap size="middle">
          <Card><Statistic title="金手指总数" value={stats.total} /></Card>
          <Card><Statistic title="激活中" value={stats.active} /></Card>
          <Card><Statistic title="手动维护" value={stats.manual} /></Card>
          <Card><Statistic title="同步导入" value={stats.synced} /></Card>
        </Space>

        <Tabs
          items={[
            {
              key: 'list',
              label: '档案列表',
              children: (
                <GoldfingerList
                  goldfingers={goldfingers}
                  loading={loading}
                  selectedId={selected?.id}
                  onSelect={openDetail}
                  onEdit={openEdit}
                  onDelete={handleDelete}
                  onHistory={openHistory}
                />
              ),
            },
            {
              key: 'pending-review',
              label: '待审核同步',
              children: projectId ? <GoldfingerPendingReviewPanel projectId={projectId} onReviewed={loadGoldfingers} /> : null,
            },
          ]}
        />
      </Space>

      <GoldfingerEditor
        open={editorOpen}
        mode={editorMode}
        goldfinger={editorMode === 'edit' ? selected : null}
        characters={characters}
        confirmLoading={saving}
        onCancel={() => setEditorOpen(false)}
        onSubmit={handleSubmit}
      />

      <GoldfingerHistoryDrawer
        open={historyOpen}
        goldfinger={historyGoldfinger}
        history={history}
        loading={historyLoading}
        onClose={() => setHistoryOpen(false)}
        onReload={() => historyGoldfinger && loadHistory(historyGoldfinger)}
      />

      <GoldfingerImportExportModal
        open={importOpen}
        projectId={projectId}
        projectTitle={currentProject?.title}
        onCancel={() => setImportOpen(false)}
        onImported={loadGoldfingers}
      />

      <Drawer
        title={selected ? `金手指详情：${selected.name}` : '金手指详情'}
        open={detailOpen}
        width={760}
        onClose={() => setDetailOpen(false)}
        extra={selected && <Button type="primary" onClick={() => openEdit(selected)}>编辑</Button>}
      >
        {selected && (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Descriptions bordered column={1} size="small">
              <Descriptions.Item label="名称">{selected.name}</Descriptions.Item>
              <Descriptions.Item label="规范名">{selected.normalized_name || '—'}</Descriptions.Item>
              <Descriptions.Item label="状态">{selectedStatus && <Tag color={selectedStatus.color}>{selectedStatus.label}</Tag>}</Descriptions.Item>
              <Descriptions.Item label="类型">{selected.type || '未分类'}</Descriptions.Item>
              <Descriptions.Item label="拥有者">{selected.owner_character_name || selected.owner_character_id || '未指定'}</Descriptions.Item>
              <Descriptions.Item label="来源">{selected.source || 'manual'}</Descriptions.Item>
              <Descriptions.Item label="置信度">{formatConfidence(selected.confidence)}</Descriptions.Item>
              <Descriptions.Item label="最后来源章节">{selected.last_source_chapter_id || '—'}</Descriptions.Item>
            </Descriptions>
            <Card size="small" title="概要">
              <Paragraph style={{ marginBottom: 0 }}>{selected.summary || '暂无概要'}</Paragraph>
            </Card>
            {detailFields.map(([field, label]) => (
              <Card size="small" title={label} key={field}>
                <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontFamily: 'inherit' }}>
                  {stringifyGoldfingerValue(selected[field])}
                </pre>
              </Card>
            ))}
            <Text type="secondary">创建：{selected.created_at || '—'} 更新：{selected.updated_at || '—'}</Text>
          </Space>
        )}
      </Drawer>
    </div>
  );
}
