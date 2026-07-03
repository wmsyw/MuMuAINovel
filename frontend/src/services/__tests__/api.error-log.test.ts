import { beforeEach, describe, expect, it, vi } from 'vitest';

type ResponseRejectedHandler = (error: unknown) => Promise<never>;

const mocks = vi.hoisted(() => {
  const responseRejectedHandlers: ResponseRejectedHandler[] = [];

  return {
    messageError: vi.fn(),
    post: vi.fn(),
    get: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    requestUse: vi.fn(),
    responseUse: vi.fn((
      _fulfilled: (response: { readonly data: unknown }) => unknown,
      rejected?: ResponseRejectedHandler
    ) => {
      if (rejected) {
        responseRejectedHandlers.push(rejected);
      }
      return 0;
    }),
    axiosPost: vi.fn(),
    axiosGet: vi.fn(),
    create: vi.fn(),
    responseRejectedHandlers,
  };
});

vi.mock('antd', () => ({
  message: {
    error: mocks.messageError,
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

import '../api';

const secretValues = [
  'cover-secret-123',
  'preset-secret-456',
  'authorization-secret-789',
  'cookie-secret-abc',
  'query-token-secret',
  'query-api-key-secret',
  'fragment-secret',
  'response-detail-secret',
  'response-message-secret',
  'fastapi-array-secret',
  'raw-error-message-secret',
] as const;

beforeEach(() => {
  mocks.messageError.mockClear();
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
});

describe('api response interceptor error logging', () => {
  it('logs sanitized axios context without response bodies, config, headers, query, fragment, or validation secrets', async () => {
    const responseRejected = mocks.responseRejectedHandlers[0];
    if (!responseRejected) {
      throw new Error('response interceptor rejected handler was not registered');
    }

    const error = {
      response: {
        status: 422,
        data: {
          detail: 'response-detail-secret',
          message: 'response-message-secret',
          errors: [
            {
              loc: ['body', 'cover_api_key'],
              msg: 'provided secret cover-secret-123 rejected',
              input: 'cover-secret-123',
            },
          ],
        },
      },
      config: {
        method: 'post',
        url: '/settings/cover/test?token=query-token-secret&api_key=query-api-key-secret#fragment-secret',
        data: JSON.stringify({
          cover_api_key: 'cover-secret-123',
          config: { api_key: 'preset-secret-456' },
        }),
        headers: {
          Authorization: 'Bearer authorization-secret-789',
          Cookie: 'session=cookie-secret-abc',
        },
      },
      request: {
        body: 'cover-secret-123 preset-secret-456 authorization-secret-789 cookie-secret-abc',
      },
      message: 'raw-error-message-secret',
    };

    const fastApiDetailError = {
      response: {
        status: 422,
        data: {
          detail: [
            {
              loc: ['body', 'cover_api_key'],
              msg: 'fastapi-array-secret',
              input: 'cover-secret-123',
            },
          ],
        },
      },
      config: {
        method: 'post',
        url: '/settings/cover/test?token=query-token-secret#fragment-secret',
      },
      message: 'raw-error-message-secret',
    };

    await expect(responseRejected(error)).rejects.toBe(error);
    await expect(responseRejected(fastApiDetailError)).rejects.toBe(fastApiDetailError);

    expect(mocks.messageError).toHaveBeenCalledWith('response-detail-secret');
    expect(mocks.messageError).toHaveBeenCalledWith('请求参数验证失败');

    const serializedLogs = JSON.stringify(vi.mocked(console.error).mock.calls);
    for (const secretValue of secretValues) {
      expect(serializedLogs).not.toContain(secretValue);
    }
    expect(serializedLogs).not.toContain('Authorization');
    expect(serializedLogs).not.toContain('Cookie');
    expect(serializedLogs).not.toContain('headers');
    expect(serializedLogs).not.toContain('config');
    expect(serializedLogs).not.toContain('request');
    expect(serializedLogs).not.toContain('api_key');
    expect(serializedLogs).not.toContain('cover_api_key');
    expect(serializedLogs).not.toContain('errorMessage');
    expect(serializedLogs).not.toContain('detail');
    expect(serializedLogs).not.toContain('message');
    expect(serializedLogs).not.toContain('errors');

    expect(console.error).toHaveBeenCalledWith('验证错误详情:', {
      validationErrorCount: 1,
    });
    expect(console.error).toHaveBeenCalledWith('API Error:', {
      errorKind: 'validation_error',
      method: 'POST',
      path: '/settings/cover/test',
      status: 422,
      validationErrorCount: 1,
    });
  });
});
