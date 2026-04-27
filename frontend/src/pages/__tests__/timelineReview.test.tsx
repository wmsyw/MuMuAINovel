import { act, type ComponentProps } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, expect, it, vi } from 'vitest';

import TimelineReviewPanel from '../../components/common/TimelineReviewPanel';
import type { Character, TimelineEvent, TimelineStateResponse } from '../../types';

type TimelinePanelProps = ComponentProps<typeof TimelineReviewPanel>;
type TimelineApiClient = NonNullable<TimelinePanelProps['apiClient']>;
type TimelineOrganizationFixture = NonNullable<TimelinePanelProps['organizations']>[number];
type TimelineCareerFixture = NonNullable<TimelinePanelProps['careers']>[number];

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

class MockResizeObserver {
  observe(): void { return undefined; }
  unobserve(): void { return undefined; }
  disconnect(): void { return undefined; }
}

Object.defineProperty(globalThis, 'ResizeObserver', {
  writable: true,
  value: MockResizeObserver,
});

Object.defineProperty(window, 'ResizeObserver', {
  writable: true,
  value: MockResizeObserver,
});

const characters: Pick<Character, 'id' | 'name'>[] = [
  { id: 'char-shen', name: '沈砚' },
  { id: 'char-qing', name: '青岚' },
];

const organizations: TimelineOrganizationFixture[] = [
  {
    id: 'organization-bridge-starfire',
    character_id: 'org-character-starfire',
    organization_entity_id: 'org-starfire',
    name: '星火盟',
  },
];

const careers: TimelineCareerFixture[] = [
  { id: 'career-wanderer', name: '散修' },
  { id: 'career-sword', name: '剑修' },
  { id: 'career-alchemy', name: '丹师' },
];

const earlyRelationship: TimelineEvent = {
  id: 'rel-mentor',
  project_id: 'project-timeline-1',
  relationship_id: 'relationship-1',
  character_id: 'char-shen',
  related_character_id: 'char-qing',
  event_type: 'relationship',
  event_status: 'active',
  relationship_name: '师徒',
  source_chapter_id: 'chapter-3',
  source_chapter_order: 3,
  valid_from_chapter_id: 'chapter-3',
  valid_from_chapter_order: 3,
  valid_to_chapter_id: 'chapter-6',
  valid_to_chapter_order: 6,
  source_start_offset: 12,
  source_end_offset: 36,
  evidence_text: '第三章，青岚收沈砚为徒，亲手传下第一式。',
  confidence: 0.93,
};

const changedRelationship: TimelineEvent = {
  id: 'rel-alliance',
  project_id: 'project-timeline-1',
  relationship_id: 'relationship-1',
  character_id: 'char-shen',
  related_character_id: 'char-qing',
  event_type: 'relationship',
  event_status: 'active',
  relationship_name: '同盟',
  source_chapter_id: 'chapter-6',
  source_chapter_order: 6,
  valid_from_chapter_id: 'chapter-6',
  valid_from_chapter_order: 6,
  valid_to_chapter_id: 'chapter-10',
  valid_to_chapter_order: 10,
  source_start_offset: 88,
  source_end_offset: 126,
  evidence_text: '第六章二人平等立誓，旧日师徒关系改为共同对敌的同盟。',
  confidence: 0.82,
  supersedes_event_id: 'rel-mentor',
};

const earlyAffiliation: TimelineEvent = {
  id: 'aff-guest',
  project_id: 'project-timeline-1',
  organization_member_id: 'member-guest',
  character_id: 'char-shen',
  organization_entity_id: 'org-starfire',
  event_type: 'affiliation',
  event_status: 'active',
  position: '客卿',
  rank: 3,
  source_chapter_id: 'chapter-3',
  source_chapter_order: 3,
  valid_from_chapter_id: 'chapter-3',
  valid_from_chapter_order: 3,
  valid_to_chapter_id: 'chapter-6',
  valid_to_chapter_order: 6,
  source_start_offset: 140,
  source_end_offset: 170,
  evidence_text: '第三章沈砚暂为星火盟客卿，只负责护送旧城商队。',
  confidence: 0.76,
};

