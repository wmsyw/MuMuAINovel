import { act } from 'react';
import type { ComponentProps } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  get: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
  requestUse: vi.fn(),
  responseUse: vi.fn(),
  axiosPost: vi.fn(),
  axiosGet: vi.fn(),
  create: vi.fn(),
  ssePost: vi.fn(),
  messageError: vi.fn(),
  messageSuccess: vi.fn(),
  messageWarning: vi.fn(),
}));

vi.mock('@ant-design/icons', async () => {
  const React = await vi.importActual<typeof import('react')>('react');
  const Icon = ({ children }: { children?: React.ReactNode }) => React.createElement('span', { 'aria-hidden': true }, children);

  return {
    CheckOutlined: Icon,
    CloseOutlined: Icon,
    EditOutlined: Icon,
    LoadingOutlined: Icon,
    ReloadOutlined: Icon,
    ThunderboltOutlined: Icon,
  };
});

vi.mock('antd', async () => {
  const React = await vi.importActual<typeof import('react')>('react');
  const h = React.createElement;

  const token = {
    colorPrimary: '#1677ff',
    colorTextSecondary: '#666',
    colorPrimaryBorder: '#91caff',
    colorBorderSecondary: '#f0f0f0',
    colorBgContainer: '#fff',
    colorFillQuaternary: '#fafafa',
    colorFillTertiary: '#f5f5f5',
    marginMD: 16,
    marginSM: 12,
    marginXS: 8,
    marginXXS: 4,
    paddingSM: 8,
    borderRadius: 6,
    borderRadiusLG: 8,
  };

  const domProps = (props: Record<string, unknown>, extraOmit: string[] = []) => {
    const omitted = new Set([
      'children',
      'checkedChildren',
      'unCheckedChildren',
      'centered',
      'direction',
      'footer',
      'htmlType',
      'icon',
      'indicator',
      'layout',
      'level',
      'loading',
      'maskClosable',
      'message',
      'open',
      'showCount',
      'showIcon',
      'size',
      'spinning',
      'status',
      'strong',
      'tooltip',
      'type',
      'width',
      ...extraOmit,
    ]);

    return Object.fromEntries(
      Object.entries(props).filter(([key]) => !omitted.has(key))
    );
  };

  const Alert = ({ message, description, ...props }: Record<string, unknown>) => h(
    'div',
    { ...domProps(props), role: 'alert' },
    h('div', null, message as React.ReactNode),
    description ? h('div', null, description as React.ReactNode) : null
  );

  const Button = ({ children, disabled, htmlType, icon, loading, onClick, ...props }: Record<string, unknown>) => h(
    'button',
    {
      ...domProps(props),
      type: typeof htmlType === 'string' ? htmlType : 'button',
      disabled: Boolean(disabled || loading),
      onClick,
    },
    icon as React.ReactNode,
    children as React.ReactNode
  );

  const Card = ({ children, title, ...props }: Record<string, unknown>) => h(
    'section',
    domProps(props),
    title ? h('header', null, title as React.ReactNode) : null,
    children as React.ReactNode
  );

  const Divider = (props: Record<string, unknown>) => h('hr', domProps(props));
  const Space = ({ children, ...props }: Record<string, unknown>) => h('div', domProps(props), children as React.ReactNode);
  const Spin = ({ children, ...props }: Record<string, unknown>) => h('div', domProps(props), children as React.ReactNode);
  const Progress = ({ percent, ...props }: Record<string, unknown>) => h(
    'div',
    { ...domProps(props), 'data-percent': String(percent ?? '') },
    `${percent ?? 0}%`
  );
  const Tag = ({ children, ...props }: Record<string, unknown>) => h('span', domProps(props), children as React.ReactNode);

  const Form = ({ children, ...props }: Record<string, unknown>) => h('form', domProps(props), children as React.ReactNode);
  (Form as { Item?: unknown }).Item = ({ children, label, ...props }: Record<string, unknown>) => h(
    'div',
    domProps(props),
    label ? h('div', null, label as React.ReactNode) : null,
    children as React.ReactNode
  );

  const TextArea = ({ children, onChange, value, ...props }: Record<string, unknown>) => h(
    'textarea',
    {
      ...domProps(props),
      value: value ?? '',
      onChange,
    },
    children as React.ReactNode
  );

  const Modal = ({ children, footer, onCancel, open, title, ...props }: Record<string, unknown>) => {
    if (!open) {
      return null;
    }

    return h(
      'div',
      { ...domProps(props), role: 'dialog' },
      h('div', null, title as React.ReactNode),
      h('button', { type: 'button', 'aria-label': '关闭弹窗', onClick: onCancel }, '关闭'),
      h('div', null, children as React.ReactNode),
      h('footer', null, footer as React.ReactNode)
    );
  };

  const Switch = ({ checked, checkedChildren, disabled, onChange, unCheckedChildren, ...props }: Record<string, unknown>) => h(
    'button',
    {
      ...domProps(props),
      type: 'button',
      role: 'switch',
      'aria-checked': checked ? 'true' : 'false',
      disabled: Boolean(disabled),
      onClick: () => {
        if (!disabled && typeof onChange === 'function') {
          onChange(!checked);
        }
      },
    },
    (checked ? checkedChildren : unCheckedChildren) as React.ReactNode
  );

  const Text = ({ children, strong, ...props }: Record<string, unknown>) => h(
    strong ? 'strong' : 'span',
    domProps(props),
    children as React.ReactNode
  );
  const Paragraph = ({ children, ...props }: Record<string, unknown>) => h('p', domProps(props), children as React.ReactNode);
  const Title = ({ children, level = 1, ...props }: Record<string, unknown>) => h(
    `h${level}`,
    domProps(props),
    children as React.ReactNode
  );

  return {
    Alert,
    Button,
    Card,
    Divider,
    Form,
    Input: { TextArea },
    Modal,
    Progress,
    Space,
    Spin,
    Switch,
    Tag,
    Typography: { Paragraph, Text, Title },
    message: {
      error: mocks.messageError,
      success: mocks.messageSuccess,
      warning: mocks.messageWarning,
    },
    theme: {
      useToken: () => ({ token }),
    },
  };
});

