import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Alert, Card, Descriptions, Drawer, Empty, Progress, Table, Tag, Button, Space, message, Modal, Form, Select, Slider, Input, Tabs, AutoComplete, Typography, theme } from 'antd';
import { PlusOutlined, ApartmentOutlined, UserOutlined, EditOutlined, FileSearchOutlined, HistoryOutlined } from '@ant-design/icons';
import { useStore } from '../store';
import { isOrganizationEntity, type LegacyOrganizationCharacterFields } from '../utils/entityCompatibility';
import GoldfingerPendingReviewPanel from '../components/goldfingers/GoldfingerPendingReviewPanel';
import { characterApi, relationshipApi } from '../services/api';
import type { Character as CharacterContract, Relationship, RelationshipHistoryEvent, RelationshipProvenance, RelationshipType } from '../types';

const { TextArea } = Input;
const { Paragraph, Text } = Typography;

type Character = Pick<CharacterContract, 'id' | 'name'> & LegacyOrganizationCharacterFields;

const formatConfidence = (confidence?: number | null) => {
  if (confidence === null || confidence === undefined) return '未记录';
  return `${Math.round(Math.max(0, Math.min(1, confidence)) * 100)}%`;
};

const formatSourceChapter = (relationship?: Pick<Relationship, 'source_chapter_number' | 'source_chapter_order' | 'source_chapter_id'> | null) => {
  if (!relationship) return '未记录来源章节';
  if (relationship.source_chapter_number !== null && relationship.source_chapter_number !== undefined) {
    return `第 ${relationship.source_chapter_number} 章`;
  }
  if (relationship.source_chapter_order !== null && relationship.source_chapter_order !== undefined) {
    return `章节顺序 ${relationship.source_chapter_order}`;
  }
  if (relationship.source_chapter_id) return `章节 ${relationship.source_chapter_id}`;
  return '未记录来源章节';
};

const formatDateTime = (value?: string | null) => {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false });
};

