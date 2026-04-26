import { act, type ComponentProps } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, expect, it, vi } from 'vitest';

import ExtractionCandidateReviewPanel from '../../components/ExtractionCandidateReviewPanel';
import type { CandidateReviewResponse, ExtractionCandidate } from '../../types';

const reviewUtils = ExtractionCandidateReviewPanel.__testUtils;
type PanelProps = ComponentProps<typeof ExtractionCandidateReviewPanel>;
type PanelApiClient = NonNullable<PanelProps['apiClient']>;

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

const candidate: ExtractionCandidate = {
  id: 'candidate-1',
  run_id: 'run-1',
  project_id: 'project-1',
  user_id: 'user-1',
  source_chapter_id: 'chapter-3',
  candidate_type: 'character',
  trigger_type: 'chapter_save',
  source_hash: 'hash',
  display_name: '沈砚',
  normalized_name: '沈砚',
  canonical_target_type: null,
  canonical_target_id: null,
  status: 'pending',
  confidence: 0.87,
  evidence_text: '沈砚在第三章拔剑，第一次显露出护送商队的本领。',
  source_start_offset: 24,
  source_end_offset: 51,
  source_chapter_number: 3,
  source_chapter_order: 3,
  payload: {
    name: '沈砚',
    aliases: ['沈护卫'],
    status: '初次登场',
  },
};

const acceptedCandidate: ExtractionCandidate = { ...candidate, status: 'accepted' };

function createMockApiClient(): PanelApiClient {
  const response: CandidateReviewResponse = {
    changed: true,
    reason: 'accepted',
    candidate: acceptedCandidate,
  };

  return {
    listCandidates: vi.fn<PanelApiClient['listCandidates']>().mockResolvedValue({ total: 1, items: [acceptedCandidate] }),
    acceptCandidate: vi.fn<PanelApiClient['acceptCandidate']>().mockResolvedValue(response),
    rejectCandidate: vi.fn<PanelApiClient['rejectCandidate']>(),
    mergeCandidate: vi.fn<PanelApiClient['mergeCandidate']>(),
    rollbackCandidate: vi.fn<PanelApiClient['rollbackCandidate']>(),
  };
}

async function delay(ms = 0): Promise<void> {
  await new Promise<void>(resolve => window.setTimeout(resolve, ms));
}

async function waitForAssertion(assertion: () => void): Promise<void> {
  let lastError: unknown;

  for (let attempt = 0; attempt < 20; attempt += 1) {
    try {
      assertion();
      return;
    } catch (error) {
      lastError = error;
      await act(async () => {
        await delay(10);
      });
    }
  }

  throw lastError;
}

async function renderPanel(props: PanelProps) {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);

  await act(async () => {
    root.render(<ExtractionCandidateReviewPanel {...props} />);
    await delay();
  });

  return {
    container,
    async cleanup() {
      await act(async () => {
        root.unmount();
      });
      container.remove();
    },
  };
}

function findButtonByText(container: HTMLElement, text: string): HTMLButtonElement {
  const button = Array.from(container.querySelectorAll('button')).find(element => element.textContent?.includes(text));
  if (!button) {
    throw new Error(`未找到按钮：${text}`);
  }
  return button;
}

describe('extraction candidate review UI helpers', () => {
  it('clicking the visible accept button calls API wrappers and refreshes candidate and canonical data', async () => {
    const apiClient = createMockApiClient();
    const refreshCanonical = vi.fn().mockResolvedValue(undefined);
    const view = await renderPanel({
      projectId: 'project-1',
      entityLabel: '角色',
      candidateTypes: ['character'],
      canonicalTargetType: 'character',
      canonicalOptions: [],
      canonicalChildren: <div>已入库角色</div>,
      initialCandidates: [candidate],
      autoLoad: false,
      defaultActiveKey: 'discovered',
      apiClient,
      onCanonicalChanged: refreshCanonical,
    });

    try {
      expect(view.container.textContent).toContain('证据片段');
      expect(view.container.textContent).toContain('沈砚在第三章拔剑');
      expect(view.container.textContent).toContain('置信度 87%');
      expect(view.container.textContent).toContain('第 3 章');
      expect(view.container.textContent).toContain('待评审');
      expect(view.container.textContent).toContain('接受入库');
      expect(view.container.textContent).toContain('拒绝');

      await act(async () => {
        findButtonByText(view.container, '接受入库').dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
        await delay();
      });

      await waitForAssertion(() => {
        expect(apiClient.acceptCandidate).toHaveBeenCalledWith('candidate-1', {});
        expect(apiClient.listCandidates).toHaveBeenCalledWith({ project_id: 'project-1', type: 'character', limit: 200 });
        expect(refreshCanonical).toHaveBeenCalledTimes(1);
        expect(view.container.textContent).toContain('正文发现 (0)');
        expect(view.container.textContent).toContain('已拒绝/历史 (1)');
      });
    } finally {
      await view.cleanup();
    }
  });

  it('disables direct AI canonical generation when the advanced override is off', () => {
    expect(reviewUtils.isAiGenerationOverrideEnabled({})).toBe(false);
    expect(reviewUtils.isAiGenerationOverrideEnabled({ allow_ai_entity_generation: false })).toBe(false);
    expect(reviewUtils.isAiGenerationOverrideEnabled({ allow_ai_entity_generation: true })).toBe(true);
    expect(reviewUtils.AI_ENTITY_GENERATION_POLICY_COPY).toBe('默认从正文自动提取角色/组织/职业；开启后才允许 AI 直接生成入库');
  });

  it('splits pending merge-target candidates and historical candidates for review tabs', () => {
    const split = reviewUtils.splitExtractionCandidates([
      candidate,
      { ...candidate, id: 'candidate-merge', canonical_target_id: 'character-1' },
      { ...candidate, id: 'candidate-rejected', status: 'rejected' },
    ]);

    expect(split.discovered.map(item => item.id)).toEqual(['candidate-1']);
    expect(split.merge.map(item => item.id)).toEqual(['candidate-merge']);
    expect(split.history.map(item => item.id)).toEqual(['candidate-rejected']);
  });
});