vi.mock('axios', () => {
  const client = {
    post: mocks.post,
    get: mocks.get,
    put: mocks.put,
    delete: mocks.delete,
    interceptors: {
      request: { use: mocks.requestUse },
      response: { use: mocks.responseUse },
    },
  };

  mocks.create.mockReturnValue(client);

  return {
    default: {
      create: mocks.create,
      post: mocks.axiosPost,
      get: mocks.axiosGet,
    },
  };
});

vi.mock('../utils/sseClient', () => ({
  ssePost: mocks.ssePost,
}));

import ProjectOptimizeModal from './ProjectOptimizeModal';
import { projectApi } from '../services/api';
import { ssePost } from '../utils/sseClient';
import type { OptimizableField, ProjectOptimizeResult } from '../types';

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string): MediaQueryList => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  }),
});

type ModalProps = ComponentProps<typeof ProjectOptimizeModal>;

const currentProject = {
  title: '旧标题',
  description: '旧简介',
  theme: '旧主题',
  genre: '玄幻',
  world_time_period: '旧时间',
  world_location: '旧地点',
  world_atmosphere: '旧氛围',
  world_rules: '旧规则',
  narrative_perspective: '第三人称',
} satisfies Record<OptimizableField, string>;

const defaultResult: ProjectOptimizeResult = {
  reply: '已生成项目优化建议。',
  fields: {
    title: {
      value: '星桥暗涌',
      reason: '标题更有悬疑钩子。',
    },
    theme: {
      value: '记忆与归乡',
      reason: '强化主题凝聚力。',
    },
    world_rules: {
      value: '星桥以记忆为燃料，月潮锁城。',
      reason: '补足可持续展开的世界规则。',
    },
  },
};

const defaultProps: ModalProps = {
  visible: true,
  projectId: 'project-1',
  currentProject,
  onCancel: vi.fn(),
  onApply: vi.fn(),
};

let cleanupModal: (() => Promise<void>) | undefined;

function delay() {
  return new Promise(resolve => setTimeout(resolve, 0));
}

async function settle() {
  await delay();
  await delay();
}

async function renderModal(props: Partial<ModalProps> = {}) {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  const mergedProps = { ...defaultProps, ...props };

  await act(async () => {
    root.render(<ProjectOptimizeModal {...mergedProps} />);
    await settle();
  });

  cleanupModal = async () => {
    await act(async () => {
      root.unmount();
      await settle();
    });
    container.remove();
  };

  return { container, props: mergedProps };
}