export default function Relationships() {
  const { projectId } = useParams<{ projectId: string }>();
  const { currentProject } = useStore();
  const navigate = useNavigate();
  const [relationships, setRelationships] = useState<Relationship[]>([]);
  const [relationshipTypes, setRelationshipTypes] = useState<RelationshipType[]>([]);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [loading, setLoading] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isEditMode, setIsEditMode] = useState(false);
  const [editingRelationship, setEditingRelationship] = useState<Relationship | null>(null);
  const [evidenceRelationship, setEvidenceRelationship] = useState<Relationship | null>(null);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [form] = Form.useForm();
  const [modal, contextHolder] = Modal.useModal();
  const { token } = theme.useToken();
  const [isMobile, setIsMobile] = useState(window.innerWidth <= 768);
  const [pageSize, setPageSize] = useState(10);
  const [currentPage, setCurrentPage] = useState(1);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth <= 768);
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  useEffect(() => {
    if (projectId) {
      loadData();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const loadData = async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const [relsRes, typesRes, charsRes] = await Promise.all([
        relationshipApi.getProjectRelationships(projectId),
        relationshipApi.getRelationshipTypes(),
        characterApi.getCharacters(projectId)
      ]);

      setRelationships(relsRes);
      setRelationshipTypes(typesRes);
      setCharacters(charsRes || []);
    } catch (error) {
      message.error('加载数据失败');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateRelationship = async (values: {
    character_from_id: string;
    character_to_id: string;
    relationship_name: string;
    intimacy_level: number;
    status: string;
    description?: string;
  }) => {
    if (!projectId) return;
    try {
      await relationshipApi.createRelationship({
        project_id: projectId,
        ...values
      });
      message.success('关系创建成功');
      setIsModalOpen(false);
      form.resetFields();
      loadData();
    } catch (error) {
      message.error('创建关系失败');
      console.error(error);
    }
  };

  const handleEditRelationship = (record: Relationship) => {
    setEditingRelationship(record);
    setIsEditMode(true);
    form.setFieldsValue({
      character_from_id: record.character_from_id,
      character_to_id: record.character_to_id,
      relationship_name: record.relationship_name,
      intimacy_level: record.intimacy_level,
      status: record.status,
      description: record.description,
    });
    setIsModalOpen(true);
  };

  const handleUpdateRelationship = async (values: {
    character_from_id: string;
    character_to_id: string;
    relationship_name: string;
    intimacy_level: number;
    status: string;
    description?: string;
  }) => {
    if (!editingRelationship) return;

    try {
      await relationshipApi.updateRelationship(editingRelationship.id, {
        relationship_name: values.relationship_name,
        intimacy_level: values.intimacy_level,
        status: values.status,
        description: values.description,
      });
      message.success('关系更新成功');
      setIsModalOpen(false);
      setIsEditMode(false);
      setEditingRelationship(null);
      form.resetFields();
      loadData();
    } catch (error) {
      message.error('更新关系失败');
      console.error(error);
    }
  };

  const handleDeleteRelationship = async (id: string) => {
    modal.confirm({
      title: '确认删除',
      content: '确定要删除这条关系吗？',
      centered: true,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await relationshipApi.deleteRelationship(id);
          message.success('关系删除成功');
          loadData();
        } catch (error) {
          message.error('删除失败');
          console.error(error);
        }
      }
    });
  };

  const openEvidenceDrawer = (record: Relationship) => {
    setEvidenceRelationship(record);
    setEvidenceOpen(true);
  };

  const renderEvidenceExcerpt = (evidence?: string | null, rows = 2) => (
    <Paragraph style={{ marginBottom: 0 }} ellipsis={evidence ? { rows, tooltip: evidence } : false}>
      {evidence || '暂无证据摘录'}
    </Paragraph>
  );

  const renderProvenanceCard = (item: RelationshipProvenance) => (
    <Card key={item.id} size="small" style={{ borderColor: token.colorBorderSecondary }}>
      <Space direction="vertical" size="small" style={{ width: '100%' }}>
        <Space wrap>
          <Tag color="geekblue">{item.source_type}</Tag>
          {item.claim_type && <Tag>{item.claim_type}</Tag>}
          {item.chapter_id && <Tag color="cyan">章节 {item.chapter_id}</Tag>}
          <Text type="secondary">置信度：{formatConfidence(item.confidence)}</Text>
          <Text type="secondary">{formatDateTime(item.created_at)}</Text>
        </Space>
        <Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
          {item.evidence_text || '暂无证据原文'}
        </Paragraph>
      </Space>
    </Card>
  );

  const renderHistoryCard = (item: RelationshipHistoryEvent) => (
    <Card key={item.id} size="small" style={{ borderColor: token.colorBorderSecondary }}>
      <Space direction="vertical" size="small" style={{ width: '100%' }}>
        <Space wrap>
          <Tag color={item.event_status === 'active' ? 'success' : item.event_status === 'ended' ? 'default' : 'processing'}>
            {item.event_status}
          </Tag>
          <Text strong>{item.relationship_name || '关系事件'}</Text>
          <Tag color="cyan">{formatSourceChapter({ source_chapter_id: item.source_chapter_id, source_chapter_order: item.source_chapter_order })}</Tag>
          <Text type="secondary">置信度：{formatConfidence(item.confidence)}</Text>
          {item.supersedes_event_id && <Tag color="orange">替换 {item.supersedes_event_id}</Tag>}
        </Space>
        {item.story_time_label && <Text type="secondary">故事时间：{item.story_time_label}</Text>}
        <Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
          {item.evidence_text || '暂无证据原文'}
        </Paragraph>
      </Space>
    </Card>
  );

  const getCharacterName = (id: string) => {
    const char = characters.find(c => c.id === id);
    return char?.name || '未知';
  };

  const getIntimacyColor = (level: number) => {
    if (level >= 75) return 'green';
    if (level >= 50) return 'blue';
    if (level >= 25) return 'orange';
    if (level >= 0) return 'volcano';
    return 'red';
  };

  const getStatusColor = (status: string) => {
    const colors: Record<string, string> = {
      active: 'green',
      broken: 'red',
      past: 'default',
      complicated: 'orange'
    };
    return colors[status] || 'default';
  };

  const getCategoryColor = (category: string) => {
    const colors: Record<string, string> = {
      family: 'magenta',
      social: 'blue',
      hostile: 'red',
      professional: 'cyan'
    };
    return colors[category] || 'default';
  };

  const columns = [
    {
      title: '角色A',
      dataIndex: 'character_from_id',
      key: 'from',
      render: (id: string) => (
        <Tag icon={<UserOutlined />} color="blue">
          {getCharacterName(id)}
        </Tag>
      ),
      width: 120,
    },
    {
      title: '关系',
      dataIndex: 'relationship_name',
      key: 'relationship',
      render: (name: string, record: Relationship) => (
        <Space direction="vertical" size={2}>
          <Space wrap size={4}>
            <Text strong>{name || '未知关系'}</Text>
            {Boolean(record.pending_candidate_count) && <Tag color="orange">待审 {record.pending_candidate_count}</Tag>}
          </Space>
          {record.description && <Text type="secondary" ellipsis style={{ maxWidth: 180 }}>{record.description}</Text>}
        </Space>
      ),
      width: 180,
    },
    {
      title: '角色B',
      dataIndex: 'character_to_id',
      key: 'to',
      render: (id: string) => (
        <Tag icon={<UserOutlined />} color="purple">
          {getCharacterName(id)}
        </Tag>
      ),
      width: 120,
    },
    {
      title: '亲密度',
      dataIndex: 'intimacy_level',
      key: 'intimacy',
      render: (level: number) => (
        <Tag color={getIntimacyColor(level)}>{level}</Tag>
      ),
      width: 80,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Tag color={getStatusColor(status)}>{status}</Tag>
      ),
      width: 80,
    },
    {
      title: '来源',
      dataIndex: 'source',
      key: 'source',
      render: (source: string, record: Relationship) => (
        <Space direction="vertical" size={2}>
          <Tag>{source === 'ai' ? 'AI生成' : source === 'manual' ? '手动创建' : source || '未知'}</Tag>
          <Text type="secondary" style={{ fontSize: token.fontSizeSM }}>{formatSourceChapter(record)}</Text>
        </Space>
      ),
      width: 150,
    },
    {
      title: '证据 / 置信度',
      key: 'provenance',
      render: (_: unknown, record: Relationship) => (
        <Space direction="vertical" size={4} style={{ width: '100%' }}>
          <Space wrap size={6}>
            <Tag color={record.evidence_text ? 'cyan' : 'default'}>证据 {record.evidence_text ? '已记录' : '未记录'}</Tag>
            <Text type="secondary">{formatConfidence(record.confidence)}</Text>
          </Space>
          {record.confidence !== null && record.confidence !== undefined && (
            <Progress percent={Math.round(Math.max(0, Math.min(1, record.confidence)) * 100)} size="small" showInfo={false} strokeColor={record.confidence >= 0.8 ? token.colorSuccess : token.colorWarning} />
          )}
          {renderEvidenceExcerpt(record.evidence_text, 1)}
        </Space>
      ),
      width: 260,
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, record: Relationship) => (
        <Space size="small">
          <Button
            type="link"
            size="small"
            icon={<FileSearchOutlined />}
            onClick={() => openEvidenceDrawer(record)}
          >
            证据
          </Button>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEditRelationship(record)}
          >
            编辑
          </Button>
          <Button
            type="link"
            danger
            size="small"
            onClick={() => handleDeleteRelationship(record.id)}
          >
            删除
          </Button>
        </Space>
      ),
      width: 210,
      fixed: isMobile ? ('right' as const) : undefined,
    },
  ];

  // 按类别分组关系类型
  const groupedTypes = relationshipTypes.reduce((acc, type) => {
    if (!acc[type.category]) {
      acc[type.category] = [];
    }
    acc[type.category].push(type);
    return acc;
  }, {} as Record<string, RelationshipType[]>);

  const categoryLabels: Record<string, string> = {
    family: '家族关系',
    social: '社交关系',
    professional: '职业关系',
    hostile: '敌对关系'
  };

  return (
    <>
      {contextHolder}
      <div>
        <Card
        title={
          <Space wrap>
            <ApartmentOutlined />
            <span style={{ fontSize: isMobile ? 14 : 16 }}>关系管理</span>
            {!isMobile && <Tag color="blue">{currentProject?.title}</Tag>}
          </Space>
        }
        extra={
          <Space>
            <Button
              onClick={() => projectId && navigate(`/project/${projectId}/relationships-graph`)}
              size={isMobile ? 'small' : 'middle'}
            >
              关系图谱
            </Button>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setIsModalOpen(true)}
              size={isMobile ? 'small' : 'middle'}
            >
              {isMobile ? '添加' : '添加关系'}
            </Button>
          </Space>
        }
      >
        <Tabs
          items={[
            {
              key: 'list',
              label: `关系列表 (${relationships.length})`,
              children: (
                <Table
                  columns={columns}
                  dataSource={relationships}
                  rowKey="id"
                  loading={loading}
                  pagination={{
                    current: currentPage,
                    pageSize: isMobile ? 10 : pageSize,
                    pageSizeOptions: ['10', '20', '50', '100'],
                    position: ['bottomCenter'],
                    showSizeChanger: !isMobile,
                    showQuickJumper: !isMobile,
                    showTotal: (total) => `共 ${total} 条`,
                    simple: isMobile,
                    onChange: (page, size) => {
                      setCurrentPage(page);
                      if (size !== pageSize) {
                        setPageSize(size);
                        setCurrentPage(1);
                      }
                    },
                    onShowSizeChange: (_, size) => {
                      setPageSize(size);
                      setCurrentPage(1);
                    }
                  }}
                  scroll={{
                    x: 980,
                    y: isMobile ? 'calc(100vh - 360px)' : 'calc(100vh - 440px)'
                  }}
                  size={isMobile ? 'small' : 'middle'}
                />
              ),
            },
            {
              key: 'pending-review',
              label: '待审核同步',
              children: projectId ? (
                <GoldfingerPendingReviewPanel
                  projectId={projectId}
                  entityType="relationship"
                  onReviewed={loadData}
                />
              ) : null,
            },
            {
              key: 'types',
              label: `关系类型 (${relationshipTypes.length})`,
              children: (
                <div style={{
                  display: 'grid',
                  gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fill, minmax(200px, 1fr))',
                  gap: isMobile ? '12px' : '16px',
                  maxHeight: isMobile ? 'calc(100vh - 400px)' : 'calc(100vh - 350px)',
                  overflow: 'auto'
                }}>
                  {Object.entries(groupedTypes).map(([category, types]) => (
                    <Card
                      key={category}
                      size="small"
                      title={categoryLabels[category] || category}
                      headStyle={{ backgroundColor: token.colorFillAlter }}
                    >
                      <Space direction="vertical" style={{ width: '100%' }}>
                        {types.map(type => (
                          <Tag key={type.id} color={getCategoryColor(category)}>
                            {type.icon} {type.name}
                            {type.reverse_name && ` ↔ ${type.reverse_name}`}
                          </Tag>
                        ))}
                      </Space>
                    </Card>
                  ))}
                </div>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title={isEditMode ? '编辑关系' : '添加关系'}
        open={isModalOpen}
        onCancel={() => {
          setIsModalOpen(false);
          setIsEditMode(false);
          setEditingRelationship(null);
          form.resetFields();
        }}
        footer={null}
        centered={!isMobile}
        width={isMobile ? '100%' : 600}
        style={isMobile ? { top: 0, paddingBottom: 0, maxWidth: '100vw' } : undefined}
        styles={isMobile ? { body: { maxHeight: 'calc(100vh - 110px)', overflowY: 'auto' } } : undefined}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={isEditMode ? handleUpdateRelationship : handleCreateRelationship}
        >
          <Form.Item
            name="character_from_id"
            label="角色A"
            rules={[{ required: true, message: '请选择角色A' }]}
          >
            <Select
              placeholder="选择角色"
              showSearch
              disabled={isEditMode}
              filterOption={(input, option) =>
                (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
              }
              options={characters
                .filter(c => !isOrganizationEntity(c))
                .map(c => ({ label: c.name, value: c.id }))}
            />
          </Form.Item>

          <Form.Item
            name="relationship_name"
            label="关系类型"
            rules={[{ required: true, message: '请选择或输入关系类型' }]}
          >
            <AutoComplete
              placeholder="选择预定义类型或输入自定义关系"
              options={relationshipTypes.map(t => ({
                label: `${t.icon || ''} ${t.name} (${categoryLabels[t.category]})`,
                value: t.name
              }))}
              filterOption={(inputValue, option) =>
                option!.value.toUpperCase().indexOf(inputValue.toUpperCase()) !== -1
              }
            />
          </Form.Item>

          <Form.Item
            name="character_to_id"
            label="角色B"
            rules={[{ required: true, message: '请选择角色B' }]}
          >
            <Select
              placeholder="选择角色"
              showSearch
              disabled={isEditMode}
              filterOption={(input, option) =>
                (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
              }
              options={characters
                .filter(c => !isOrganizationEntity(c))
                .map(c => ({ label: c.name, value: c.id }))}
            />
          </Form.Item>

          <Form.Item
            name="intimacy_level"
            label="亲密度"
            initialValue={50}
          >
            <Slider
              min={-100}
              max={100}
              marks={{
                '-100': '-100',
                '-50': '-50',
                0: '0',
                50: '50',
                100: '100'
              }}
            />
          </Form.Item>

          <Form.Item
            name="status"
            label="状态"
            initialValue="active"
          >
            <Select>
              <Select.Option value="active">活跃</Select.Option>
              <Select.Option value="broken">破裂</Select.Option>
              <Select.Option value="past">过去</Select.Option>
              <Select.Option value="complicated">复杂</Select.Option>
            </Select>
          </Form.Item>

          <Form.Item name="description" label="关系描述">
            <TextArea rows={3} placeholder="描述这段关系的细节..." />
          </Form.Item>

          <Form.Item>
            <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
              <Button onClick={() => {
                setIsModalOpen(false);
                setIsEditMode(false);
                setEditingRelationship(null);
                form.resetFields();
              }}>取消</Button>
              <Button type="primary" htmlType="submit">
                {isEditMode ? '更新' : '创建'}
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        title={evidenceRelationship ? `关系证据：${getCharacterName(evidenceRelationship.character_from_id)} → ${getCharacterName(evidenceRelationship.character_to_id)}` : '关系证据'}
        open={evidenceOpen}
        width={720}
        onClose={() => setEvidenceOpen(false)}
      >
        {evidenceRelationship ? (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            {Boolean(evidenceRelationship.pending_candidate_count) && (
              <Alert
                type="warning"
                showIcon
                message="存在待审核关系候选"
                description={`当前正式关系没有被自动覆盖；仍有 ${evidenceRelationship.pending_candidate_count} 条冲突或低置信度候选等待评审。`}
              />
            )}
            <Descriptions bordered column={1} size="small">
              <Descriptions.Item label="关系">
                <Space wrap>
                  <Tag icon={<UserOutlined />} color="blue">{getCharacterName(evidenceRelationship.character_from_id)}</Tag>
                  <Text strong>{evidenceRelationship.relationship_name || '未知关系'}</Text>
                  <Tag icon={<UserOutlined />} color="purple">{getCharacterName(evidenceRelationship.character_to_id)}</Tag>
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="来源">{evidenceRelationship.source || '—'}</Descriptions.Item>
              <Descriptions.Item label="来源章节">{formatSourceChapter(evidenceRelationship)}</Descriptions.Item>
              <Descriptions.Item label="置信度">{formatConfidence(evidenceRelationship.confidence)}</Descriptions.Item>
              <Descriptions.Item label="状态">{evidenceRelationship.status}</Descriptions.Item>
              <Descriptions.Item label="亲密度">{evidenceRelationship.intimacy_level}</Descriptions.Item>
              <Descriptions.Item label="更新时间">{formatDateTime(evidenceRelationship.updated_at)}</Descriptions.Item>
            </Descriptions>

            <Card size="small" title="证据摘录">
              {renderEvidenceExcerpt(evidenceRelationship.evidence_text, 4)}
            </Card>

            <Card size="small" title={<Space><HistoryOutlined />合并 / 历史事件</Space>}>
              {evidenceRelationship.history && evidenceRelationship.history.length > 0 ? (
                <Space direction="vertical" size="small" style={{ width: '100%' }}>
                  {evidenceRelationship.history.map(renderHistoryCard)}
                </Space>
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无关系历史事件" />
              )}
            </Card>

            <Card size="small" title="来源 / Provenance">
              {evidenceRelationship.provenance && evidenceRelationship.provenance.length > 0 ? (
                <Space direction="vertical" size="small" style={{ width: '100%' }}>
                  {evidenceRelationship.provenance.map(renderProvenanceCard)}
                </Space>
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无来源记录" />
              )}
            </Card>
          </Space>
        ) : null}
      </Drawer>
      </div>
    </>
  );
}