const changedAffiliation: TimelineEvent = {
  id: 'aff-guardian',
  project_id: 'project-timeline-1',
  organization_member_id: 'member-guardian',
  character_id: 'char-shen',
  organization_entity_id: 'org-starfire',
  event_type: 'affiliation',
  event_status: 'active',
  position: '护法',
  rank: 7,
  source_chapter_id: 'chapter-6',
  source_chapter_order: 6,
  valid_from_chapter_id: 'chapter-6',
  valid_from_chapter_order: 6,
  valid_to_chapter_id: 'chapter-10',
  valid_to_chapter_order: 10,
  source_start_offset: 176,
  source_end_offset: 224,
  evidence_text: '第六章星火盟正式授沈砚护法令，允许他调动巡夜队。',
  confidence: 0.88,
  supersedes_event_id: 'aff-guest',
};

const earlyProfessionCurrent: TimelineEvent = {
  id: 'prof-wanderer-current',
  project_id: 'project-timeline-1',
  character_id: 'char-shen',
  career_id: 'career-wanderer',
  event_type: 'profession',
  event_status: 'active',
  career_stage: 1,
  source_chapter_id: 'chapter-3',
  source_chapter_order: 3,
  valid_from_chapter_id: 'chapter-3',
  valid_from_chapter_order: 3,
  valid_to_chapter_id: 'chapter-6',
  valid_to_chapter_order: 6,
  source_start_offset: 42,
  source_end_offset: 60,
  evidence_text: '第三章沈砚仍以散修身份行走云海。',
  confidence: 0.79,
};

const supersededProfession: TimelineEvent = {
  ...earlyProfessionCurrent,
  id: 'prof-old',
  event_status: 'superseded',
};

const changedProfession: TimelineEvent = {
  id: 'prof-sword',
  project_id: 'project-timeline-1',
  character_id: 'char-shen',
  career_id: 'career-sword',
  event_type: 'profession',
  event_status: 'active',
  career_stage: 2,
  source_chapter_id: 'chapter-6',
  source_chapter_order: 6,
  valid_from_chapter_id: 'chapter-6',
  valid_from_chapter_order: 6,
  valid_to_chapter_id: 'chapter-10',
  valid_to_chapter_order: 10,
  source_start_offset: 230,
  source_end_offset: 260,
  evidence_text: '第六章沈砚正式转修剑道，突破至第二阶。',
  confidence: 0.91,
  supersedes_event_id: 'prof-old',
};

const rolledBackProfession: TimelineEvent = {
  id: 'prof-alchemy-rollback',
  project_id: 'project-timeline-1',
  character_id: 'char-shen',
  career_id: 'career-alchemy',
  event_type: 'profession',
  event_status: 'rolled_back',
  career_stage: 1,
  source_chapter_id: 'chapter-3',
  source_chapter_order: 3,
  valid_from_chapter_id: 'chapter-3',
  valid_from_chapter_order: 3,
  source_start_offset: 262,
  source_end_offset: 286,
  evidence_text: '炼丹尝试被后续评审回滚，不再作为当前职业。',
  confidence: 0.55,
};

const historyEvents: TimelineEvent[] = [
  earlyRelationship,
  changedRelationship,
  earlyAffiliation,
  changedAffiliation,
  supersededProfession,
  changedProfession,
  rolledBackProfession,
];

function stateForChapter(chapterNumber: number): TimelineStateResponse {
  const relationships = chapterNumber === 3
    ? [earlyRelationship]
    : chapterNumber === 6
      ? [changedRelationship]
      : [];
  const affiliations = chapterNumber === 3
    ? [earlyAffiliation]
    : chapterNumber === 6
      ? [changedAffiliation]
      : [];
  const professions = chapterNumber === 3
    ? [earlyProfessionCurrent]
    : chapterNumber === 6
      ? [changedProfession]
      : [];

  return {
    project_id: 'project-timeline-1',
    point: {
      chapter_id: `chapter-${chapterNumber}`,
      chapter_number: chapterNumber,
      chapter_order: chapterNumber,
    },
    relationships,
    affiliations,
    professions,
  };
}

function createTimelineApiClient(): TimelineApiClient {
  return {
    getProjectState: vi.fn<TimelineApiClient['getProjectState']>().mockImplementation(async (_projectId, params) => {
      const chapterNumber = params?.chapter_number ?? 10;
      return stateForChapter(chapterNumber);
    }),
    getProjectHistory: vi.fn<TimelineApiClient['getProjectHistory']>().mockImplementation(async (_projectId, params) => {
      const items = historyEvents.filter(event => !params?.event_type || event.event_type === params.event_type);
      return {
        project_id: 'project-timeline-1',
        event_type: params?.event_type ?? null,
        total: items.length,
        items,
      };
    }),
  };
}