async function click(element: HTMLElement) {
  await act(async () => {
    element.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    await settle();
  });
}

async function changeTextArea(textArea: HTMLTextAreaElement, value: string) {
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
    setter?.call(textArea, value);
    textArea.dispatchEvent(new Event('input', { bubbles: true }));
    textArea.dispatchEvent(new Event('change', { bubbles: true }));
    await settle();
  });
}

async function waitForAssertion(assertion: () => void) {
  let lastError: unknown;

  for (let attempt = 0; attempt < 10; attempt += 1) {
    try {
      assertion();
      return;
    } catch (error) {
      lastError = error;
      await act(async () => {
        await delay();
      });
    }
  }

  throw lastError;
}

function getButtonByText(text: string) {
  const button = Array.from(document.body.querySelectorAll<HTMLButtonElement>('button'))
    .find(element => element.textContent?.includes(text));

  if (!button) {
    throw new Error(`Button not found: ${text}`);
  }

  return button;
}

function getTextAreaByPlaceholder(fragment: string) {
  const textArea = Array.from(document.body.querySelectorAll<HTMLTextAreaElement>('textarea'))
    .find(element => element.placeholder.includes(fragment));

  if (!textArea) {
    throw new Error(`Textarea not found: ${fragment}`);
  }

  return textArea;
}

function getFieldCard(field: OptimizableField) {
  const card = document.body.querySelector<HTMLElement>(`[data-omo-field="${field}"]`);

  if (!card) {
    throw new Error(`Field card not found: ${field}`);
  }

  return card;
}

function getFieldTextArea(field: OptimizableField) {
  const textArea = getFieldCard(field).querySelector<HTMLTextAreaElement>('textarea');

  if (!textArea) {
    throw new Error(`Field textarea not found: ${field}`);
  }

  return textArea;
}

function getFieldSwitch(field: OptimizableField) {
  const switchButton = getFieldCard(field).querySelector<HTMLButtonElement>('button[role="switch"]');

  if (!switchButton) {
    throw new Error(`Field switch not found: ${field}`);
  }

  return switchButton;
}

function mockStreamResult(result: ProjectOptimizeResult = defaultResult) {
  mocks.ssePost.mockImplementation(async (_url: string, _data: unknown, handlers: Record<string, (...args: unknown[]) => void> = {}) => {
    handlers.onProgress?.('正在分析项目设定...', 35, 'processing');
    handlers.onChunk?.('流式片段');
    handlers.onResult?.(result);
    handlers.onComplete?.();
    return result;
  });
}

async function startOptimize(requirement?: string) {
  if (requirement !== undefined) {
    await changeTextArea(getTextAreaByPlaceholder('强化悬疑张力'), requirement);
  }

  await click(getButtonByText('开始优化'));
}

beforeEach(() => {
  vi.restoreAllMocks();
  mocks.post.mockClear();
  mocks.get.mockClear();
  mocks.put.mockClear();
  mocks.delete.mockClear();
  mocks.requestUse.mockClear();
  mocks.responseUse.mockClear();
  mocks.messageError.mockClear();
  mocks.messageSuccess.mockClear();
  mocks.messageWarning.mockClear();
  mocks.ssePost.mockReset();

  vi.spyOn(projectApi, 'optimizeProjectStream').mockImplementation((projectId, payload, handlers) => (
    ssePost<ProjectOptimizeResult>(`/api/projects/${projectId}/optimize-stream`, payload, handlers)
  ));

  mockStreamResult();
});

afterEach(async () => {
  if (cleanupModal) {
    await cleanupModal();
    cleanupModal = undefined;
  }

  document.body.innerHTML = '';
});

