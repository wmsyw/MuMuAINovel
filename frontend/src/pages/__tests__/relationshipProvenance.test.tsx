import { act, type ComponentProps } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, expect, it, vi } from 'vitest';

import GoldfingerPendingReviewPanel from '../../components/goldfingers/GoldfingerPendingReviewPanel';
import { getSyncCandidateDiff } from '../../components/goldfingers/syncReviewUtils';
import type { SyncCandidate, SyncCandidateReviewResponse } from '../../types';

type ReviewPanelProps = ComponentProps<typeof GoldfingerPendingReviewPanel>;
type ReviewApiClient = NonNullable<ReviewPanelProps['apiClient']>;

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

const relationshipCandidate: SyncCandidate = {
  id: 'candidate-relationship-1',
  run_id: 'run-relationship-1',
  project_id: 'project-1',
  user_id: 'user-1',
  source_chapter_id: 'chapter-8',
  candidate_type: 'relationship',
  trigger_type: 'chapter_save',
  source_hash: 'hash-relationship',
  display_name: '仇敌',
  normalized_name: '仇敌',
  canonical_target_type: 'relationship',
  canonical_target_id: 'relationship-existing',
  status: 'pending',
  confidence: 0.63,
  evidence_text: '第八章低置信度描述林墨与苏青反目，但上下文仍有歧义。',
  source_start_offset: 12,
  source_end_offset: 38,
  source_chapter_number: 8,
  source_chapter_order: 8,
  payload: {
    character_from_name: '林墨',
    character_from_id: 'char-linmo',
    character_to_name: '苏青',
    character_to_id: 'char-suqing',
    relationship_name: '仇敌',
    old_value: { relationship_name: '盟友', status: 'active' },
    new_value: { relationship_name: '仇敌', status: 'active' },
  },
  review_required_reason: 'low_confidence',
};

const goldfingerCandidate: SyncCandidate = {
  ...relationshipCandidate,
  id: 'candidate-goldfinger-1',
  candidate_type: 'goldfinger',
  display_name: '天命系统',
  normalized_name: '天命系统',
  canonical_target_type: 'goldfinger',
  canonical_target_id: null,
  confidence: 0.95,
  evidence_text: '天命系统发布三日救援任务并承诺悟性奖励。',
  payload: {
    name: '天命系统',
    type: 'system',
    status: 'active',
    tasks: [{ title: '三日内救下师姐苏青' }],
    rewards: [{ name: '悟性提升' }],
  },
  review_required_reason: 'manual_review_required',
};

async function delay(ms = 0): Promise<void> {
  await new Promise<void>(resolve => window.setTimeout(resolve, ms));
}

async function waitForAssertion(assertion: () => void): Promise<void> {
  let lastError: unknown;
  for (let attempt = 0; attempt < 25; attempt += 1) {
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

function createMockApiClient(candidate: SyncCandidate): ReviewApiClient {
  const response: SyncCandidateReviewResponse = {
    changed: true,
    reason: 'reviewed',
    candidate: { ...candidate, status: candidate.candidate_type === 'relationship' ? 'merged' : 'accepted' },
  };

  return {
    listCandidates: vi.fn<ReviewApiClient['listCandidates']>().mockResolvedValue({ total: 0, items: [] }),
    approveCandidate: vi.fn<ReviewApiClient['approveCandidate']>().mockResolvedValue(response),
    rejectCandidate: vi.fn<ReviewApiClient['rejectCandidate']>().mockResolvedValue(response),
  };
}

async function renderPanel(props: ReviewPanelProps) {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);

  await act(async () => {
    root.render(<GoldfingerPendingReviewPanel {...props} />);
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
  if (!button) throw new Error(`未找到按钮：${text}`);
  return button;
}

describe('relationship provenance and shared sync review UI', () => {
  it('renders relationship pending candidates with source chapter, evidence, confidence and old/new snapshots', async () => {
    const apiClient = createMockApiClient(relationshipCandidate);
    const onReviewed = vi.fn().mockResolvedValue(undefined);
    const view = await renderPanel({
      projectId: 'project-1',
      entityType: 'relationship',
      initialCandidates: [relationshipCandidate],
      autoLoad: false,
      apiClient,
      onReviewed,
    });

    try {
      expect(view.container.textContent).toContain('待审核关系同步');
      expect(view.container.textContent).toContain('林墨 → 苏青 · 仇敌');
      expect(view.container.textContent).toContain('第 8 章');
      expect(view.container.textContent).toContain('置信度 63%');
      expect(view.container.textContent).toContain('旧值快照');
      expect(view.container.textContent).toContain('新值/正文提案');
      expect(view.container.textContent).toContain('低置信度，需要人工确认');
      expect(getSyncCandidateDiff(relationshipCandidate, 'relationship').map(item => item.label)).toContain('旧值快照');

      await act(async () => {
        findButtonByText(view.container, '通过并合并').dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
        await delay();
      });

      await waitForAssertion(() => {
        expect(apiClient.approveCandidate).toHaveBeenCalledWith('candidate-relationship-1', {
          target_type: 'relationship',
          target_id: 'relationship-existing',
          override: true,
        });
        expect(apiClient.listCandidates).toHaveBeenCalledWith('project-1', { entity_type: 'relationship', status: 'pending', limit: 50 });
        expect(onReviewed).toHaveBeenCalledTimes(1);
      });
    } finally {
      await view.cleanup();
    }
  });

  it('keeps the default goldfinger review path using syncApi semantics', async () => {
    const apiClient = createMockApiClient(goldfingerCandidate);
    const view = await renderPanel({
      projectId: 'project-1',
      initialCandidates: [goldfingerCandidate],
      autoLoad: false,
      apiClient,
    });

    try {
      expect(view.container.textContent).toContain('金手指候选需要人工确认');
      expect(view.container.textContent).toContain('天命系统');
      expect(view.container.textContent).toContain('三日内救下师姐苏青');
      expect(getSyncCandidateDiff(goldfingerCandidate, 'goldfinger').map(item => item.label)).toContain('任务');

      await act(async () => {
        findButtonByText(view.container, '通过并合并').dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
        await delay();
      });

      await waitForAssertion(() => {
        expect(apiClient.approveCandidate).toHaveBeenCalledWith('candidate-goldfinger-1', expect.objectContaining({ target_type: 'goldfinger' }));
        expect(apiClient.listCandidates).toHaveBeenCalledWith('project-1', { entity_type: 'goldfinger', status: 'pending', limit: 50 });
      });
    } finally {
      await view.cleanup();
    }
  });
});
