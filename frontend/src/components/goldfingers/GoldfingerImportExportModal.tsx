import { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Divider, Empty, List, Modal, Space, Typography, Upload, message, theme } from 'antd';
import { DownloadOutlined, FileTextOutlined, ImportOutlined, UploadOutlined } from '@ant-design/icons';
import type { GoldfingerImportDryRunResult, GoldfingerImportPayload } from '../../types';
import { goldfingerApi } from '../../services/api';
import { GOLDFINGER_PAYLOAD_VERSION } from './constants';

const { Paragraph, Text } = Typography;

interface GoldfingerImportExportModalProps {
  open: boolean;
  projectId?: string;
  projectTitle?: string;
  onCancel: () => void;
  onImported: () => Promise<void> | void;
}

function parseImportPayload(text: string): GoldfingerImportPayload {
  const parsed = JSON.parse(text) as GoldfingerImportPayload;
  if (!parsed || typeof parsed !== 'object' || !Array.isArray(parsed.data)) {
    throw new Error('导入内容必须是包含 data 数组的金手指卡片 JSON');
  }
  return parsed;
}

function ValidationList({ title, items, type }: { title: string; items: Array<{ message: string; name?: string | null; index?: number | null }>; type: 'error' | 'warning' | 'info' }) {
  if (items.length === 0) return null;
  return (
    <Alert
      type={type}
      showIcon
      message={title}
      description={(
        <List
          size="small"
          dataSource={items}
          renderItem={(item) => (
            <List.Item style={{ padding: '2px 0' }}>
              <Text>
                {item.index !== null && item.index !== undefined ? `#${item.index + 1} ` : ''}
                {item.name ? `「${item.name}」` : ''}{item.message}
              </Text>
            </List.Item>
          )}
        />
      )}
      style={{ marginBottom: 12 }}
    />
  );
}

