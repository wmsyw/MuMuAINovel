import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Empty,
  Input,
  InputNumber,
  List,
  message,
  Popconfirm,
  Progress,
  Row,
  Select,
  Space,
  Spin,
  Steps,
  Tag,
  Typography,
  Upload,
  theme,
} from 'antd';
import type { UploadFile } from 'antd/es/upload/interface';
import { InboxOutlined, PlayCircleOutlined, ReloadOutlined, StopOutlined, WarningOutlined, RedoOutlined } from '@ant-design/icons';
import { bookImportApi } from '../services/api';
import type {
  BookImportApplyPayload,
  BookImportExtractMode,
  BookImportPreview,
  BookImportStepFailure,
  BookImportTask,
} from '../types';
import { useIsMobile } from '../hooks/useMediaQuery';
import { sx } from '../styles/sx';

const { Text, Title } = Typography;
const { Dragger } = Upload;
const { TextArea } = Input;

const BOOK_IMPORT_CACHE_KEY = 'book_import_page_cache_v1';

type BookImportPageCache = {
  taskId: string | null;
  taskStatus: BookImportTask | null;
  preview: BookImportPreview | null;
  applyProgress: number;
  applyMessage: string;
  applyError: string | null;
  isApplyComplete: boolean;
  extractMode: BookImportExtractMode;
  tailChapterCount: number;
  cachedAt: number;
};

