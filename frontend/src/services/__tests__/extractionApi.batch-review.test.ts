import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ExtractionCandidate } from '../../types';

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

import { extractionApi } from '../api';

function candidate(id: string): ExtractionCandidate {
  return {
    id,
    run_id: 'run-1',
    project_id: 'project-1',
    user_id: 'user-1',
    candidate_type: 'character',
    trigger_type: 'chapter_save',
    source_hash: 'hash',
    status: 'accepted',
    confidence: 0.9,
    evidence_text: '证据',
    source_start_offset: 0,
    source_end_offset: 2,
    payload: {},
  };
}

beforeEach(() => {
  mocks.post.mockReset();
});

describe('extractionApi batch review contracts', () => {
  it('chunks accepts at 200 IDs and combines each chunk in response order', async () => {
    const candidateIds = Array.from({ length: 450 }, (_, index) => `candidate-${index + 1}`);
    mocks.post
      .mockResolvedValueOnce({
        changed: 2,
        failures: [{ candidate_id: 'candidate-2', reason: 'already accepted' }],
        candidates: [candidate('candidate-200'), candidate('candidate-1')],
      })
      .mockResolvedValueOnce({
        changed: 1,
        failures: [{ candidate_id: 'candidate-201', reason: 'ambiguous' }],
        candidates: [candidate('candidate-400')],
      })
      .mockResolvedValueOnce({
        changed: 1,
        failures: [{ candidate_id: 'candidate-401', reason: 'unsupported' }],
        candidates: [candidate('candidate-450')],
      });

    const response = await extractionApi.batchAcceptCandidates(candidateIds);

    expect(mocks.post).toHaveBeenCalledTimes(3);
    expect(mocks.post.mock.calls.map(([, body]) => (body as { candidate_ids: string[] }).candidate_ids.length)).toEqual([
      200,
      200,
      50,
    ]);
    expect(mocks.post.mock.calls[0]?.[1]).toEqual({ candidate_ids: candidateIds.slice(0, 200) });
    expect(mocks.post.mock.calls[1]?.[1]).toEqual({ candidate_ids: candidateIds.slice(200, 400) });
    expect(mocks.post.mock.calls[2]?.[1]).toEqual({ candidate_ids: candidateIds.slice(400) });
    expect(response.changed).toBe(4);
    expect(response.failures.map(failure => failure.candidate_id)).toEqual([
      'candidate-2',
      'candidate-201',
      'candidate-401',
    ]);
    expect(response.candidates.map(item => item.id)).toEqual([
      'candidate-200',
      'candidate-1',
      'candidate-400',
      'candidate-450',
    ]);
  });

  it('chunks rejects and carries the same reason to every request', async () => {
    const candidateIds = Array.from({ length: 201 }, (_, index) => `candidate-${index + 1}`);
    mocks.post.mockImplementation(async (_url: string, body: { candidate_ids: string[]; reason?: string }) => ({
      changed: body.candidate_ids.length,
      failures: [],
      candidates: [],
    }));

    const response = await extractionApi.batchRejectCandidates(candidateIds, '重复候选');

    expect(mocks.post).toHaveBeenCalledTimes(2);
    expect(mocks.post.mock.calls.map(([, body]) => body)).toEqual([
      { candidate_ids: candidateIds.slice(0, 200), reason: '重复候选' },
      { candidate_ids: candidateIds.slice(200), reason: '重复候选' },
    ]);
    expect(response).toEqual({ changed: 201, failures: [], candidates: [] });
  });
  it('accepts goldfinger canonical targets and review-required reasons', () => {
    const goldfingerCandidate: ExtractionCandidate = {
      ...candidate('goldfinger-candidate'),
      candidate_type: 'goldfinger',
      canonical_target_type: 'goldfinger',
      review_required_reason: 'needs manual review',
    };

    expect(goldfingerCandidate.candidate_type).toBe('goldfinger');
    expect(goldfingerCandidate.canonical_target_type).toBe('goldfinger');
    expect(goldfingerCandidate.review_required_reason).toBe('needs manual review');
  });
});
