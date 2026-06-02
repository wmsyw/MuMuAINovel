import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ProjectOptimizeRequest, ProjectOptimizeResult } from '../../types';
import type { SSEClientOptions } from '../../utils/sseClient';

const mocks = vi.hoisted(() => ({
  ssePost: vi.fn(),
  post: vi.fn(),
  get: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
  requestUse: vi.fn(),
  responseUse: vi.fn(),
  axiosPost: vi.fn(),
  axiosGet: vi.fn(),
  create: vi.fn(),
}));

vi.mock('antd', () => ({
  message: {
    error: vi.fn(),
  },
}));

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

vi.mock('../../utils/sseClient', () => ({
  ssePost: mocks.ssePost,
}));

import { projectApi } from '../api';

beforeEach(() => {
  mocks.ssePost.mockReset();
});

describe('projectApi.optimizeProjectStream', () => {
  it('delegates to ssePost with optimize-stream route and passthrough handlers', async () => {
    const payload: ProjectOptimizeRequest = {
      requirement: '增强标题冲突感',
      conversation_history: [{ role: 'user', content: '请优化这个项目设定' }],
      current_draft: { title: '星桥尽头' },
    };

    const expectedResult: ProjectOptimizeResult = {
      fields: {
        title: {
          value: '星桥尽头：归乡回声',
          reason: '标题更突出归乡与冲突的核心卖点。',
        },
      },
      reply: '已根据需求优化标题，并保留当前设定方向。',
    };

    const onProgress = vi.fn();
    const onChunk = vi.fn();
    const onResult = vi.fn();
    const onError = vi.fn();
    const onComplete = vi.fn();

    const handlers = {
      onProgress,
      onChunk,
      onResult,
      onError,
      onComplete,
    } satisfies SSEClientOptions;

    mocks.ssePost.mockImplementation(async (_url: string, _data: unknown, options: SSEClientOptions = {}) => {
      options.onProgress?.('优化中', 60, 'processing', 1200);
      options.onChunk?.('chunk-1');
      options.onResult?.(expectedResult);
      options.onComplete?.();
      return expectedResult;
    });

    const result = await projectApi.optimizeProjectStream('project-123', payload, handlers);

    expect(mocks.ssePost).toHaveBeenCalledTimes(1);
    expect(mocks.ssePost).toHaveBeenCalledWith(
      '/api/projects/project-123/optimize-stream',
      payload,
      handlers
    );
    expect(onProgress).toHaveBeenCalledWith('优化中', 60, 'processing', 1200);
    expect(onChunk).toHaveBeenCalledWith('chunk-1');
    expect(onResult).toHaveBeenCalledWith(expectedResult);
    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(onError).not.toHaveBeenCalled();
    expect(result).toEqual(expectedResult);
  });
});