function loadBookImportCache(): BookImportPageCache | null {
  try {
    const raw = sessionStorage.getItem(BOOK_IMPORT_CACHE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as BookImportPageCache;
  } catch (error) {
    console.warn('读取拆书页面缓存失败:', error);
    return null;
  }
}

function saveBookImportCache(cache: BookImportPageCache) {
  try {
    sessionStorage.setItem(BOOK_IMPORT_CACHE_KEY, JSON.stringify(cache));
  } catch (error) {
    const isQuotaExceeded =
      error instanceof DOMException &&
      (error.name === 'QuotaExceededError' || error.name === 'NS_ERROR_DOM_QUOTA_REACHED');

    if (isQuotaExceeded) {
      // 发生容量溢出时降级为轻量缓存（不保存预览正文），避免持续报错
      try {
        const lightweightCache: BookImportPageCache = {
          ...cache,
          preview: null,
        };
        sessionStorage.setItem(BOOK_IMPORT_CACHE_KEY, JSON.stringify(lightweightCache));
        return;
      } catch (fallbackError) {
        console.warn('写入轻量拆书页面缓存失败:', fallbackError);
        try {
          sessionStorage.removeItem(BOOK_IMPORT_CACHE_KEY);
        } catch {
          // ignore
        }
      }
    }

    console.warn('写入拆书页面缓存失败:', error);
  }
}

function clearBookImportCache() {
  try {
    sessionStorage.removeItem(BOOK_IMPORT_CACHE_KEY);
  } catch (error) {
    console.warn('清理拆书页面缓存失败:', error);
  }
}

function isNotFoundError(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false;
  const maybeError = error as { response?: { status?: number } };
  return maybeError.response?.status === 404;
}

export default function BookImport() {
  const navigate = useNavigate();
  const { token } = theme.useToken();
  const isMobile = useIsMobile();
  const [file, setFile] = useState<File | null>(null);
  const [extractMode, setExtractMode] = useState<BookImportExtractMode>('tail');
  const [tailChapterCount, setTailChapterCount] = useState(10);

  const [taskId, setTaskId] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState<BookImportTask | null>(null);
  const [preview, setPreview] = useState<BookImportPreview | null>(null);

  const [creatingTask, setCreatingTask] = useState(false);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [applying, setApplying] = useState(false);
  const [applyProgress, setApplyProgress] = useState(0);
  const [applyMessage, setApplyMessage] = useState('');
  const [applyError, setApplyError] = useState<string | null>(null);
  const [isApplyComplete, setIsApplyComplete] = useState(false);
  const [cacheReady, setCacheReady] = useState(false);

  // 步骤级失败和重试相关状态
  const [failedSteps, setFailedSteps] = useState<BookImportStepFailure[]>([]);
  const [retrying, setRetrying] = useState(false);
  const [retryProgress, setRetryProgress] = useState(0);
  const [retryMessage, setRetryMessage] = useState('');
  const importedProjectId = useRef<string | null>(null);

  const isTaskTerminal = useMemo(() => {
    return !!taskStatus && ['completed', 'failed', 'cancelled'].includes(taskStatus.status);
  }, [taskStatus]);

  const currentStep = useMemo(() => {
    if (!taskId) return 0;
    if (taskStatus && ['pending', 'running'].includes(taskStatus.status)) return 1;
    if (applying || isApplyComplete) return 3; // 新增生成导入步骤
    if (preview) return 2;
    return 1;
  }, [taskId, taskStatus, preview, applying, isApplyComplete]);

  const canRestart = useMemo(() => {
    return Boolean(
      file ||
      taskId ||
      taskStatus ||
      preview ||
      applyProgress > 0 ||
      applyMessage ||
      applyError ||
      isApplyComplete ||
      failedSteps.length > 0 ||
      retrying
    );
  }, [
    file,
    taskId,
    taskStatus,
    preview,
    applyProgress,
    applyMessage,
    applyError,
    isApplyComplete,
    failedSteps,
    retrying,
  ]);

  const normalizedTailChapterCount = useMemo(
    () => Math.max(5, Math.ceil(tailChapterCount / 5) * 5),
    [tailChapterCount]
  );
  const effectiveExtractMode = useMemo<BookImportExtractMode>(
    () => (normalizedTailChapterCount > 50 ? 'full' : extractMode),
    [extractMode, normalizedTailChapterCount]
  );
  const rangeLocked = Boolean(taskId || taskStatus || preview || creatingTask || applying || retrying);

  const stepItems = [
    { title: '上传文件' },
    { title: '解析中' },
    { title: '预览修改' },
    { title: '生成导入' },
  ];
  const currentStepText = stepItems[currentStep]?.title || '上传文件';

  useEffect(() => {
    const cache = loadBookImportCache();
    if (cache) {
      const cacheAgeMs = typeof cache.cachedAt === 'number'
        ? Date.now() - cache.cachedAt
        : Number.POSITIVE_INFINITY;

      // 超过6小时的缓存直接视为失效，避免后端重启后继续使用旧taskId
      if (cacheAgeMs > 6 * 60 * 60 * 1000) {
        clearBookImportCache();
      } else {
        setTaskId(cache.taskId);
        setTaskStatus(cache.taskStatus);
        setPreview(cache.preview);
        setApplyProgress(cache.applyProgress);
        setApplyError(cache.applyError);
        setIsApplyComplete(cache.isApplyComplete);
        setExtractMode(cache.extractMode ?? 'tail');
        setTailChapterCount(cache.tailChapterCount ?? 10);
        setApplyMessage(
          cache.applyMessage || (cache.applyProgress > 0 && !cache.isApplyComplete
            ? '已恢复页面缓存，请重新点击“确认导入”继续。'
            : '')
        );
        message.info('已恢复拆书导入页面缓存');
      }
    }
    setCacheReady(true);
  }, []);

  useEffect(() => {
    if (!cacheReady) return;

    // 导入完成后必须清理缓存，避免后续回到页面时恢复到旧任务状态
    if (isApplyComplete) {
      clearBookImportCache();
      return;
    }

    const hasCacheData = Boolean(
      taskId ||
      taskStatus ||
      preview ||
      applyError ||
      applyProgress > 0 ||
      applyMessage
    );

    if (!hasCacheData) {
      clearBookImportCache();
      return;
    }

    saveBookImportCache({
      taskId,
      taskStatus,
      // preview 含完整章节正文，体积大，容易触发 sessionStorage 配额限制
      // 页面恢复时可根据 taskId + taskStatus 重新拉取 preview
      preview: null,
      applyProgress,
      applyMessage,
      applyError,
      isApplyComplete,
      extractMode,
      tailChapterCount,
      cachedAt: Date.now(),
    });
  }, [
    cacheReady,
    taskId,
    taskStatus,
    preview,
    applyProgress,
    applyMessage,
    applyError,
    isApplyComplete,
    extractMode,
    tailChapterCount,
  ]);

  useEffect(() => {
    if (!taskId) return;
    if (isTaskTerminal) return;

    const timer = setInterval(async () => {
      try {
        const status = await bookImportApi.getTaskStatus(taskId);
        setTaskStatus(status);
      } catch (error) {
        console.error('轮询任务状态失败:', error);
        if (isNotFoundError(error)) {
          clearBookImportCache();
          setTaskId(null);
          setTaskStatus(null);
          setPreview(null);
          setApplyProgress(0);
          setApplyMessage('');
          setApplyError(null);
          setIsApplyComplete(false);
          message.warning('拆书任务已失效（可能因服务重启），请重新上传TXT并开始解析');
        }
      }
    }, 1500);

    return () => clearInterval(timer);
  }, [taskId, isTaskTerminal]);

  useEffect(() => {
    const fetchPreview = async () => {
      if (!taskId || !taskStatus) return;
      if (taskStatus.status !== 'completed' || preview) return;

      try {
        setLoadingPreview(true);
        const data = await bookImportApi.getPreview(taskId);
        setPreview(data);
      } catch (error) {
        console.error('获取预览失败:', error);
        if (isNotFoundError(error)) {
          clearBookImportCache();
          setTaskId(null);
          setTaskStatus(null);
          setPreview(null);
          setApplyProgress(0);
          setApplyMessage('');
          setApplyError(null);
          setIsApplyComplete(false);
          message.warning('拆书任务预览不存在（可能因服务重启），已清空缓存，请重新上传TXT');
        } else {
          message.error('获取预览失败');
        }
      } finally {
        setLoadingPreview(false);
      }
    };

    fetchPreview();
  }, [taskId, taskStatus, preview]);

  const startTask = async () => {
    if (!file) {
      message.warning('请先选择 TXT 文件');
      return;
    }

    try {
      setCreatingTask(true);
      setPreview(null);
      setTaskStatus(null);

      setExtractMode(effectiveExtractMode);
      setTailChapterCount(normalizedTailChapterCount);

      const response = await bookImportApi.createTask({
        file,
        extract_mode: effectiveExtractMode,
        tail_chapter_count: normalizedTailChapterCount,
      });

      setTaskId(response.task_id);
      message.success('拆书任务已创建');
    } catch (error) {
      console.error('创建任务失败:', error);
      message.error('创建拆书任务失败');
    } finally {
      setCreatingTask(false);
    }
  };

  const refreshStatus = async () => {
    if (!taskId) return;
    try {
      const status = await bookImportApi.getTaskStatus(taskId);
      setTaskStatus(status);
    } catch (error) {
      console.error('刷新状态失败:', error);
      if (isNotFoundError(error)) {
        clearBookImportCache();
        setTaskId(null);
        setTaskStatus(null);
        setPreview(null);
        setApplyProgress(0);
        setApplyMessage('');
        setApplyError(null);
        setIsApplyComplete(false);
        message.warning('任务不存在，已清空本地缓存，请重新创建拆书任务');
      }
    }
  };

  const cancelTask = async () => {
    if (!taskId) return;
    try {
      await bookImportApi.cancelTask(taskId);
      message.success('任务已取消');
      await refreshStatus();
    } catch (error) {
      console.error('取消任务失败:', error);
      message.error('取消任务失败');
    }
  };

  const applyImport = async () => {
    if (!taskId || !preview) return;

    const payload: BookImportApplyPayload = {
      project_suggestion: preview.project_suggestion,
      chapters: preview.chapters,
      outlines: preview.outlines,
      import_mode: 'append',
    };

    try {
      setApplying(true);
      setApplyProgress(0);
      setApplyMessage('准备导入...');
      setApplyError(null);
      setIsApplyComplete(false);
      setFailedSteps([]);

      await bookImportApi.applyImportStream(
        taskId,
        payload,
        {
          onProgress: (msg, prog, status) => {
            // 检查是否是步骤失败的特殊消息
            if (status === 'step_failures') {
              try {
                const parsed = JSON.parse(msg);
                if (parsed.failed_steps && Array.isArray(parsed.failed_steps)) {
                  setFailedSteps(parsed.failed_steps as BookImportStepFailure[]);
                }
              } catch {
                // 不是JSON，忽略
              }
              return;
            }
            setApplyProgress(prog);
            setApplyMessage(msg);
          },
          onResult: (result) => {
            importedProjectId.current = result.project_id;
            const generatedCareers = result.statistics?.generated_careers ?? 0;
            const generatedEntities = result.statistics?.generated_entities ?? 0;

            // 检查最终是否有失败步骤
            setIsApplyComplete(true);

            // 如果没有失败步骤才自动跳转
            // 注意：这里需要延迟一帧来等待 failedSteps 的更新
            setTimeout(() => {
              setFailedSteps(prev => {
                if (prev.length === 0) {
                  message.success(`导入成功：已生成职业${generatedCareers}个，角色/组织${generatedEntities}个`);
                  clearBookImportCache();
                  setTimeout(() => {
                    navigate(`/project/${result.project_id}/chapters`);
                  }, 1000);
                } else {
                  message.warning(`导入完成，但有 ${prev.length} 个生成步骤失败，可点击重试`);
                }
                return prev;
              });
            }, 100);
          },
          onError: (error) => {
            console.error('导入过程发生错误:', error);
            setApplyError(`导入失败: ${error}`);
            message.error(`导入失败: ${error}`);
            setApplying(false);
          },
          onComplete: () => {
            setApplyProgress(100);
            setApplyMessage('导入完成！');
          }
        }
      );
    } catch (error) {
      console.error('确认导入失败:', error);
      setApplyError('确认导入失败，无法连接到服务器');
      message.error('确认导入失败');
      setApplying(false);
    }
  };

  const retryFailedSteps = useCallback(async () => {
    if (!taskId || failedSteps.length === 0) return;

    const stepsToRetry = failedSteps.map(f => f.step_name);

    try {
      setRetrying(true);
      setRetryProgress(0);
      setRetryMessage('正在重试失败的生成步骤...');

      await bookImportApi.retryFailedStepsStream(
        taskId,
        stepsToRetry,
        {
          onProgress: (msg, prog, status) => {
            if (status === 'step_failures') {
              try {
                const parsed = JSON.parse(msg);
                if (parsed.failed_steps && Array.isArray(parsed.failed_steps)) {
                  setFailedSteps(parsed.failed_steps as BookImportStepFailure[]);
                }
              } catch {
                // 不是JSON，忽略
              }
              return;
            }
            setRetryProgress(prog);
            setRetryMessage(msg);
          },
          onResult: (result) => {
            if (result.still_failed && result.still_failed.length > 0) {
              setFailedSteps(result.still_failed);
              message.warning(`重试完成，仍有 ${result.still_failed.length} 个步骤失败`);
            } else {
              setFailedSteps([]);
              message.success('所有步骤重试成功！');
              clearBookImportCache();
              const projectId = result.project_id || importedProjectId.current;
              if (projectId) {
                setTimeout(() => {
                  navigate(`/project/${projectId}/chapters`);
                }, 1000);
              }
            }
          },
          onError: (error) => {
            console.error('重试失败:', error);
            message.error(`重试失败: ${error}`);
          },
          onComplete: () => {
            setRetrying(false);
            setRetryProgress(100);
            setRetryMessage('重试完成');
          }
        }
      );
    } catch (error) {
      console.error('重试请求失败:', error);
      message.error('重试请求失败，无法连接到服务器');
      setRetrying(false);
    }
  }, [taskId, failedSteps, navigate]);

  const skipFailedSteps = useCallback(() => {
    setFailedSteps([]);
    clearBookImportCache();
    const projectId = importedProjectId.current;
    if (projectId) {
      message.info('已跳过失败步骤，正在跳转到项目...');
      navigate(`/project/${projectId}/chapters`);
    }
  }, [navigate]);

  const restartImport = useCallback(() => {
    clearBookImportCache();
    importedProjectId.current = null;

    setFile(null);
    setTaskId(null);
    setTaskStatus(null);
    setPreview(null);

    setCreatingTask(false);
    setLoadingPreview(false);
    setApplying(false);
    setApplyProgress(0);
    setApplyMessage('');
    setApplyError(null);
    setIsApplyComplete(false);

    setFailedSteps([]);
    setRetrying(false);
    setRetryProgress(0);
    setRetryMessage('');
    setExtractMode('tail');
    setTailChapterCount(10);

    message.success('已重新开始，请重新上传 TXT 并解析');
  }, []);

  const updateChapter = (index: number, patch: Partial<BookImportPreview['chapters'][number]>) => {
    setPreview(prev => {
      if (!prev) return prev;
      const next = [...prev.chapters];
      next[index] = { ...next[index], ...patch };
      return { ...prev, chapters: next };
    });
  };

  return (
    <div
      className={sx({
        minHeight: '90vh',
        overflow: 'auto',
        background: `linear-gradient(180deg, ${token.colorBgLayout} 0%, ${token.colorFillSecondary} 100%)`,
        padding: isMobile ? '20px 16px 70px' : '24px 24px 70px',
      })}
    >
      <div className="u-nsav5t">
        <Card
          variant="borderless"
          className={sx({
            background: `linear-gradient(135deg, ${token.colorPrimary} 0%, ${token.colorPrimaryHover} 100%)`,
            borderRadius: isMobile ? 16 : 20,
            boxShadow: token.boxShadowSecondary,
            marginBottom: isMobile ? 14 : 16,
            border: 'none',
            position: 'relative',
            overflow: 'hidden',
          })}
        >
          <div className={sx({ position: 'absolute', top: -48, right: -48, width: 160, height: 160, borderRadius: '50%', background: token.colorWhite, opacity: 0.08, pointerEvents: 'none' })} />
          <div className={sx({ position: 'absolute', bottom: -40, left: '26%', width: 110, height: 110, borderRadius: '50%', background: token.colorWhite, opacity: 0.05, pointerEvents: 'none' })} />

          <Row align="middle" justify="space-between" gutter={[16, 16]} className="u-5dyu45">
            <Col xs={24} sm={12}>
              <Space direction="vertical" size={4}>
                <Title level={isMobile ? 3 : 2} className={sx({ margin: 0, color: token.colorWhite, textShadow: `0 2px 4px ${token.colorBgMask}` })}>
                  <InboxOutlined className={sx({ color: token.colorWhite, opacity: 0.9, marginRight: 8 })} />
                  拆书导入
                </Title>
                <Text className={sx({ fontSize: isMobile ? 12 : 14, color: token.colorTextLightSolid, opacity: 0.85, marginLeft: isMobile ? 40 : 48 })}>
                  上传TXT并自动解析为章节、预览并导入项目
                </Text>
              </Space>
            </Col>
            <Col xs={24} sm={12}>
              <Space
                size={12}
                className={sx({
                  width: '100%',
                  display: 'flex',
                  justifyContent: isMobile ? 'flex-start' : 'flex-end',
                })}
              >
                <Tag
                  className={sx({
                    marginInlineEnd: 0,
                    background: token.colorWhite,
                    border: `1px solid ${token.colorWhite}`,
                    color: token.colorPrimary,
                    fontWeight: 600,
                    borderRadius: 8,
                    paddingInline: 10,
                  })}
                >
                  当前进度：{currentStepText}
                </Tag>
                <Popconfirm
                  title="确认重新开始？"
                  description="将清空当前拆书任务与缓存，并回到上传文件步骤。"
                  onConfirm={restartImport}
                  okText="重新开始"
                  cancelText="取消"
                  disabled={!canRestart}
                >
                  <Button
                    danger
                    type="primary"
                    icon={<ReloadOutlined />}
                    disabled={!canRestart}
                    className="u-1cqqb6m"
                  >
                    重新开始
                  </Button>
                </Popconfirm>
              </Space>
            </Col>
          </Row>

          <Card
            variant="borderless"
            className={sx({
              marginTop: isMobile ? 14 : 18,
              borderRadius: 12,
              background: token.colorBgContainer,
              border: `1px solid ${token.colorBorderSecondary}`,
              boxShadow: token.boxShadow,
            })}
            styles={{ body: { padding: isMobile ? '10px 12px' : '12px 16px' } }}
          >
            <Steps current={currentStep} size={isMobile ? 'small' : 'default'} items={stepItems} />
          </Card>
        </Card>

      {currentStep === 0 && (
      <Card title="上传 TXT 并开始解析" className="u-6srbul">
        <Space direction="vertical" className="u-1f3r3s" size={16}>
          <Dragger
            accept=".txt"
            multiple={false}
            beforeUpload={(f) => {
              setFile(f);
              return false;
            }}
            onRemove={() => {
              setFile(null);
            }}
            fileList={
              file
                ? [
                    {
                      uid: 'selected-txt',
                      name: file.name,
                      status: 'done',
                    } as UploadFile,
                  ]
                : []
            }
            className="u-15tlmef"
          >
            <p className="ant-upload-drag-icon">
              <InboxOutlined />
            </p>
            <p className="ant-upload-text">点击或拖拽 TXT 文件到此区域</p>
            <p className="ant-upload-hint">首版仅支持 .txt，建议不超过 50MB</p>
          </Dragger>

          <Card size="small" title="解析范围设置">
            <Space direction="vertical" className="u-1f3r3s" size={12}>
              {rangeLocked && (
                <Alert
                  type="warning"
                  showIcon
                  message="当前任务的解析范围已锁定"
                  description="拆书任务会按创建任务时的解析范围执行。若需修改范围，请点击上方“重新开始”后重新上传并解析。"
                />
              )}
              <Select
                value={extractMode}
                onChange={(value) => setExtractMode(value)}
                options={[
                  { label: '截取末 x 章反向生成', value: 'tail' },
                  { label: '整本反向生成', value: 'full' },
                ]}
                className="u-1f3r3s"
                disabled={rangeLocked}
              />
              <InputNumber
                min={5}
                max={55}
                step={5}
                precision={0}
                value={tailChapterCount}
                disabled={rangeLocked || extractMode !== 'tail'}
                onChange={(value) => setTailChapterCount(typeof value === 'number' ? value : 10)}
                addonBefore="末尾章节数"
                className="u-1f3r3s"
              />
              <Text type="secondary">
                {effectiveExtractMode === 'tail'
                  ? `当前将截取末 ${normalizedTailChapterCount} 章进行反向生成；章节数必须为 5 的倍数，最多 50 章。`
                  : extractMode === 'tail' && tailChapterCount > 50
                    ? '当前输入已超过 50 章，将自动按整本拆处理。'
                    : '当前将基于整本内容进行反向生成，适合完整拆书但耗时可能更长。'}
              </Text>
            </Space>
          </Card>

          <Alert
            type="info"
            showIcon
            message="支持的拆书 TXT 格式要求"
            description={
              <div className="u-1ezb7ed">
                <div>1. 仅支持 <strong>.txt</strong> 文件，建议每章使用单独的章节标题行。</div>
                <div>2. 推荐格式：<strong>第1章 标题</strong>，下一行开始写正文内容。</div>
                <div>3. 正文建议按自然段换行，首行可缩进两个字符。</div>
                <div>4. 章节之间保留空行即可，不要添加多余的分割线、全文完、导出时间等干扰内容。</div>
                <div className="u-u35y5u">
                  示例：
                  <pre className={sx({ margin: '8px 0 0', padding: 12, borderRadius: 8, background: token.colorFillAlter, whiteSpace: 'pre-wrap' })}>
{`第1章 初入江湖
这里是第1章正文第一段。
这里是第1章正文第二段。

第2章 雨夜追踪
这里是第2章正文内容。`}
                  </pre>
                </div>
              </div>
            }
          />
          
          <Space wrap>
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              loading={creatingTask}
              onClick={startTask}
            >
              开始解析
            </Button>
            {taskId && (
              <Tag color="blue">任务ID: {taskId}</Tag>
            )}
          </Space>
        </Space>
      </Card>
      )}

      {currentStep === 1 && (
      <Card title="解析任务状态" className="u-6srbul">
        {!taskId ? (
          <Empty description="尚未创建任务" />
        ) : (
          <div className="u-1iz3svh">
            <Progress
              type="circle"
              percent={taskStatus?.progress || 0}
              status={
                taskStatus?.status === 'failed' ? 'exception' :
                taskStatus?.status === 'completed' ? 'success' :
                'active'
              }
            />
            <div className="u-1xr8872">
              <Text strong className="u-tw6n7q">
                {taskStatus?.status === 'pending' && '等待调度...'}
                {taskStatus?.status === 'running' && '正在解析TXT文件...'}
                {taskStatus?.status === 'completed' && '解析完成！正在生成预览...'}
                {taskStatus?.status === 'failed' && '解析失败'}
                {taskStatus?.status === 'cancelled' && '已取消'}
              </Text>
              {taskStatus?.message && (
                <div className="u-u35y5u">
                  <Text type="secondary">{taskStatus.message}</Text>
                </div>
              )}
            </div>

            {taskStatus?.error && (
              <Alert type="error" message={taskStatus.error} showIcon className="u-1ve3etn" />
            )}

            <Space className="u-1xr8872">
              <Button icon={<ReloadOutlined />} onClick={refreshStatus}>刷新状态</Button>
              {taskStatus && ['pending', 'running'].includes(taskStatus.status) && (
                <Button danger icon={<StopOutlined />} onClick={cancelTask}>取消任务</Button>
              )}
            </Space>
          </div>
        )}
      </Card>
      )}

      {currentStep === 2 && (
      <>
      <Card
        title="预览修正"
        extra={
          <Button
            type="primary"
            loading={applying}
            disabled={!preview}
            onClick={applyImport}
          >
            确认导入
          </Button>
        }
        className="u-6srbul"
      >
        <Spin spinning={loadingPreview}>
          {!preview ? (
            <Empty description="解析完成后将显示预览数据" />
          ) : (
            <div className="u-1k1r8vr">
              <Space direction="vertical" className="u-1f3r3s" size={16}>
              {preview.warnings.length > 0 && (
                <Alert
                  type="warning"
                  showIcon
                  message="检测到告警"
                  description={
                    <ul className="u-1ou6caz">
                      {preview.warnings.map((w, idx) => (
                        <li key={`${w.code}-${idx}`}>[{w.level}] {w.message}</li>
                      ))}
                    </ul>
                  }
                />
              )}

              <Card
                size="small"
                title="项目信息"
              >
                <Row gutter={12}>
                  <Col xs={24} md={12}>
                    <Text>标题</Text>
                    <Input
                      value={preview.project_suggestion.title}
                      onChange={(e) =>
                        setPreview(prev => prev ? ({
                          ...prev,
                          project_suggestion: { ...prev.project_suggestion, title: e.target.value },
                        }) : prev)
                      }
                    />
                  </Col>
                  <Col xs={24} md={12}>
                    <Text>类型</Text>
                    <Input
                      value={preview.project_suggestion.genre}
                      onChange={(e) =>
                        setPreview(prev => prev ? ({
                          ...prev,
                          project_suggestion: { ...prev.project_suggestion, genre: e.target.value },
                        }) : prev)
                      }
                    />
                  </Col>
                  <Col xs={24}>
                    <Text>主题</Text>
                    <TextArea
                      rows={3}
                      value={preview.project_suggestion.theme}
                      onChange={(e) =>
                        setPreview(prev => prev ? ({
                          ...prev,
                          project_suggestion: { ...prev.project_suggestion, theme: e.target.value },
                        }) : prev)
                      }
                    />
                  </Col>
                  <Col xs={24}>
                    <Text>简介</Text>
                    <TextArea
                      rows={3}
                      value={preview.project_suggestion.description}
                      onChange={(e) =>
                        setPreview(prev => prev ? ({
                          ...prev,
                          project_suggestion: { ...prev.project_suggestion, description: e.target.value },
                        }) : prev)
                      }
                    />
                  </Col>
                  <Col xs={24} md={12}>
                    <Text>叙事角度</Text>
                    <Select
                      className="u-1f3r3s"
                      value={preview.project_suggestion.narrative_perspective}
                      onChange={(v) =>
                        setPreview(prev => prev ? ({
                          ...prev,
                          project_suggestion: { ...prev.project_suggestion, narrative_perspective: v },
                        }) : prev)
                      }
                      options={[
                        { value: '第一人称', label: '第一人称' },
                        { value: '第三人称', label: '第三人称' },
                        { value: '全知视角', label: '全知视角' },
                      ]}
                    />
                  </Col>
                  <Col xs={24} md={12}>
                    <Text>目标字数</Text>
                    <InputNumber
                      className="u-1f3r3s"
                      min={1000}
                      step={1000}
                      value={preview.project_suggestion.target_words}
                      onChange={(v) =>
                        setPreview(prev => prev ? ({
                          ...prev,
                          project_suggestion: {
                            ...prev.project_suggestion,
                            target_words: Number(v || 100000),
                          },
                        }) : prev)
                      }
                    />
                  </Col>
                </Row>
              </Card>

              <Card size="small" title={`章节（${preview.chapters.length}）`}>
                <Collapse
                  items={preview.chapters.map((ch, idx) => ({
                    key: String(idx),
                    label: `第 ${ch.chapter_number} 章 · ${ch.title}`,
                    children: (
                      <Space direction="vertical" className="u-1f3r3s">
                        <Input
                          value={ch.title}
                          addonBefore="标题"
                          onChange={(e) => updateChapter(idx, { title: e.target.value })}
                        />
                        <TextArea
                          rows={2}
                          value={ch.summary}
                          placeholder="章节摘要"
                          onChange={(e) => updateChapter(idx, { summary: e.target.value })}
                        />
                        <TextArea
                          rows={8}
                          value={ch.content}
                          placeholder="章节正文"
                          onChange={(e) => updateChapter(idx, { content: e.target.value })}
                        />
                      </Space>
                    ),
                  }))}
                />
              </Card>

              </Space>
            </div>
          )}
        </Spin>
      </Card>

      </>
      )}

      {currentStep === 3 && (
      <Card title="生成导入进度" className="u-6srbul">
        <div className="u-5zg3tf">
          <Typography.Title level={4} className="u-yplvzz">
            {retrying ? '正在重试失败的生成步骤' : (failedSteps.length > 0 && isApplyComplete ? '导入完成，部分步骤需要重试' : '正在为您生成并导入项目内容')}
          </Typography.Title>
          
          <Progress
            percent={retrying ? retryProgress : applyProgress}
            status={
              applyError ? 'exception' :
              (failedSteps.length > 0 && isApplyComplete && !retrying) ? 'exception' :
              (isApplyComplete && failedSteps.length === 0) ? 'success' :
              'active'
            }
            strokeColor={{
              '0%': 'var(--color-primary)',
              '100%': failedSteps.length > 0 ? token.colorWarning : 'var(--color-primary-active)',
            }}
            className="u-19d88e2"
          />
          
          <Typography.Paragraph
            className={sx({
              fontSize: 16,
              marginBottom: 32,
              color: applyError ? 'var(--color-error)' :
                (failedSteps.length > 0 && isApplyComplete && !retrying) ? token.colorWarning :
                'var(--color-text-secondary)'
            })}
          >
            {retrying ? retryMessage : (applyError || applyMessage)}
          </Typography.Paragraph>
          
          {applyError && (
            <Alert
              type="error"
              message="导入出错"
              description={applyError}
              showIcon
              className="u-i1lxpe"
            />
          )}

          {/* 步骤失败提示与重试UI */}
          {failedSteps.length > 0 && isApplyComplete && !retrying && (
            <div className="u-i1lxpe">
              <Alert
                type="warning"
                icon={<WarningOutlined />}
                showIcon
                message={`${failedSteps.length} 个生成步骤失败`}
                description={
                  <div>
                    <Typography.Paragraph className="u-n9nj68">
                      以下AI生成步骤未能完成，但基础数据（章节、大纲）已成功导入。您可以选择重试或跳过。
                    </Typography.Paragraph>
                    <List
                      size="small"
                      bordered
                      dataSource={failedSteps}
                      renderItem={(item) => (
                        <List.Item
                          className="u-3b493u"
                        >
                          <List.Item.Meta
                            title={
                              <Space>
                                <Tag color="error">{item.step_label}</Tag>
                                {(item.retry_count ?? 0) > 0 && (
                                  <Tag color="orange">已重试 {item.retry_count} 次</Tag>
                                )}
                              </Space>
                            }
                            description={
                              <Typography.Text type="secondary" className="u-1pw6xki">
                                {item.error.length > 120 ? item.error.slice(0, 120) + '...' : item.error}
                              </Typography.Text>
                            }
                          />
                        </List.Item>
                      )}
                    />
                    <Space className="u-13c2il5">
                      <Button
                        type="primary"
                        icon={<RedoOutlined />}
                        onClick={retryFailedSteps}
                        loading={retrying}
                      >
                        智能重试全部失败步骤
                      </Button>
                      <Button onClick={skipFailedSteps}>
                        跳过，直接进入项目
                      </Button>
                    </Space>
                  </div>
                }
                className="u-6srbul"
              />
            </div>
          )}

          {/* 重试进行中 */}
          {retrying && (
            <div className="u-19d88e2">
              <Spin spinning={retrying}>
                <Alert
                  type="info"
                  showIcon
                  message="正在重试..."
                  description={retryMessage}
                  className="u-1jqnuuc"
                />
              </Spin>
            </div>
          )}
          
          {!failedSteps.length && !retrying && (
            <div className="u-7vogbc">
              <Typography.Text type="secondary" className="u-sidwtb">
                导入过程中，AI会自动帮您补全：<br />
                • 世界观设定（时间、地点、氛围、规则）<br />
                • 职业体系（主职业与副职业）<br />
                • 核心角色与相关组织<br />
                {isApplyComplete ? '所有步骤已完成，即将自动跳转。' : '请耐心等待，完成后将自动跳转。'}
              </Typography.Text>
            </div>
          )}
        </div>
      </Card>
      )}

      </div>
    </div>
  );
}