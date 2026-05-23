import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import {
  Card,
  Row,
  Col,
  Input,
  InputNumber,
  Select,
  Button,
  Tag,
  Space,
  Empty,
  Spin,
  Modal,
  Form,
  message,
  Tooltip,
  Badge,
  Tabs,
  Typography,
  Pagination,
  Alert,
  Statistic,
  List,
  theme,
} from 'antd';
import {
  SearchOutlined,
  DownloadOutlined,
  HeartOutlined,
  HeartFilled,
  CloudUploadOutlined,
  EyeOutlined,
  UserOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  SyncOutlined,
  DeleteOutlined,
  CloudOutlined,
  DisconnectOutlined,
  SettingOutlined,
  PlusOutlined,
  DatabaseOutlined,
} from '@ant-design/icons';
import { promptWorkshopApi, authApi, lorebookApi, dataBankApi } from '../services/api';
import type {
  DataBankRetrievalTraceResponse,
  LorebookPromptPreviewResponse,
  PromptAssemblyTraceResponse,
  PromptWorkshopItem,
  PromptSubmission,
  PromptSubmissionCreate,
  User,
} from '../types';
import { PROMPT_CATEGORIES } from '../types';

const { TextArea } = Input;
const { Text, Paragraph } = Typography;

export default function PromptWorkshop() {
  const { projectId } = useParams<{ projectId: string }>();
  const [items, setItems] = useState<PromptWorkshopItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize] = useState(12);
  
  // 筛选条件
  const [category, setCategory] = useState<string>('');
  const [searchKeyword, setSearchKeyword] = useState('');
  const [sortBy, setSortBy] = useState<'newest' | 'popular' | 'downloads'>('newest');
  
  // 服务状态
  const [serviceStatus, setServiceStatus] = useState<{
    mode: string;
    instance_id: string;
    cloud_connected?: boolean;
  } | null>(null);
  
  // 提交相关
  const [isSubmitModalOpen, setIsSubmitModalOpen] = useState(false);
  const [submitLoading, setSubmitLoading] = useState(false);
  const [submitForm] = Form.useForm();
  
  // 我的提交
  const [mySubmissions, setMySubmissions] = useState<PromptSubmission[]>([]);
  const [submissionsLoading, setSubmissionsLoading] = useState(false);
  
  // 详情弹窗
  const [detailItem, setDetailItem] = useState<PromptWorkshopItem | null>(null);
  const [isDetailModalOpen, setIsDetailModalOpen] = useState(false);
  
  // 导入状态
  const [importingId, setImportingId] = useState<string | null>(null);
  
  // 当前用户
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  
  // 管理员审核相关
  const [adminSubmissions, setAdminSubmissions] = useState<PromptSubmission[]>([]);
  const [adminSubmissionsLoading, setAdminSubmissionsLoading] = useState(false);
  const [adminPendingCount, setAdminPendingCount] = useState(0);
  const [adminStats, setAdminStats] = useState<{
    total_items: number;
    total_official: number;
    total_pending: number;
    total_downloads: number;
    total_likes: number;
  } | null>(null);
  const [reviewModalOpen, setReviewModalOpen] = useState(false);
  const [reviewingSubmission, setReviewingSubmission] = useState<PromptSubmission | null>(null);
  const [reviewForm] = Form.useForm();
  const [reviewLoading, setReviewLoading] = useState(false);
  const [addOfficialModalOpen, setAddOfficialModalOpen] = useState(false);
  const [addOfficialForm] = Form.useForm();
  const [addOfficialLoading, setAddOfficialLoading] = useState(false);
  
  // 已发布提示词管理
  const [publishedItems, setPublishedItems] = useState<PromptWorkshopItem[]>([]);
  const [publishedLoading, setPublishedLoading] = useState(false);
  const [editingItem, setEditingItem] = useState<PromptWorkshopItem | null>(null);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editForm] = Form.useForm();
  const [editLoading, setEditLoading] = useState(false);

  // Lorebook 预览追踪
  const [loreActivationText, setLoreActivationText] = useState('');
  const [loreMaxTokens, setLoreMaxTokens] = useState<number | null>(512);
  const [lorePreview, setLorePreview] = useState<LorebookPromptPreviewResponse | null>(null);
  const [lorePreviewLoading, setLorePreviewLoading] = useState(false);

  // Data Bank / RAG 来源追踪预览（preview-only）
  const [ragQuery, setRagQuery] = useState('');
  const [ragLimit, setRagLimit] = useState<number | null>(5);
  const [ragPreview, setRagPreview] = useState<DataBankRetrievalTraceResponse | null>(null);
  const [ragPreviewLoading, setRagPreviewLoading] = useState(false);

  // 提示词组装追踪（trace-only，不创建第二套预设系统）
  const [assemblySystemPrompt, setAssemblySystemPrompt] = useState('');
  const [assemblyWorkshopPrompt, setAssemblyWorkshopPrompt] = useState('');
  const [assemblyUserInstruction, setAssemblyUserInstruction] = useState('');
  const [assemblyTrace, setAssemblyTrace] = useState<PromptAssemblyTraceResponse | null>(null);
  const [assemblyTraceLoading, setAssemblyTraceLoading] = useState(false);
  
  // 当前活动的 Tab
  const [activeTab, setActiveTab] = useState<string>('browse');
  
  const isMobile = window.innerWidth <= 768;
  const { token } = theme.useToken();
  
  // 判断是否为服务端管理员
  const isServerAdmin = serviceStatus?.mode === 'server' && currentUser?.is_admin;

  // 卡片网格配置 - 与 WritingStyles 保持一致
  const gridConfig = {
    gutter: isMobile ? 8 : 16,
    xs: 24,
    sm: 24,
    md: 12,
    lg: 8,
    xl: 6,
  };

  // 加载服务状态和用户信息
  useEffect(() => {
    const init = async () => {
      try {
        const [status, user] = await Promise.all([
          promptWorkshopApi.getStatus(),
          authApi.getCurrentUser().catch(() => null),
        ]);
        setServiceStatus(status);
        setCurrentUser(user);
      } catch (error) {
        console.error('Failed to initialize:', error);
      }
    };
    init();
  }, []);

  // 加载工坊列表
  const loadItems = useCallback(async () => {
    setLoading(true);
    try {
      const response = await promptWorkshopApi.getItems({
        category: category || undefined,
        search: searchKeyword || undefined,
        sort: sortBy,
        page: currentPage,
        limit: pageSize,
      });
      setItems(response.data?.items || []);
      setTotal(response.data?.total || 0);
    } catch (error) {
      console.error('Failed to load workshop items:', error);
      message.error('加载提示词工坊失败');
    } finally {
      setLoading(false);
    }
  }, [category, searchKeyword, sortBy, currentPage, pageSize]);

  useEffect(() => {
    loadItems();
  }, [loadItems]);

  // 加载我的提交
  const loadMySubmissions = async () => {
    setSubmissionsLoading(true);
    try {
      const response = await promptWorkshopApi.getMySubmissions();
      setMySubmissions(response.data?.items || []);
    } catch (error) {
      console.error('Failed to load submissions:', error);
    } finally {
      setSubmissionsLoading(false);
    }
  };

  // 导入到本地
  const handleImport = async (item: PromptWorkshopItem) => {
    setImportingId(item.id);
    try {
      await promptWorkshopApi.importItem(item.id);
      message.success(`已导入「${item.name}」到本地写作风格`);
      // 刷新列表更新下载计数
      loadItems();
    } catch (error) {
      console.error('Failed to import item:', error);
      message.error('导入失败');
    } finally {
      setImportingId(null);
    }
  };

  // 点赞
  const handleLike = async (item: PromptWorkshopItem) => {
    try {
      const response = await promptWorkshopApi.toggleLike(item.id);
      // 更新本地状态
      setItems(prev => prev.map(i => 
        i.id === item.id 
          ? { ...i, is_liked: response.liked, like_count: response.like_count }
          : i
      ));
    } catch (error) {
      console.error('Failed to toggle like:', error);
      message.error('操作失败');
    }
  };

  // 提交新提示词
  const handleSubmit = async (values: PromptSubmissionCreate) => {
    setSubmitLoading(true);
    try {
      await promptWorkshopApi.submit({
        ...values,
        tags: values.tags ? (values.tags as unknown as string).split(',').map((t: string) => t.trim()).filter(Boolean) : [],
      });
      message.success('提交成功，等待管理员审核');
      setIsSubmitModalOpen(false);
      submitForm.resetFields();
      loadMySubmissions();
      // 如果是服务端管理员，刷新待审核列表
      if (isServerAdmin) {
        loadAdminSubmissions();
      }
    } catch (error) {
      console.error('Failed to submit:', error);
      message.error('提交失败');
    } finally {
      setSubmitLoading(false);
    }
  };

  // 撤回提交（pending状态）
  const handleWithdraw = async (submissionId: string) => {
    try {
      await promptWorkshopApi.withdrawSubmission(submissionId);
      message.success('已撤回');
      loadMySubmissions();
      // 如果是服务端管理员，刷新待审核列表
      if (isServerAdmin) {
        loadAdminSubmissions();
      }
    } catch (error) {
      console.error('Failed to withdraw:', error);
      message.error('撤回失败');
    }
  };

  // 删除提交记录（已审核状态）
  const handleDeleteSubmission = async (submission: PromptSubmission) => {
    Modal.confirm({
      title: '删除提交记录',
      content: `确定要删除「${submission.name}」的提交记录吗？此操作不可恢复。`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      centered: true,
      onOk: async () => {
        try {
          await promptWorkshopApi.deleteSubmission(submission.id);
          message.success('删除成功');
          loadMySubmissions();
          // 如果是服务端管理员，刷新相关列表
          if (isServerAdmin) {
            loadAdminSubmissions();
          }
        } catch (error) {
          console.error('Failed to delete submission:', error);
          message.error('删除失败');
        }
      },
    });
  };

  // 查看详情
  const handleViewDetail = async (item: PromptWorkshopItem) => {
    try {
      const response = await promptWorkshopApi.getItem(item.id);
      setDetailItem(response.data);
      setIsDetailModalOpen(true);
    } catch (error) {
      console.error('Failed to load detail:', error);
      message.error('加载详情失败');
    }
  };

  const handlePreviewLorebook = async () => {
    if (!projectId) {
      message.warning('请先进入项目后再预览 Lorebook');
      return;
    }
    setLorePreviewLoading(true);
    try {
      const response = await lorebookApi.previewPromptTrace(projectId, {
        activation_text: loreActivationText,
        max_tokens: loreMaxTokens || undefined,
        chars_per_token: 4,
      });
      setLorePreview(response);
      message.success('Lorebook 预览已更新');
    } catch (error) {
      console.error('Failed to preview lorebook prompt trace:', error);
      message.error('Lorebook 预览失败');
    } finally {
      setLorePreviewLoading(false);
    }
  };

  const handlePreviewRagSources = async () => {
    if (!projectId) {
      message.warning('请先进入项目后再预览 Data Bank');
      return;
    }
    const query = ragQuery.trim();
    if (!query) {
      message.warning('请输入用于检索 Data Bank 的查询文本');
      return;
    }

    setRagPreviewLoading(true);
    try {
      const response = await dataBankApi.retrievePreview(projectId, {
        query,
        limit: ragLimit || undefined,
      });
      setRagPreview(response);
      message.success('Data Bank/RAG 预览已更新');
    } catch (error) {
      console.error('Failed to preview Data Bank RAG sources:', error);
      message.error('Data Bank/RAG 预览失败');
    } finally {
      setRagPreviewLoading(false);
    }
  };

  const handlePreviewAssemblyTrace = async () => {
    const layerInputs = [
      {
        id: 'system-template',
        label: '系统模板 / 基础提示词',
        source_type: 'system_template',
        content: assemblySystemPrompt,
        order: 10,
        metadata: { boundary: 'prompt_workshop', editable_in: 'PromptWorkshop' },
      },
      {
        id: 'workshop-item',
        label: '工坊提示词 / 写作风格',
        source_type: 'workshop_item',
        content: assemblyWorkshopPrompt,
        order: 40,
        metadata: { boundary: 'prompt_workshop', persistence: 'existing_workshop_or_writing_style' },
      },
      {
        id: 'user-instruction',
        label: '本次用户指令',
        source_type: 'user_instruction',
        content: assemblyUserInstruction,
        order: 80,
        metadata: { boundary: 'prompt_workshop', ephemeral: true },
      },
    ];
    const layers = layerInputs
      .map(layer => ({ ...layer, content: layer.content.trim() }))
      .filter(layer => layer.content.length > 0);

    if (layers.length === 0) {
      message.warning('请至少填写一个提示词层');
      return;
    }

    setAssemblyTraceLoading(true);
    try {
      const response = await promptWorkshopApi.previewAssemblyTrace({
        trace_version: 1,
        layers,
        separator: '\n\n',
      });
      setAssemblyTrace(response);
      message.success('组装追踪已更新');
    } catch (error) {
      console.error('Failed to preview prompt assembly trace:', error);
      message.error('组装追踪失败');
    } finally {
      setAssemblyTraceLoading(false);
    }
  };

  // 获取分类标签颜色
  const getCategoryColor = (cat: string) => {
    const colors: Record<string, string> = {
      general: 'blue',
      fantasy: 'purple',
      martial: 'orange',
      romance: 'pink',
      scifi: 'cyan',
      horror: 'red',
      history: 'gold',
      urban: 'green',
      game: 'magenta',
      other: 'default',
    };
    return colors[cat] || 'default';
  };

  // 获取分类名称
  const getCategoryName = (cat: string) => {
    return PROMPT_CATEGORIES[cat] || cat;
  };
  
  // 获取分类选项列表
  const categoryOptions = Object.entries(PROMPT_CATEGORIES).map(([value, label]) => ({
    value,
    label,
  }));

  // 获取提交状态标签
  const getStatusTag = (status: string) => {
    const config: Record<string, { color: string; icon: React.ReactNode; text: string }> = {
      pending: { color: 'processing', icon: <ClockCircleOutlined />, text: '待审核' },
      approved: { color: 'success', icon: <CheckCircleOutlined />, text: '已通过' },
      rejected: { color: 'error', icon: <CloseCircleOutlined />, text: '已拒绝' },
    };
    const cfg = config[status] || config.pending;
    return <Tag color={cfg.color} icon={cfg.icon}>{cfg.text}</Tag>;
  };

  // 渲染筛选区域（固定在顶部）
  const renderFilterBar = () => (
    <div style={{ marginBottom: 16 }}>
      {/* 服务状态 */}
      {serviceStatus && !serviceStatus.cloud_connected && serviceStatus.mode === 'client' && (
        <Alert
          type="warning"
          message="云端服务未连接"
          description="无法访问提示词工坊，请检查网络连接或稍后重试"
          icon={<DisconnectOutlined />}
          showIcon
          style={{ marginBottom: 16 }}
        />
      )}
      
      {/* 筛选区域 */}
      <div style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: 12,
        alignItems: 'center',
      }}>
        <Input
          placeholder="搜索提示词..."
          prefix={<SearchOutlined />}
          value={searchKeyword}
          onChange={e => setSearchKeyword(e.target.value)}
          onPressEnter={() => { setCurrentPage(1); loadItems(); }}
          style={{ width: isMobile ? '100%' : 200 }}
          allowClear
        />
        <Select
          placeholder="选择分类"
          value={category}
          onChange={v => { setCategory(v); setCurrentPage(1); }}
          style={{ width: isMobile ? '100%' : 150 }}
          allowClear
        >
          {categoryOptions.map(cat => (
            <Select.Option key={cat.value} value={cat.value}>{cat.label}</Select.Option>
          ))}
        </Select>
        <Select
          value={sortBy}
          onChange={v => { setSortBy(v); setCurrentPage(1); }}
          style={{ width: isMobile ? '100%' : 120 }}
        >
          <Select.Option value="newest">最新发布</Select.Option>
          <Select.Option value="popular">最受欢迎</Select.Option>
          <Select.Option value="downloads">下载最多</Select.Option>
        </Select>
        <Button
          icon={<SyncOutlined />}
          onClick={() => { setCurrentPage(1); loadItems(); }}
        >
          刷新
        </Button>
      </div>
    </div>
  );

  // 渲染工坊列表（只有卡片部分，用于滚动区域）
  const renderWorkshopList = () => (
    <Spin spinning={loading}>
          {items.length === 0 ? (
            <Empty description="暂无提示词" />
          ) : (
            <>
              <Row
                gutter={[0, gridConfig.gutter]}
                style={{ marginLeft: 0, marginRight: 0 }}
              >
              {items.map(item => (
                <Col
                  key={item.id}
                  xs={gridConfig.xs}
                  sm={gridConfig.sm}
                  md={gridConfig.md}
                  lg={gridConfig.lg}
                  xl={gridConfig.xl}
                  style={{
                    paddingLeft: 0,
                    paddingRight: gridConfig.gutter / 2,
                    marginBottom: gridConfig.gutter
                  }}
                >
                  <Card
                    hoverable
                    style={{ 
                      height: '100%', 
                      borderRadius: 12,
                      display: 'flex',
                      flexDirection: 'column',
                      border: `1px solid ${token.colorBorderSecondary}`,
                    }}
                    styles={{ body: { 
                      padding: 16, 
                      display: 'flex', 
                      flexDirection: 'column', 
                      flex: 1,
                    } }}
                    actions={[
                      <Tooltip title="查看详情" key="view">
                        <EyeOutlined onClick={() => handleViewDetail(item)} />
                      </Tooltip>,
                      <Tooltip title={item.is_liked ? '取消点赞' : '点赞'} key="like">
                        <span onClick={() => handleLike(item)}>
                          {item.is_liked ? (
                            <HeartFilled style={{ color: token.colorError }} />
                          ) : (
                            <HeartOutlined />
                          )}
                          <span style={{ marginLeft: 4 }}>{item.like_count || 0}</span>
                        </span>
                      </Tooltip>,
                      <Tooltip title="导入到本地" key="import">
                        <Button
                          type="link"
                          size="small"
                          icon={<DownloadOutlined />}
                          loading={importingId === item.id}
                          onClick={() => handleImport(item)}
                        >
                          {item.download_count || 0}
                        </Button>
                      </Tooltip>,
                    ]}
                  >
                    <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
                      <Space style={{ marginBottom: 12 }} wrap>
                        <Text strong style={{ fontSize: 16 }}>{item.name}</Text>
                        <Tag color={getCategoryColor(item.category)}>
                          {getCategoryName(item.category)}
                        </Tag>
                      </Space>
                      
                      {item.description && (
                        <Paragraph
                          type="secondary"
                          style={{ fontSize: 13, marginBottom: 12 }}
                          ellipsis={{ rows: 2, tooltip: item.description }}
                        >
                          {item.description}
                        </Paragraph>
                      )}
                      
                      <Paragraph
                        type="secondary"
                        style={{
                          fontSize: 12,
                          marginBottom: 0,
                          backgroundColor: token.colorFillQuaternary,
                          padding: 8,
                          borderRadius: 4,
                          flex: 1,
                          minHeight: 60,
                        }}
                        ellipsis={{ rows: 3 }}
                      >
                        {item.prompt_content}
                      </Paragraph>
                      
                      {item.tags && item.tags.length > 0 && (
                        <Space size={4} wrap style={{ marginTop: 8 }}>
                          {item.tags.slice(0, 3).map(tag => (
                            <Tag key={tag} style={{ fontSize: 11 }}>{tag}</Tag>
                          ))}
                          {item.tags.length > 3 && (
                            <Tag style={{ fontSize: 11 }}>+{item.tags.length - 3}</Tag>
                          )}
                        </Space>
                      )}
                    </div>
                    
                    <div style={{ marginTop: 8, color: token.colorTextTertiary, fontSize: 12 }}>
                      <Space>
                        <span><UserOutlined /> {item.author_name || '匿名'}</span>
                      </Space>
                    </div>
                  </Card>
                </Col>
              ))}
              </Row>
              
              {total > pageSize && (
                <div style={{ marginTop: 24, textAlign: 'center', paddingBottom: 16 }}>
                  <Pagination
                    current={currentPage}
                    total={total}
                    pageSize={pageSize}
                    onChange={page => setCurrentPage(page)}
                    showSizeChanger={false}
                    showTotal={t => `共 ${t} 个提示词`}
                  />
                </div>
              )}
            </>
          )}
    </Spin>
  );

  // 渲染我的提交
  const renderMySubmissions = () => (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text>查看您提交的提示词及审核状态</Text>
        <Button icon={<SyncOutlined />} onClick={loadMySubmissions}>
          刷新
        </Button>
      </div>
      
      <Spin spinning={submissionsLoading}>
          {mySubmissions.length === 0 ? (
            <Empty description="暂无提交记录" />
          ) : (
            <Row gutter={[0, gridConfig.gutter]} style={{ marginLeft: 0, marginRight: 0 }}>
              {mySubmissions.map(sub => (
              <Col 
                key={sub.id} 
                xs={gridConfig.xs} 
                sm={gridConfig.sm} 
                md={gridConfig.md} 
                lg={gridConfig.lg}
                xl={gridConfig.xl}
                style={{
                  paddingLeft: 0,
                  paddingRight: gridConfig.gutter / 2,
                  marginBottom: gridConfig.gutter
                }}
              >
                <Card
                  style={{ borderRadius: 12, height: '100%', border: `1px solid ${token.colorBorderSecondary}` }}
                  styles={{ body: { padding: 16 } }}
                >
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Text strong>{sub.name}</Text>
                      {getStatusTag(sub.status)}
                    </div>
                    
                    <Tag color={getCategoryColor(sub.category)}>
                      {getCategoryName(sub.category)}
                    </Tag>
                    
                    <Paragraph
                      type="secondary"
                      style={{ fontSize: 12, marginBottom: 0 }}
                      ellipsis={{ rows: 2 }}
                    >
                      {sub.prompt_content}
                    </Paragraph>
                    
                    {sub.status === 'rejected' && sub.review_note && (
                      <Alert
                        type="error"
                        message="拒绝原因"
                        description={sub.review_note}
                        style={{ fontSize: 12 }}
                      />
                    )}
                    
                    <div style={{ fontSize: 12, color: token.colorTextTertiary }}>
                      提交时间: {sub.created_at ? new Date(sub.created_at).toLocaleDateString() : '-'}
                    </div>
                    
                    <Space>
                      {sub.status === 'pending' && (
                        <Button
                          type="link"
                          danger
                          size="small"
                          icon={<DeleteOutlined />}
                          onClick={() => handleWithdraw(sub.id)}
                        >
                          撤回
                        </Button>
                      )}
                      {sub.status !== 'pending' && (
                        <Button
                          type="link"
                          danger
                          size="small"
                          icon={<DeleteOutlined />}
                          onClick={() => handleDeleteSubmission(sub)}
                        >
                          删除记录
                        </Button>
                      )}
                    </Space>
                  </Space>
                </Card>
              </Col>
            ))}
            </Row>
          )}
      </Spin>
    </div>
  );

  const renderLorebookPreview = () => {
    const trace = lorePreview?.trace;
    return (
      <div style={{ paddingRight: isMobile ? 0 : 8 }}>
        <Alert
          type="info"
          showIcon
          message="Lorebook 提示词预览"
          description="这里仅展示会被选中的 Lorebook 条目和提示词追踪；默认不会注入章节生成，除非后端显式开启 lorebook_injection_enabled。"
          style={{ marginBottom: 16 }}
        />

        <Card style={{ borderRadius: 12, border: `1px solid ${token.colorBorderSecondary}`, marginBottom: 16 }}>
          <Space direction="vertical" style={{ width: '100%' }} size={12}>
            <Text strong>激活文本</Text>
            <TextArea
              rows={5}
              value={loreActivationText}
              onChange={event => setLoreActivationText(event.target.value)}
              placeholder="粘贴章节大纲、上一章摘要或试写片段，用于匹配 Lorebook 激活关键词..."
            />
            <Space wrap>
              <Text type="secondary">Token 预算估算</Text>
              <InputNumber
                min={1}
                max={4000}
                value={loreMaxTokens}
                onChange={value => setLoreMaxTokens(typeof value === 'number' ? value : null)}
              />
              <Button type="primary" loading={lorePreviewLoading} onClick={handlePreviewLorebook}>
                生成预览
              </Button>
            </Space>
          </Space>
        </Card>

        {trace ? (
          <Space direction="vertical" style={{ width: '100%' }} size={16}>
            <Row gutter={[12, 12]}>
              <Col xs={24} md={8}>
                <Card size="small"><Statistic title="命中条目" value={trace.selected_count} suffix={`/ ${trace.total_candidates}`} /></Card>
              </Col>
              <Col xs={24} md={8}>
                <Card size="small"><Statistic title="预算字符" value={trace.budget_estimate.chars_used} suffix={trace.budget_estimate.budget_chars ? `/ ${trace.budget_estimate.budget_chars}` : ''} /></Card>
              </Col>
              <Col xs={24} md={8}>
                <Card size="small"><Statistic title="估算 Token" value={trace.budget_estimate.estimated_tokens} /></Card>
              </Col>
            </Row>

            <Card title="追踪摘要" size="small">
              <Space direction="vertical" style={{ width: '100%' }}>
                <div><Text type="secondary">来源类型：</Text><Tag color="blue">{trace.source_type}</Tag></div>
                <div><Text type="secondary">选中 ID：</Text>{trace.selected_lore_ids.length > 0 ? trace.selected_lore_ids.map(id => <Tag key={id}>{id}</Tag>) : <Text type="secondary">无</Text>}</div>
              </Space>
            </Card>

            <Card title="选中条目" size="small">
              <List
                dataSource={trace.items}
                locale={{ emptyText: '未命中 Lorebook 条目' }}
                renderItem={item => (
                  <List.Item>
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <Space wrap>
                        <Tag color="processing">#{item.order}</Tag>
                        <Text strong>{item.title}</Text>
                        <Tag>{item.id}</Tag>
                        <Tag color="blue">{item.source_type}</Tag>
                        <Tag color="purple">{item.entry_source_type}</Tag>
                        <Text type="secondary">优先级 {item.priority}</Text>
                      </Space>
                      <Text type="secondary">匹配关键词：{item.matched_keys.join('、') || '无'}</Text>
                      <Paragraph style={{ marginBottom: 0 }} ellipsis={{ rows: 2, expandable: true }}>
                        {item.content}
                      </Paragraph>
                    </Space>
                  </List.Item>
                )}
              />
            </Card>

            <Card title="最终预览文本" size="small">
              {trace.final_preview_text ? (
                <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: 0, fontSize: 13 }}>
                  {trace.final_preview_text}
                </pre>
              ) : (
                <Empty description="没有可注入的预览文本" />
              )}
            </Card>
          </Space>
        ) : (
          <Empty description="输入激活文本后生成 Lorebook 预览" />
        )}
      </div>
    );
  };

  const renderRagPreview = () => {
    const trace = ragPreview;
    return (
      <div style={{ paddingRight: isMobile ? 0 : 8 }}>
        <Alert
          type="info"
          showIcon
          message="Data Bank / RAG 来源预览"
          description="这里仅预览本项目 Data Bank 中哪些来源会进入提示词候选上下文；默认 rag_injection_enabled=false，不会自动注入章节生成，也不会写入、抓取或修改资料库。"
          style={{ marginBottom: token.marginMD }}
        />

        <Card style={{ borderRadius: token.borderRadiusLG, border: `1px solid ${token.colorBorderSecondary}`, marginBottom: token.marginMD }}>
          <Space direction="vertical" style={{ width: '100%' }} size={token.marginSM}>
            <Space align="center" wrap>
              <DatabaseOutlined style={{ color: token.colorPrimary }} />
              <Text strong>检索查询</Text>
              <Tag color="blue">preview-only</Tag>
              <Tag color="default">rag_injection_enabled=false</Tag>
            </Space>
            <TextArea
              rows={4}
              value={ragQuery}
              onChange={event => setRagQuery(event.target.value)}
              placeholder="粘贴章节大纲、场景目标或关键词，用于查看 Data Bank 会命中的来源片段..."
            />
            <Space wrap>
              <Text type="secondary">返回来源数</Text>
              <InputNumber
                min={1}
                max={20}
                value={ragLimit}
                onChange={value => setRagLimit(typeof value === 'number' ? value : null)}
              />
              <Button type="primary" loading={ragPreviewLoading} onClick={handlePreviewRagSources}>
                生成来源预览
              </Button>
            </Space>
          </Space>
        </Card>

        {trace ? (
          <Space direction="vertical" style={{ width: '100%' }} size={token.marginMD}>
            <Row gutter={[token.marginSM, token.marginSM]}>
              <Col xs={24} md={8}>
                <Card size="small"><Statistic title="命中来源" value={trace.returned_count} suffix={`/ ${trace.total_candidates}`} /></Card>
              </Col>
              <Col xs={24} md={8}>
                <Card size="small"><Statistic title="检索策略" value={trace.strategy} /></Card>
              </Col>
              <Col xs={24} md={8}>
                <Card size="small"><Statistic title="项目范围" value={trace.project_id} /></Card>
              </Col>
            </Row>

            <Card title="来源追踪" size="small">
              <List
                dataSource={trace.results}
                locale={{ emptyText: '当前查询未命中 Data Bank 来源' }}
                renderItem={item => (
                  <List.Item>
                    <Space direction="vertical" style={{ width: '100%' }} size={token.marginXS}>
                      <Space wrap>
                        <Tag color="processing">#{item.order}</Tag>
                        <Text strong>{item.title}</Text>
                        <Tag>{item.item_id}</Tag>
                        <Tag color="blue">score {item.score.toFixed(2)}</Tag>
                        <Tag color="purple">{item.item_source_type}</Tag>
                        {item.filename && <Tag>{item.filename}</Tag>}
                      </Space>
                      <Text type="secondary">
                        chunk_id={item.chunk_id} · chunk_index={item.chunk_index} · 位置 {item.char_start}–{item.char_end}
                      </Text>
                      <Text type="secondary">匹配词：{item.matched_terms.join('、') || '无'}</Text>
                      <div
                        style={{
                          padding: `${token.paddingXS}px ${token.paddingSM}px`,
                          background: token.colorFillTertiary,
                          border: `1px solid ${token.colorBorderSecondary}`,
                          borderRadius: token.borderRadius,
                        }}
                      >
                        <Text type="secondary" style={{ display: 'block', marginBottom: token.marginXXS }}>Excerpt</Text>
                        <Paragraph style={{ marginBottom: 0 }} ellipsis={{ rows: 3, expandable: true, symbol: '展开' }}>
                          {item.content}
                        </Paragraph>
                      </div>
                    </Space>
                  </List.Item>
                )}
              />
            </Card>

            <Card title="预览说明" size="small">
              <Space direction="vertical" style={{ width: '100%' }}>
                <div><Text type="secondary">请求范围：</Text><Tag color="green">server-scoped project/user</Tag></div>
                <div><Text type="secondary">来源 ID：</Text>{trace.results.length > 0 ? trace.results.map(item => <Tag key={`${item.item_id}-${item.chunk_id}`}>{item.item_id}</Tag>) : <Text type="secondary">无</Text>}</div>
                <Text type="secondary">该界面复用 /api/memories/projects/{'{project_id}'}/data-bank/retrieve；不会在前端生成 embeddings 或抓取远程 URL。</Text>
              </Space>
            </Card>
          </Space>
        ) : (
          <Empty description="输入查询文本后生成 Data Bank/RAG 来源预览" />
        )}
      </div>
    );
  };

  const renderAssemblyTrace = () => {
    const trace = assemblyTrace?.trace;
    return (
      <div style={{ paddingRight: isMobile ? 0 : 8 }}>
        <Alert
          type="info"
          showIcon
          message="提示词组装追踪（不新增预设栈）"
          description="Task 9 调查确认新的预设系统会与提示词工坊高度重叠；这里仅在现有边界内校验层顺序、版本和哈希，不保存、不分享、不执行脚本。"
          style={{ marginBottom: 16 }}
        />

        <Card style={{ borderRadius: 12, border: `1px solid ${token.colorBorderSecondary}`, marginBottom: 16 }}>
          <Space direction="vertical" style={{ width: '100%' }} size={12}>
            <Row gutter={[12, 12]}>
              <Col xs={24} lg={8}>
                <Text strong>系统模板 / 基础提示词</Text>
                <TextArea
                  rows={6}
                  value={assemblySystemPrompt}
                  onChange={event => setAssemblySystemPrompt(event.target.value)}
                  placeholder="粘贴系统模板或章节基础提示词..."
                  style={{ marginTop: 8 }}
                />
              </Col>
              <Col xs={24} lg={8}>
                <Text strong>工坊提示词 / 写作风格</Text>
                <TextArea
                  rows={6}
                  value={assemblyWorkshopPrompt}
                  onChange={event => setAssemblyWorkshopPrompt(event.target.value)}
                  placeholder="粘贴从工坊导入或本地写作风格内容..."
                  style={{ marginTop: 8 }}
                />
              </Col>
              <Col xs={24} lg={8}>
                <Text strong>本次用户指令</Text>
                <TextArea
                  rows={6}
                  value={assemblyUserInstruction}
                  onChange={event => setAssemblyUserInstruction(event.target.value)}
                  placeholder="填写一次性的章节/场景要求..."
                  style={{ marginTop: 8 }}
                />
              </Col>
            </Row>
            <Space wrap>
              <Tag color="blue">trace_version=1</Tag>
              <Tag color="purple">boundary=prompt_workshop</Tag>
              <Tag color="green">persistence=none</Tag>
              <Button type="primary" loading={assemblyTraceLoading} onClick={handlePreviewAssemblyTrace}>
                生成组装追踪
              </Button>
            </Space>
          </Space>
        </Card>

        {trace ? (
          <Space direction="vertical" style={{ width: '100%' }} size={16}>
            <Row gutter={[12, 12]}>
              <Col xs={24} md={8}>
                <Card size="small"><Statistic title="追踪ID" value={trace.trace_id} /></Card>
              </Col>
              <Col xs={24} md={8}>
                <Card size="small"><Statistic title="层数量" value={trace.layers.length} /></Card>
              </Col>
              <Col xs={24} md={8}>
                <Card size="small"><Statistic title="输出字符" value={trace.final_prompt.length} /></Card>
              </Col>
            </Row>

            <Card title="边界与校验" size="small">
              <Space direction="vertical" style={{ width: '100%' }}>
                <div><Text type="secondary">Schema：</Text><Tag>{trace.schema_version}</Tag></div>
                <div><Text type="secondary">边界：</Text><Tag color="purple">{trace.preset_boundary}</Tag><Tag color="green">{assemblyTrace?.boundary.mode}</Tag></div>
                <div><Text type="secondary">是否有效：</Text><Tag color={trace.validation.valid ? 'green' : 'red'}>{trace.validation.valid ? 'valid' : 'invalid'}</Tag></div>
                <Text type="secondary">最终 Hash：{trace.final_prompt_hash}</Text>
              </Space>
            </Card>

            <Card title="层顺序" size="small">
              <List
                dataSource={trace.layers}
                renderItem={item => (
                  <List.Item>
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <Space wrap>
                        <Tag color="processing">#{item.order}</Tag>
                        <Text strong>{item.label}</Text>
                        <Tag>{item.id}</Tag>
                        <Tag color="blue">{item.source_type}</Tag>
                        <Tag color={item.enabled ? 'green' : 'default'}>{item.enabled ? 'enabled' : 'disabled'}</Tag>
                      </Space>
                      <Text type="secondary">content_sha256={item.content_hash} · {item.content_length} 字符</Text>
                    </Space>
                  </List.Item>
                )}
              />
            </Card>

            <Card title="最终组装预览" size="small">
              {trace.final_prompt ? (
                <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: 0, fontSize: 13 }}>
                  {trace.final_prompt}
                </pre>
              ) : (
                <Empty description="没有可预览的组装文本" />
              )}
            </Card>
          </Space>
        ) : (
          <Empty description="填写提示词层后生成确定性追踪" />
        )}
      </div>
    );
  };

  // 加载管理员待审核列表
  const loadAdminSubmissions = async () => {
    if (!isServerAdmin) return;
    
    setAdminSubmissionsLoading(true);
    try {
      const [subsResponse, statsResponse] = await Promise.all([
        promptWorkshopApi.adminGetSubmissions({ status: 'pending', limit: 50 }),
        promptWorkshopApi.adminGetStats(),
      ]);
      setAdminSubmissions(subsResponse.data?.items || []);
      setAdminPendingCount(subsResponse.data?.pending_count || 0);
      setAdminStats(statsResponse.data || null);
    } catch (error) {
      console.error('Failed to load admin submissions:', error);
    } finally {
      setAdminSubmissionsLoading(false);
    }
  };

  // 加载已发布的提示词列表（管理员用）
  const loadPublishedItems = async () => {
    if (!isServerAdmin) return;
    
    setPublishedLoading(true);
    try {
      const response = await promptWorkshopApi.getItems({ limit: 100 });
      setPublishedItems(response.data?.items || []);
    } catch (error) {
      console.error('Failed to load published items:', error);
    } finally {
      setPublishedLoading(false);
    }
  };

  // 删除已发布的提示词
  const handleDeleteItem = async (item: PromptWorkshopItem) => {
    Modal.confirm({
      title: '确认删除',
      content: `确定要删除「${item.name}」吗？此操作不可恢复。`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      centered: true,
      onOk: async () => {
        try {
          await promptWorkshopApi.adminDeleteItem(item.id);
          message.success('删除成功');
          loadPublishedItems();
          loadAdminSubmissions();
          loadItems();
        } catch (error) {
          console.error('Failed to delete item:', error);
          message.error('删除失败');
        }
      },
    });
  };

  // 编辑已发布的提示词
  const handleEditItem = async (values: { name: string; category: string; description?: string; prompt_content: string; tags?: string }) => {
    if (!editingItem) return;
    
    setEditLoading(true);
    try {
      await promptWorkshopApi.adminUpdateItem(editingItem.id, {
        ...values,
        tags: values.tags ? values.tags.split(',').map(t => t.trim()).filter(Boolean) : undefined,
      });
      message.success('修改成功');
      setEditModalOpen(false);
      setEditingItem(null);
      editForm.resetFields();
      loadPublishedItems();
      loadItems();
    } catch (error) {
      console.error('Failed to update item:', error);
      message.error('修改失败');
    } finally {
      setEditLoading(false);
    }
  };

  // 打开编辑弹窗
  const openEditModal = (item: PromptWorkshopItem) => {
    setEditingItem(item);
    editForm.setFieldsValue({
      name: item.name,
      category: item.category,
      description: item.description,
      prompt_content: item.prompt_content,
      tags: item.tags?.join(', '),
    });
    setEditModalOpen(true);
  };

  // 审核提交
  const handleReview = async (action: 'approve' | 'reject') => {
    if (!reviewingSubmission) return;
    
    setReviewLoading(true);
    try {
      const values = reviewForm.getFieldsValue();
      await promptWorkshopApi.adminReviewSubmission(reviewingSubmission.id, {
        action,
        review_note: values.review_note,
        category: values.category,
        tags: values.tags ? values.tags.split(',').map((t: string) => t.trim()).filter(Boolean) : undefined,
      });
      message.success(action === 'approve' ? '已通过审核' : '已拒绝');
      setReviewModalOpen(false);
      setReviewingSubmission(null);
      reviewForm.resetFields();
      // 刷新所有相关数据
      loadAdminSubmissions();
      loadItems();
      loadPublishedItems();  // 通过时会新增到已发布列表
    } catch (error) {
      console.error('Failed to review:', error);
      message.error('审核失败');
    } finally {
      setReviewLoading(false);
    }
  };

  // 添加官方提示词
  const handleAddOfficial = async (values: { name: string; category: string; description?: string; prompt_content: string; tags?: string }) => {
    setAddOfficialLoading(true);
    try {
      await promptWorkshopApi.adminCreateItem({
        ...values,
        tags: values.tags ? values.tags.split(',').map(t => t.trim()).filter(Boolean) : undefined,
      });
      message.success('添加成功');
      setAddOfficialModalOpen(false);
      addOfficialForm.resetFields();
      loadItems();
      loadAdminSubmissions();
      loadPublishedItems();
    } catch (error) {
      console.error('Failed to add official item:', error);
      message.error('添加失败');
    } finally {
      setAddOfficialLoading(false);
    }
  };

  // 渲染管理员面板
  const renderAdminPanel = () => (
    <div>
      {/* 统计数据 */}
      {adminStats && (
        <Row gutter={16} style={{ marginBottom: 24 }}>
          <Col span={4}>
            <Card size="small">
              <Statistic title="总提示词" value={adminStats.total_items} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="官方提示词" value={adminStats.total_official} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="待审核" value={adminStats.total_pending} valueStyle={{ color: token.colorWarning }} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="总下载" value={adminStats.total_downloads} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="总点赞" value={adminStats.total_likes} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddOfficialModalOpen(true)}>
                添加官方
              </Button>
            </Card>
          </Col>
        </Row>
      )}
      
      {/* 待审核列表 */}
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text strong>待审核提交 ({adminPendingCount})</Text>
        <Button icon={<SyncOutlined />} onClick={loadAdminSubmissions}>
          刷新
        </Button>
      </div>
      
      <Spin spinning={adminSubmissionsLoading}>
        {adminSubmissions.length === 0 ? (
          <Empty description="暂无待审核提交" />
        ) : (
          <Row gutter={[0, gridConfig.gutter]} style={{ marginLeft: 0, marginRight: 0 }}>
            {adminSubmissions.map(sub => (
              <Col 
                key={sub.id} 
                xs={gridConfig.xs} 
                sm={gridConfig.sm} 
                md={gridConfig.md} 
                lg={gridConfig.lg}
                xl={gridConfig.xl}
                style={{
                  paddingLeft: 0,
                  paddingRight: gridConfig.gutter / 2,
                  marginBottom: gridConfig.gutter
                }}
              >
                <Card
                  style={{ borderRadius: 12, border: `1px solid ${token.colorBorderSecondary}` }}
                      styles={{ body: { padding: 16 } }}
                  actions={[
                    <Button
                      key="approve"
                      type="link"
                      style={{ color: token.colorSuccess }}
                      onClick={() => {
                        setReviewingSubmission(sub);
                        reviewForm.setFieldsValue({
                          category: sub.category,
                          tags: sub.tags?.join(', '),
                        });
                        setReviewModalOpen(true);
                      }}
                    >
                      审核
                    </Button>,
                  ]}
                >
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Text strong>{sub.name}</Text>
                    <Tag color={getCategoryColor(sub.category)}>
                      {getCategoryName(sub.category)}
                    </Tag>
                    
                    <Paragraph
                      type="secondary"
                      style={{ fontSize: 12, marginBottom: 0 }}
                      ellipsis={{ rows: 3 }}
                    >
                      {sub.prompt_content}
                    </Paragraph>
                    
                    <div style={{ fontSize: 11, color: token.colorTextTertiary }}>
                      <div>提交者: {sub.submitter_name || '未知'}</div>
                      <div>来源: {sub.source_instance}</div>
                      <div>时间: {sub.created_at ? new Date(sub.created_at).toLocaleDateString() : '-'}</div>
                    </div>
                  </Space>
                </Card>
              </Col>
            ))}
          </Row>
        )}
      </Spin>
      
      {/* 已发布提示词管理 */}
      <div style={{ marginTop: 32, marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text strong>已发布提示词管理 ({publishedItems.length})</Text>
        <Button icon={<SyncOutlined />} onClick={loadPublishedItems}>
          刷新
        </Button>
      </div>
      
      <Spin spinning={publishedLoading}>
        {publishedItems.length === 0 ? (
          <Empty description="暂无已发布提示词" />
        ) : (
          <Row gutter={[0, gridConfig.gutter]} style={{ marginLeft: 0, marginRight: 0 }}>
            {publishedItems.map(item => (
              <Col 
                key={item.id} 
                xs={gridConfig.xs} 
                sm={gridConfig.sm} 
                md={gridConfig.md} 
                lg={gridConfig.lg}
                xl={gridConfig.xl}
                style={{
                  paddingLeft: 0,
                  paddingRight: gridConfig.gutter / 2,
                  marginBottom: gridConfig.gutter
                }}
              >
                <Card
                  style={{ borderRadius: 12, border: `1px solid ${token.colorBorderSecondary}` }}
                      styles={{ body: { padding: 16 } }}
                  actions={[
                    <Tooltip title="编辑" key="edit">
                      <Button
                        type="link"
                        icon={<SettingOutlined />}
                        onClick={() => openEditModal(item)}
                      />
                    </Tooltip>,
                    <Tooltip title="删除" key="delete">
                      <Button
                        type="link"
                        danger
                        icon={<DeleteOutlined />}
                        onClick={() => handleDeleteItem(item)}
                      />
                    </Tooltip>,
                  ]}
                >
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Text strong ellipsis style={{ maxWidth: 120 }}>{item.name}</Text>
                      {item.is_official && <Tag color="gold">官方</Tag>}
                    </div>
                    <Tag color={getCategoryColor(item.category)}>
                      {getCategoryName(item.category)}
                    </Tag>
                    
                    <Paragraph
                      type="secondary"
                      style={{ fontSize: 12, marginBottom: 0 }}
                      ellipsis={{ rows: 2 }}
                    >
                      {item.prompt_content}
                    </Paragraph>
                    
                    <div style={{ fontSize: 11, color: token.colorTextTertiary }}>
                      <Space>
                        <span><HeartOutlined /> {item.like_count || 0}</span>
                        <span><DownloadOutlined /> {item.download_count || 0}</span>
                      </Space>
                    </div>
                  </Space>
                </Card>
              </Col>
            ))}
          </Row>
        )}
      </Spin>
    </div>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* 固定区域：标题 + Tabs切换栏 + 筛选栏 */}
      <div style={{ flexShrink: 0 }}>
        {/* 标题和操作区 */}
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: isMobile ? '12px 0' : '16px 0',
          marginBottom: isMobile ? 12 : 16,
          borderBottom: `1px solid ${token.colorBorderSecondary}`,
          flexWrap: 'wrap',
          gap: 12,
        }}>
          <h2 style={{ margin: 0, fontSize: isMobile ? 18 : 24, display: 'flex', alignItems: 'center', gap: 8 }}>
            <CloudOutlined />
            提示词工坊
            {serviceStatus?.mode === 'server' && (
              <Badge status="success" text="服务端模式" style={{ marginLeft: 8, fontSize: 12 }} />
            )}
          </h2>
          <Button
            type="primary"
            icon={<CloudUploadOutlined />}
            onClick={() => setIsSubmitModalOpen(true)}
          >
            分享我的提示词
          </Button>
        </div>

        {/* Tabs 切换栏（不含内容） */}
        <Tabs
          activeKey={activeTab}
          onChange={key => {
            setActiveTab(key);
            if (key === 'submissions') loadMySubmissions();
            if (key === 'admin') {
              loadAdminSubmissions();
              loadPublishedItems();
            }
          }}
          items={[
            { key: 'browse', label: '浏览工坊' },
            { key: 'lorebook-preview', label: 'Lorebook预览' },
            { key: 'rag-preview', label: 'Data Bank预览' },
            { key: 'assembly-trace', label: '组装追踪' },
            {
              key: 'submissions',
              label: (
                <Badge count={mySubmissions.filter(s => s.status === 'pending').length} size="small">
                  我的提交
                </Badge>
              ),
            },
            ...(isServerAdmin ? [{
              key: 'admin',
              label: (
                <Badge count={adminPendingCount} size="small">
                  <span><SettingOutlined /> 管理审核</span>
                </Badge>
              ),
            }] : []),
          ]}
          tabBarStyle={{ marginBottom: 16 }}
        />

        {/* 筛选栏（仅在浏览工坊时显示） */}
        {activeTab === 'browse' && renderFilterBar()}
      </div>

      {/* 滚动区域：只有卡片列表滚动 */}
      <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
        {activeTab === 'browse' && renderWorkshopList()}
        {activeTab === 'lorebook-preview' && renderLorebookPreview()}
        {activeTab === 'rag-preview' && renderRagPreview()}
        {activeTab === 'assembly-trace' && renderAssemblyTrace()}
        {activeTab === 'submissions' && renderMySubmissions()}
        {activeTab === 'admin' && renderAdminPanel()}
      </div>

      {/* 提交弹窗 */}
      <Modal
        title="分享提示词到工坊"
        open={isSubmitModalOpen}
        onCancel={() => {
          setIsSubmitModalOpen(false);
          submitForm.resetFields();
        }}
        footer={null}
        width={isMobile ? '100%' : 600}
        centered
      >
        <Alert
          type="info"
          message="提交须知"
          description="您的提示词将提交给管理员审核，审核通过后会在工坊中展示。请确保内容原创且不含敏感信息。"
          style={{ marginBottom: 16 }}
          showIcon
        />
        
        <Form
          form={submitForm}
          layout="vertical"
          onFinish={handleSubmit}
        >
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '请输入名称' }]}
          >
            <Input placeholder="给您的提示词起个名字" maxLength={50} />
          </Form.Item>
          
          <Form.Item
            name="category"
            label="分类"
            rules={[{ required: true, message: '请选择分类' }]}
          >
            <Select placeholder="选择分类">
              {categoryOptions.map(cat => (
                <Select.Option key={cat.value} value={cat.value}>{cat.label}</Select.Option>
              ))}
            </Select>
          </Form.Item>
          
          <Form.Item name="description" label="描述">
            <TextArea rows={2} placeholder="简要描述这个提示词的用途和效果" maxLength={200} />
          </Form.Item>
          
          <Form.Item
            name="prompt_content"
            label="提示词内容"
            rules={[{ required: true, message: '请输入提示词内容' }]}
          >
            <TextArea rows={6} placeholder="输入完整的提示词内容..." />
          </Form.Item>
          
          <Form.Item
            name="author_display_name"
            label="作者署名"
            rules={[{ required: true, message: '请输入作者署名' }]}
            tooltip="发布后显示的作者名称"
          >
            <Input placeholder="请输入作者署名（必填）" maxLength={50} />
          </Form.Item>
          
          <Form.Item name="tags" label="标签">
            <Input placeholder="输入标签，多个用逗号分隔，如: 武侠,对话,细腻" />
          </Form.Item>
          
          <Form.Item>
            <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
              <Button onClick={() => {
                setIsSubmitModalOpen(false);
                submitForm.resetFields();
              }}>
                取消
              </Button>
              <Button type="primary" htmlType="submit" loading={submitLoading}>
                提交审核
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* 详情弹窗 */}
      <Modal
        title={detailItem?.name}
        open={isDetailModalOpen}
        onCancel={() => {
          setIsDetailModalOpen(false);
          setDetailItem(null);
        }}
        footer={[
          <Button key="close" onClick={() => setIsDetailModalOpen(false)}>
            关闭
          </Button>,
          <Button
            key="import"
            type="primary"
            icon={<DownloadOutlined />}
            loading={importingId === detailItem?.id}
            onClick={() => detailItem && handleImport(detailItem)}
          >
            导入到本地
          </Button>,
        ]}
        width={isMobile ? '100%' : 700}
        centered
      >
        {detailItem && (
          <div>
            <Space style={{ marginBottom: 16 }} wrap>
              <Tag color={getCategoryColor(detailItem.category)}>
                {getCategoryName(detailItem.category)}
              </Tag>
              {detailItem.tags?.map(tag => (
                <Tag key={tag}>{tag}</Tag>
              ))}
            </Space>
            
            {detailItem.description && (
              <Paragraph style={{ marginBottom: 16 }}>
                {detailItem.description}
              </Paragraph>
            )}
            
            <div style={{
              backgroundColor: token.colorFillSecondary,
              padding: 16,
              borderRadius: 8,
              marginBottom: 16,
              maxHeight: 400,
              overflow: 'auto',
            }}>
              <Text strong style={{ display: 'block', marginBottom: 8 }}>提示词内容</Text>
              <pre style={{
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                margin: 0,
                fontSize: 13,
              }}>
                {detailItem.prompt_content}
              </pre>
            </div>
            
            <Row gutter={16}>
              <Col span={8}>
                <Text type="secondary">作者</Text>
                <div><UserOutlined /> {detailItem.author_name || '匿名'}</div>
              </Col>
              <Col span={8}>
                <Text type="secondary">点赞</Text>
                <div><HeartOutlined /> {detailItem.like_count || 0}</div>
              </Col>
              <Col span={8}>
                <Text type="secondary">下载</Text>
                <div><DownloadOutlined /> {detailItem.download_count || 0}</div>
              </Col>
            </Row>
          </div>
        )}
      </Modal>
      {/* 审核弹窗 */}
      <Modal
        title={`审核: ${reviewingSubmission?.name}`}
        open={reviewModalOpen}
        onCancel={() => {
          setReviewModalOpen(false);
          setReviewingSubmission(null);
          reviewForm.resetFields();
        }}
        footer={null}
        width={700}
        centered
      >
        {reviewingSubmission && (
          <div>
            <div style={{
              backgroundColor: token.colorFillSecondary,
              padding: 16,
              borderRadius: 8,
              marginBottom: 16,
              maxHeight: 300,
              overflow: 'auto',
            }}>
              <Text strong style={{ display: 'block', marginBottom: 8 }}>提示词内容预览</Text>
              <pre style={{
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                margin: 0,
                fontSize: 13,
              }}>
                {reviewingSubmission.prompt_content}
              </pre>
            </div>
            
            <Form form={reviewForm} layout="vertical">
              <Form.Item name="category" label="分类（可修改）">
                <Select>
                  {categoryOptions.map(cat => (
                    <Select.Option key={cat.value} value={cat.value}>{cat.label}</Select.Option>
                  ))}
                </Select>
              </Form.Item>
              
              <Form.Item name="tags" label="标签（可修改，逗号分隔）">
                <Input placeholder="武侠, 对话, 细腻" />
              </Form.Item>
              
              <Form.Item name="review_note" label="审核备注">
                <TextArea rows={2} placeholder="拒绝时请填写原因..." />
              </Form.Item>
              
              <Form.Item>
                <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
                  <Button onClick={() => setReviewModalOpen(false)}>
                    取消
                  </Button>
                  <Button danger loading={reviewLoading} onClick={() => handleReview('reject')}>
                    拒绝
                  </Button>
                  <Button type="primary" loading={reviewLoading} onClick={() => handleReview('approve')}>
                    通过
                  </Button>
                </Space>
              </Form.Item>
            </Form>
          </div>
        )}
      </Modal>

      {/* 添加官方提示词弹窗 */}
      <Modal
        title="添加官方提示词"
        open={addOfficialModalOpen}
        onCancel={() => {
          setAddOfficialModalOpen(false);
          addOfficialForm.resetFields();
        }}
        footer={null}
        width={600}
        centered
      >
        <Form
          form={addOfficialForm}
          layout="vertical"
          onFinish={handleAddOfficial}
        >
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '请输入名称' }]}
          >
            <Input placeholder="提示词名称" maxLength={50} />
          </Form.Item>
          
          <Form.Item
            name="category"
            label="分类"
            rules={[{ required: true, message: '请选择分类' }]}
          >
            <Select placeholder="选择分类">
              {categoryOptions.map(cat => (
                <Select.Option key={cat.value} value={cat.value}>{cat.label}</Select.Option>
              ))}
            </Select>
          </Form.Item>
          
          <Form.Item name="description" label="描述">
            <TextArea rows={2} placeholder="简要描述" maxLength={200} />
          </Form.Item>
          
          <Form.Item
            name="prompt_content"
            label="提示词内容"
            rules={[{ required: true, message: '请输入提示词内容' }]}
          >
            <TextArea rows={8} placeholder="输入完整的提示词内容..." />
          </Form.Item>
          
          <Form.Item name="tags" label="标签">
            <Input placeholder="逗号分隔，如: 武侠,对话,细腻" />
          </Form.Item>
          
          <Form.Item>
            <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
              <Button onClick={() => {
                setAddOfficialModalOpen(false);
                addOfficialForm.resetFields();
              }}>
                取消
              </Button>
              <Button type="primary" htmlType="submit" loading={addOfficialLoading}>
                添加
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* 编辑提示词弹窗 */}
      <Modal
        title={`编辑: ${editingItem?.name}`}
        open={editModalOpen}
        onCancel={() => {
          setEditModalOpen(false);
          setEditingItem(null);
          editForm.resetFields();
        }}
        footer={null}
        width={600}
        centered
      >
        <Form
          form={editForm}
          layout="vertical"
          onFinish={handleEditItem}
        >
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '请输入名称' }]}
          >
            <Input placeholder="提示词名称" maxLength={50} />
          </Form.Item>
          
          <Form.Item
            name="category"
            label="分类"
            rules={[{ required: true, message: '请选择分类' }]}
          >
            <Select placeholder="选择分类">
              {categoryOptions.map(cat => (
                <Select.Option key={cat.value} value={cat.value}>{cat.label}</Select.Option>
              ))}
            </Select>
          </Form.Item>
          
          <Form.Item name="description" label="描述">
            <TextArea rows={2} placeholder="简要描述" maxLength={200} />
          </Form.Item>
          
          <Form.Item
            name="prompt_content"
            label="提示词内容"
            rules={[{ required: true, message: '请输入提示词内容' }]}
          >
            <TextArea rows={8} placeholder="输入完整的提示词内容..." />
          </Form.Item>
          
          <Form.Item name="tags" label="标签">
            <Input placeholder="逗号分隔，如: 武侠,对话,细腻" />
          </Form.Item>
          
          <Form.Item>
            <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
              <Button onClick={() => {
                setEditModalOpen(false);
                setEditingItem(null);
                editForm.resetFields();
              }}>
                取消
              </Button>
              <Button type="primary" htmlType="submit" loading={editLoading}>
                保存修改
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
