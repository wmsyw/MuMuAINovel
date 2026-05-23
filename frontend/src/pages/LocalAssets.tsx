import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Image,
  Input,
  Popconfirm,
  Row,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
  Upload,
  message as antdMessage,
  theme,
} from 'antd';
import type { UploadFile } from 'antd/es/upload/interface';
import {
  CloudUploadOutlined,
  DeleteOutlined,
  FileImageOutlined,
  PictureOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import { projectAssetApi } from '../services/api';
import type { ProjectAsset, ProjectAssetType } from '../types';

const { Dragger } = Upload;
const { Paragraph, Text, Title } = Typography;

const ASSET_TYPE_OPTIONS: Array<{ label: string; value: ProjectAssetType; tag: string }> = [
  { label: '头像 Avatar', value: 'avatar', tag: '头像' },
  { label: '背景 Background', value: 'background', tag: '背景' },
  { label: '立绘 Sprite', value: 'sprite', tag: '立绘' },
];

function assetTypeLabel(assetType: string): string {
  return ASSET_TYPE_OPTIONS.find(option => option.value === assetType)?.tag || assetType;
}

function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) {
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
  if (bytes >= 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${bytes} B`;
}

function formatDate(value?: string | null): string {
  if (!value) return '-';
  return new Date(value).toLocaleString('zh-CN');
}

export default function LocalAssets() {
  const { projectId } = useParams<{ projectId: string }>();
  const { token } = theme.useToken();

  const [assets, setAssets] = useState<ProjectAsset[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [assetType, setAssetType] = useState<ProjectAssetType>('avatar');
  const [filterType, setFilterType] = useState<ProjectAssetType | undefined>();
  const [displayName, setDisplayName] = useState('');
  const [fileList, setFileList] = useState<UploadFile[]>([]);

  const previewHeight = token.controlHeightLG * 4;
  const typeCounts = useMemo(() => {
    return ASSET_TYPE_OPTIONS.reduce<Record<ProjectAssetType, number>>((acc, option) => {
      acc[option.value] = assets.filter(asset => asset.asset_type === option.value).length;
      return acc;
    }, { avatar: 0, background: 0, sprite: 0 });
  }, [assets]);

  const loadAssets = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const response = await projectAssetApi.list(projectId, filterType ? { asset_type: filterType } : undefined);
      setAssets(response.items);
    } catch (err) {
      console.error('加载本地资源失败:', err);
      setError('本地资源暂时不可用，可能是当前账号无权访问该项目。');
      setAssets([]);
    } finally {
      setLoading(false);
    }
  }, [projectId, filterType]);

  useEffect(() => {
    loadAssets();
  }, [loadAssets]);

  const selectedFile = fileList[0]?.originFileObj as File | undefined;

  const handleUpload = async () => {
    if (!projectId) return;
    if (!selectedFile) {
      antdMessage.warning('请选择一个本地图片文件');
      return;
    }
    setUploading(true);
    setError(null);
    try {
      await projectAssetApi.upload(projectId, {
        asset_type: assetType,
        display_name: displayName.trim() || undefined,
        file: selectedFile,
      });
      antdMessage.success('本地资源已上传');
      setFileList([]);
      setDisplayName('');
      await loadAssets();
    } catch (err) {
      console.error('上传本地资源失败:', err);
      setError('上传失败：仅支持本地图片文件，文件名、扩展名、MIME、大小和项目权限都会由服务端校验。');
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (asset: ProjectAsset) => {
    if (!projectId) return;
    try {
      await projectAssetApi.deleteAsset(projectId, asset.id);
      setAssets(prev => prev.filter(item => item.id !== asset.id));
      antdMessage.success('本地资源已删除');
    } catch (err) {
      console.error('删除本地资源失败:', err);
      antdMessage.error('删除失败');
    }
  };

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', gap: token.paddingMD }}>
      <Card>
        <Space align="start" style={{ width: '100%', justifyContent: 'space-between' }} wrap>
          <Space direction="vertical" size={token.marginXXS}>
            <Space>
              <PictureOutlined style={{ color: token.colorPrimary, fontSize: token.fontSizeHeading3 }} />
              <Title level={3} style={{ margin: 0 }}>本地资源</Title>
            </Space>
            <Paragraph type="secondary" style={{ marginBottom: 0 }}>
              为当前项目保存头像、背景和立绘等本地图片。资源只从本机上传，不支持远程URL导入；文件名会归一化为服务端生成路径，不与角色身份绑定。
            </Paragraph>
          </Space>
          <Space wrap>
            <Tag icon={<SafetyCertificateOutlined />} color="green">本地上传</Tag>
            <Tag color="blue">图片资源 {assets.length}</Tag>
            <Button icon={<ReloadOutlined />} onClick={loadAssets} loading={loading}>刷新</Button>
          </Space>
        </Space>
      </Card>

      {error && <Alert type="warning" showIcon message={error} />}

      <Row gutter={[token.marginMD, token.marginMD]} style={{ flex: 1, minHeight: 0 }}>
        <Col xs={24} xl={8} style={{ minHeight: 0 }}>
          <Card title="上传安全资源" style={{ height: '100%', overflow: 'hidden' }} bodyStyle={{ height: 'calc(100% - 57px)', overflow: 'auto' }}>
            <Space direction="vertical" size={token.marginMD} style={{ width: '100%' }}>
              <Alert
                type="info"
                showIcon
                message="服务端安全校验"
                description="仅接受 PNG/JPG/GIF/WEBP 图片；服务端会校验扩展名、MIME、文件头、大小、路径归一化和项目归属。"
              />
              <Space direction="vertical" size={token.marginXS} style={{ width: '100%' }}>
                <Text strong>资源类型</Text>
                <Select<ProjectAssetType>
                  value={assetType}
                  onChange={setAssetType}
                  options={ASSET_TYPE_OPTIONS.map(({ label, value }) => ({ label, value }))}
                  style={{ width: '100%' }}
                />
              </Space>
              <Space direction="vertical" size={token.marginXS} style={{ width: '100%' }}>
                <Text strong>展示名称（可选）</Text>
                <Input
                  maxLength={200}
                  value={displayName}
                  onChange={event => setDisplayName(event.target.value)}
                  placeholder="例如：雨夜窗景 / 少年主角头像"
                />
              </Space>
              <Dragger
                accept="image/png,image/jpeg,image/gif,image/webp"
                maxCount={1}
                multiple={false}
                fileList={fileList}
                beforeUpload={() => false}
                onChange={({ fileList: nextFileList }) => setFileList(nextFileList.slice(-1))}
              >
                <p className="ant-upload-drag-icon"><CloudUploadOutlined /></p>
                <p className="ant-upload-text">拖入或点击选择本地图片</p>
                <p className="ant-upload-hint">不填写URL，不拉取远程文件；上传后由项目/用户目录隔离保存。</p>
              </Dragger>
              <Button type="primary" icon={<FileImageOutlined />} block loading={uploading} onClick={handleUpload}>
                上传到资源库
              </Button>
            </Space>
          </Card>
        </Col>

        <Col xs={24} xl={16} style={{ minHeight: 0 }}>
          <Card
            title="项目资源库"
            extra={(
              <Select<ProjectAssetType>
                allowClear
                placeholder="全部类型"
                value={filterType}
                onChange={setFilterType}
                options={ASSET_TYPE_OPTIONS.map(({ label, value }) => ({ label, value }))}
                style={{ minWidth: token.controlHeightLG * 4 }}
              />
            )}
            style={{ height: '100%', overflow: 'hidden' }}
            bodyStyle={{ height: 'calc(100% - 57px)', overflow: 'auto' }}
          >
            <Space wrap style={{ marginBottom: token.marginMD }}>
              {ASSET_TYPE_OPTIONS.map(option => (
                <Tag key={option.value}>{option.tag} {typeCounts[option.value]}</Tag>
              ))}
            </Space>
            {loading ? (
              <div style={{ minHeight: previewHeight, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Spin />
              </div>
            ) : assets.length === 0 ? (
              <Empty description="暂无本地资源" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <Row gutter={[token.marginMD, token.marginMD]}>
                {assets.map(asset => (
                  <Col xs={24} md={12} xxl={8} key={asset.id}>
                    <Card
                      hoverable
                      style={{
                        height: '100%',
                        borderRadius: token.borderRadiusLG,
                        borderColor: token.colorBorderSecondary,
                        boxShadow: token.boxShadowTertiary,
                        overflow: 'hidden',
                      }}
                      cover={(
                        <div style={{ background: token.colorFillQuaternary, height: previewHeight, overflow: 'hidden' }}>
                          <Image
                            src={asset.file_url}
                            alt={asset.display_name}
                            width="100%"
                            height={previewHeight}
                            style={{ objectFit: 'cover' }}
                          />
                        </div>
                      )}
                      actions={[
                        <Popconfirm
                          key="delete"
                          title="删除本地资源？"
                          description="文件会从项目本地存储中移除，不会影响角色资料。"
                          onConfirm={() => handleDelete(asset)}
                        >
                          <Button type="text" danger icon={<DeleteOutlined />}>删除</Button>
                        </Popconfirm>,
                      ]}
                    >
                      <Space direction="vertical" size={token.marginXXS} style={{ width: '100%' }}>
                        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                          <Text strong ellipsis style={{ maxWidth: '70%' }}>{asset.display_name}</Text>
                          <Tag>{assetTypeLabel(asset.asset_type)}</Tag>
                        </Space>
                        <Text type="secondary" ellipsis>{asset.original_filename}</Text>
                        <Space size={token.marginXS} wrap>
                          <Tag>{asset.mime_type}</Tag>
                          <Tag>{formatBytes(asset.file_size)}</Tag>
                        </Space>
                        <Text type="secondary">上传于 {formatDate(asset.created_at)}</Text>
                      </Space>
                    </Card>
                  </Col>
                ))}
              </Row>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
}