describe('ProjectOptimizeModal', () => {
  it('renders streamed comparison rows with label, original value, suggested value, and reason after onResult', async () => {
    await renderModal();

    await startOptimize('强化悬疑张力');

    await waitForAssertion(() => {
      expect(document.body.textContent).toContain('项目标题');
      expect(document.body.textContent).toContain('旧标题');
      expect(getFieldTextArea('title').value).toBe('星桥暗涌');
      expect(document.body.textContent).toContain('理由：标题更有悬疑钩子。');
      expect(document.body.textContent).toContain('主题');
      expect(document.body.textContent).toContain('旧主题');
      expect(getFieldTextArea('theme').value).toBe('记忆与归乡');
      expect(document.body.textContent).toContain('理由：强化主题凝聚力。');
      expect(document.body.textContent).toContain('世界规则');
      expect(document.body.textContent).toContain('旧规则');
      expect(getFieldTextArea('world_rules').value).toBe('星桥以记忆为燃料，月潮锁城。');
      expect(document.body.textContent).toContain('理由：补足可持续展开的世界规则。');
    });

    expect(projectApi.optimizeProjectStream).toHaveBeenCalledWith(
      'project-1',
      { requirement: '强化悬疑张力' },
      expect.objectContaining({
        onProgress: expect.any(Function),
        onResult: expect.any(Function),
        onError: expect.any(Function),
        onComplete: expect.any(Function),
      })
    );
    expect(ssePost).toHaveBeenCalledWith(
      '/api/projects/project-1/optimize-stream',
      { requirement: '强化悬疑张力' },
      expect.objectContaining({ onChunk: expect.any(Function) })
    );
  });

  it('applies only accepted fields after accept/reject switches change', async () => {
    const onApply = vi.fn();
    await renderModal({ onApply });

    await startOptimize('只保留部分建议');
    await click(getFieldSwitch('theme'));

    await click(getButtonByText('应用已接受字段'));

    expect(onApply).toHaveBeenCalledTimes(1);
    expect(onApply).toHaveBeenCalledWith({
      title: '星桥暗涌',
      world_rules: '星桥以记忆为燃料，月潮锁城。',
    });
  });

  it('uses a user-edited suggested value when applying accepted fields', async () => {
    const onApply = vi.fn();
    mockStreamResult({
      reply: '标题建议。',
      fields: {
        title: {
          value: '星桥暗涌',
          reason: '更有爆点。',
        },
      },
    });
    await renderModal({ onApply });

    await startOptimize('标题更有网文感');
    await changeTextArea(getFieldTextArea('title'), '用户改写标题');
    await click(getButtonByText('应用已接受字段'));

    expect(onApply).toHaveBeenCalledTimes(1);
    expect(onApply).toHaveBeenCalledWith({ title: '用户改写标题' });
  });

  it('can start a streaming request when requirement is empty', async () => {
    await renderModal();

    await startOptimize();

    await waitForAssertion(() => {
      expect(projectApi.optimizeProjectStream).toHaveBeenCalledTimes(1);
    });

    expect(projectApi.optimizeProjectStream).toHaveBeenCalledWith(
      'project-1',
      { requirement: undefined },
      expect.objectContaining({ onResult: expect.any(Function) })
    );
    expect(ssePost).toHaveBeenCalledWith(
      '/api/projects/project-1/optimize-stream',
      { requirement: undefined },
      expect.objectContaining({ signal: expect.any(Object) })
    );
  });

  it('shows onError messages and does not call onApply in the error state', async () => {
    const onApply = vi.fn();
    mocks.ssePost.mockImplementation(async (_url: string, _data: unknown, handlers: Record<string, (...args: unknown[]) => void> = {}) => {
      handlers.onProgress?.('正在分析项目设定...', 20, 'processing');
      handlers.onError?.('服务繁忙');
      throw new Error('服务繁忙');
    });
    await renderModal({ onApply });

    await startOptimize('触发错误');

    await waitForAssertion(() => {
      expect(document.body.textContent).toContain('优化失败');
      expect(document.body.textContent).toContain('服务繁忙');
    });
    expect(onApply).not.toHaveBeenCalled();
  });

  it('disables and blocks apply when zero suggested fields are accepted', async () => {
    const onApply = vi.fn();
    mockStreamResult({
      reply: '两个字段建议。',
      fields: {
        title: {
          value: '星桥暗涌',
          reason: '更有钩子。',
        },
        theme: {
          value: '记忆与归乡',
          reason: '主题更集中。',
        },
      },
    });
    await renderModal({ onApply });

    await startOptimize('全部先拒绝');
    await click(getFieldSwitch('title'));
    await click(getFieldSwitch('theme'));

    await waitForAssertion(() => {
      expect(document.body.textContent).toContain('尚未接受任何字段');
      expect(getButtonByText('应用已接受字段').disabled).toBe(true);
    });
    await click(getButtonByText('应用已接受字段'));
    expect(onApply).not.toHaveBeenCalled();
  });
});