async function delay(ms = 0): Promise<void> {
  await new Promise<void>(resolve => window.setTimeout(resolve, ms));
}

async function waitForAssertion(assertion: () => void): Promise<void> {
  let lastError: unknown;

  for (let attempt = 0; attempt < 30; attempt += 1) {
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

async function renderTimelinePanel(props: Partial<TimelinePanelProps>) {
  const apiClient = props.apiClient || createTimelineApiClient();
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);

  await act(async () => {
    root.render(
      <TimelineReviewPanel
        projectId="project-timeline-1"
        title="人物关系时间线"
        eventTypes={['relationship']}
        characters={characters}
        organizations={organizations}
        careers={careers}
        apiClient={apiClient}
        {...props}
      />,
    );
    await delay();
  });

  return {
    apiClient,
    container,
    async cleanup() {
      await act(async () => {
        root.unmount();
      });
      container.remove();
    },
  };
}

describe('timeline review panel', () => {
  it('shows chapter 3 current relationship projection with evidence and confidence', async () => {
    const view = await renderTimelinePanel({ defaultChapterNumber: 3 });

    try {
      await waitForAssertion(() => {
        expect(view.apiClient.getProjectState).toHaveBeenCalledWith('project-timeline-1', { chapter_number: 3, chapter_order: 3 });
        expect(view.container.textContent).toContain('当前坐标：第 3 章 / 顺序 3');
        expect(view.container.textContent).toContain('沈砚 ↔ 青岚');
        expect(view.container.textContent).toContain('师徒');
        expect(view.container.textContent).toContain('第三章，青岚收沈砚为徒');
        expect(view.container.textContent).toContain('置信度：93%');
        expect(view.container.textContent).toContain('生效中');
      });
    } finally {
      await view.cleanup();
    }
  });

  it('shows chapter 6 changed current relationship and removes the older projection', async () => {
    const view = await renderTimelinePanel({ defaultChapterNumber: 6 });

    try {
      await waitForAssertion(() => {
        expect(view.apiClient.getProjectState).toHaveBeenCalledWith('project-timeline-1', { chapter_number: 6, chapter_order: 6 });
        expect(TimelineReviewPanel.__testUtils.getTimelineEventsForTypes(stateForChapter(6), ['relationship']).map(event => event.id)).toEqual(['rel-alliance']);
        expect(view.container.textContent).toContain('同盟');
        expect(view.container.textContent).toContain('变更');
        expect(view.container.textContent).toContain('替换事件 rel-mentor');
      });
    } finally {
      await view.cleanup();
    }
  });

  it('keeps ended chapter 10 relationship out of current projection but visible in history', async () => {
    const view = await renderTimelinePanel({ defaultChapterNumber: 10, defaultMode: 'history' });

    try {
      await waitForAssertion(() => {
        expect(view.apiClient.getProjectState).toHaveBeenCalledWith('project-timeline-1', { chapter_number: 10, chapter_order: 10 });
        expect(TimelineReviewPanel.__testUtils.getTimelineEventsForTypes(stateForChapter(10), ['relationship'])).toHaveLength(0);
        expect(view.container.textContent).toContain('历史记录 (2)');
        expect(view.container.textContent).toContain('第六章二人平等立誓');
        expect(view.container.textContent).toContain('置信度：82%');
        expect(view.container.textContent).toContain('第 6 章 → 第 10 章前');
        expect(view.container.textContent).toContain('已结束');
        expect(view.container.textContent).toContain('替换事件 rel-mentor');
      });
    } finally {
      await view.cleanup();
    }
  });

  it('shows chapter 6 affiliation current projection with mapped organization names', async () => {
    const view = await renderTimelinePanel({
      defaultChapterNumber: 6,
      eventTypes: ['affiliation'],
      title: '组织归属时间线',
    });

    try {
      await waitForAssertion(() => {
        expect(view.apiClient.getProjectState).toHaveBeenCalledWith('project-timeline-1', { chapter_number: 6, chapter_order: 6 });
        expect(view.apiClient.getProjectHistory).toHaveBeenCalledWith('project-timeline-1', { event_type: 'affiliation' });
        expect(TimelineReviewPanel.__testUtils.getTimelineEventsForTypes(stateForChapter(6), ['affiliation']).map(event => event.id)).toEqual(['aff-guardian']);
        expect(view.container.textContent).toContain('组织归属');
        expect(view.container.textContent).toContain('沈砚 → 星火盟');
        expect(view.container.textContent).toContain('护法 · 等级 7');
        expect(view.container.textContent).toContain('第六章星火盟正式授沈砚护法令');
        expect(view.container.textContent).toContain('置信度：88%');
        expect(view.container.textContent).toContain('生效中');
      });
    } finally {
      await view.cleanup();
    }
  });

  it('keeps ended affiliation history visible after chapter 10 projection closes it', async () => {
    const view = await renderTimelinePanel({
      defaultChapterNumber: 10,
      defaultMode: 'history',
      eventTypes: ['affiliation'],
      title: '组织归属时间线',
    });

    try {
      await waitForAssertion(() => {
        expect(view.apiClient.getProjectState).toHaveBeenCalledWith('project-timeline-1', { chapter_number: 10, chapter_order: 10 });
        expect(TimelineReviewPanel.__testUtils.getTimelineEventsForTypes(stateForChapter(10), ['affiliation'])).toHaveLength(0);
        expect(view.container.textContent).toContain('历史记录 (2)');
        expect(view.container.textContent).toContain('沈砚 → 星火盟');
        expect(view.container.textContent).toContain('客卿 · 等级 3');
        expect(view.container.textContent).toContain('第三章沈砚暂为星火盟客卿');
        expect(view.container.textContent).toContain('第 3 章 → 第 6 章前');
        expect(view.container.textContent).toContain('已结束');
        expect(view.container.textContent).toContain('替换事件 aff-guest');
      });
    } finally {
      await view.cleanup();
    }
  });

  it('shows chapter 6 profession current projection with mapped career names', async () => {
    const view = await renderTimelinePanel({
      defaultChapterNumber: 6,
      eventTypes: ['profession'],
      title: '职业时间线',
    });

    try {
      await waitForAssertion(() => {
        expect(view.apiClient.getProjectState).toHaveBeenCalledWith('project-timeline-1', { chapter_number: 6, chapter_order: 6 });
        expect(view.apiClient.getProjectHistory).toHaveBeenCalledWith('project-timeline-1', { event_type: 'profession' });
        expect(TimelineReviewPanel.__testUtils.getTimelineEventsForTypes(stateForChapter(6), ['profession']).map(event => event.id)).toEqual(['prof-sword']);
        expect(view.container.textContent).toContain('职业变更');
        expect(view.container.textContent).toContain('沈砚 → 剑修');
        expect(view.container.textContent).toContain('第 2 阶');
        expect(view.container.textContent).toContain('第六章沈砚正式转修剑道');
        expect(view.container.textContent).toContain('置信度：91%');
        expect(view.container.textContent).toContain('生效中');
      });
    } finally {
      await view.cleanup();
    }
  });

  it('keeps ended, superseded, and rolled-back profession history visible after chapter 10', async () => {
    const view = await renderTimelinePanel({
      defaultChapterNumber: 10,
      defaultMode: 'history',
      eventTypes: ['profession'],
      title: '职业时间线',
    });

    try {
      await waitForAssertion(() => {
        expect(view.apiClient.getProjectState).toHaveBeenCalledWith('project-timeline-1', { chapter_number: 10, chapter_order: 10 });
        expect(TimelineReviewPanel.__testUtils.getTimelineEventsForTypes(stateForChapter(10), ['profession'])).toHaveLength(0);
        expect(view.container.textContent).toContain('历史记录 (3)');
        expect(view.container.textContent).toContain('沈砚 → 散修');
        expect(view.container.textContent).toContain('已被替换');
        expect(view.container.textContent).toContain('沈砚 → 剑修');
        expect(view.container.textContent).toContain('第 6 章 → 第 10 章前');
        expect(view.container.textContent).toContain('替换事件 prof-old');
        expect(view.container.textContent).toContain('沈砚 → 丹师');
        expect(view.container.textContent).toContain('炼丹尝试被后续评审回滚');
        expect(view.container.textContent).toContain('置信度：55%');
        expect(view.container.textContent).toContain('已回滚');
      });
    } finally {
      await view.cleanup();
    }
  });
});