export default function GoldfingerImportExportModal({
  open,
  projectId,
  projectTitle,
  onCancel,
  onImported,
}: GoldfingerImportExportModalProps) {
  const { token } = theme.useToken();
  const [payloadText, setPayloadText] = useState('');
  const [parseError, setParseError] = useState<string | null>(null);
  const [dryRun, setDryRun] = useState<GoldfingerImportDryRunResult | null>(null);
  const [dryRunLoading, setDryRunLoading] = useState(false);
  const [importLoading, setImportLoading] = useState(false);
  const [exportLoading, setExportLoading] = useState(false);

  useEffect(() => {
    if (!open) {
      setPayloadText('');
      setParseError(null);
      setDryRun(null);
      setDryRunLoading(false);
      setImportLoading(false);
    }
  }, [open]);

  const localVersionWarning = useMemo(() => {
    if (!payloadText.trim()) return null;
    try {
      const payload = JSON.parse(payloadText) as Partial<GoldfingerImportPayload>;
      if (payload.version && payload.version !== GOLDFINGER_PAYLOAD_VERSION) {
        return `当前文件版本为 ${payload.version}，期望版本 ${GOLDFINGER_PAYLOAD_VERSION}`;
      }
    } catch {
      return null;
    }
    return null;
  }, [payloadText]);

  const handleDownload = async () => {
    if (!projectId) return;
    setExportLoading(true);
    try {
      await goldfingerApi.downloadExport(projectId, projectTitle);
      message.success('金手指卡片已导出');
    } finally {
      setExportLoading(false);
    }
  };

  const handleDryRun = async () => {
    if (!projectId) return;
    setDryRunLoading(true);
    setParseError(null);
    setDryRun(null);
    try {
      const payload = parseImportPayload(payloadText);
      const result = await goldfingerApi.dryRunImport(projectId, payload);
      setDryRun(result);
      if (result.valid) {
        message.success(`校验通过，可导入 ${result.creatable} 个金手指`);
      } else {
        message.warning(`校验未通过，请修正后再导入。期望版本 ${result.expected_version}`);
      }
    } catch (error) {
      const err = error as { message?: string };
      setParseError(err.message || `文件解析失败，请确认是 ${GOLDFINGER_PAYLOAD_VERSION} 格式`);
    } finally {
      setDryRunLoading(false);
    }
  };

  const handleImport = async () => {
    if (!projectId || !dryRun?.valid) return;
    setImportLoading(true);
    try {
      const payload = parseImportPayload(payloadText);
      const result = await goldfingerApi.importProject(projectId, payload);
      if (result.success) {
        message.success(result.message || `成功导入 ${result.imported} 个金手指`);
        await onImported();
        onCancel();
      } else {
        setDryRun(result.dry_run);
        message.warning(result.message || `导入前验证失败，期望版本 ${GOLDFINGER_PAYLOAD_VERSION}`);
      }
    } finally {
      setImportLoading(false);
    }
  };

  return (
    <Modal
      title="金手指导入 / 导出"
      open={open}
      onCancel={onCancel}
      width={760}
      footer={(
        <Space wrap>
          <Button onClick={onCancel}>关闭</Button>
          <Button icon={<DownloadOutlined />} loading={exportLoading} onClick={handleDownload}>导出当前项目</Button>
          <Button icon={<FileTextOutlined />} loading={dryRunLoading} onClick={handleDryRun} disabled={!payloadText.trim()}>Dry-run 校验</Button>
          <Button type="primary" icon={<ImportOutlined />} loading={importLoading} disabled={!dryRun?.valid} onClick={handleImport}>正式导入</Button>
        </Space>
      )}
    >
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <Alert
          type="info"
          showIcon
          message="导入格式要求"
          description={`仅支持 ${GOLDFINGER_PAYLOAD_VERSION}。请先执行 dry-run，确认无版本错误、字段错误或同名冲突后再正式导入。`}
        />

        <Upload
          accept="application/json,.json"
          maxCount={1}
          beforeUpload={async file => {
            const text = await file.text();
            setPayloadText(text);
            setDryRun(null);
            setParseError(null);
            return false;
          }}
          onRemove={() => {
            setPayloadText('');
            setDryRun(null);
          }}
        >
          <Button icon={<UploadOutlined />}>选择 JSON 文件</Button>
        </Upload>

        <div>
          <Text type="secondary">或直接粘贴导入载荷</Text>
          <textarea
            aria-label="金手指导入 JSON"
            value={payloadText}
            onChange={event => {
              setPayloadText(event.target.value);
              setDryRun(null);
              setParseError(null);
            }}
            placeholder={`{\n  "version": "${GOLDFINGER_PAYLOAD_VERSION}",\n  "export_type": "goldfingers",\n  "data": []\n}`}
            style={{
              width: '100%',
              minHeight: 180,
              marginTop: 8,
              padding: 12,
              border: `1px solid ${token.colorBorder}`,
              borderRadius: token.borderRadius,
              background: token.colorBgContainer,
              color: token.colorText,
              fontFamily: 'monospace',
            }}
          />
        </div>

        {localVersionWarning && <Alert type="warning" showIcon message="版本不匹配" description={`${localVersionWarning}，请使用 ${GOLDFINGER_PAYLOAD_VERSION}。`} />}
        {parseError && <Alert type="error" showIcon message="解析失败" description={`${parseError}；期望版本 ${GOLDFINGER_PAYLOAD_VERSION}`} />}

        <Divider style={{ margin: 0 }} />

        {!dryRun ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="等待 dry-run 校验结果" />
        ) : (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Alert
              type={dryRun.valid ? 'success' : 'error'}
              showIcon
              message={dryRun.valid ? '校验通过' : '校验未通过'}
              description={`版本：${dryRun.version || '缺失'}；期望版本：${dryRun.expected_version}；总数 ${dryRun.total}，可创建 ${dryRun.creatable}，冲突 ${dryRun.conflicts.length}，错误 ${dryRun.errors.length}`}
            />
            <ValidationList title="错误" items={dryRun.errors} type="error" />
            <ValidationList title="警告" items={dryRun.warnings} type="warning" />
            {dryRun.conflicts.length > 0 && (
              <Alert
                type="warning"
                showIcon
                message="同名冲突"
                description={(
                  <List
                    size="small"
                    dataSource={dryRun.conflicts}
                    renderItem={item => <List.Item style={{ padding: '2px 0' }}>#{item.index + 1} 「{item.name || '未命名'}」：{item.reason}</List.Item>}
                  />
                )}
              />
            )}
            {dryRun.would_create.length > 0 && (
              <Paragraph style={{ marginBottom: 0 }}>将创建：{dryRun.would_create.map(item => String(item.name || item.normalized_name)).join('、')}</Paragraph>
            )}
          </Space>
        )}
      </Space>
    </Modal>
  );
}
