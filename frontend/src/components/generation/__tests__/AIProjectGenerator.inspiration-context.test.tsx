import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { InspirationGenerationContext, InspirationStoryBibleDraft } from '../../../types';
import type { SSEClientOptions } from '../../../utils/sseClient';
import type { GenerationConfig } from '../AIProjectGenerator';

const mocks = vi.hoisted(() => ({
  generateWorldBuildingStream: vi.fn(),
  generateCareerSystemStream: vi.fn(),
  generateCharactersStream: vi.fn(),
  generateCompleteOutlineStream: vi.fn(),
  navigate: vi.fn(),
}));

vi.mock('../../../services/api', () => ({
  wizardStreamApi: {
    generateWorldBuildingStream: mocks.generateWorldBuildingStream,
    generateCareerSystemStream: mocks.generateCareerSystemStream,
    generateCharactersStream: mocks.generateCharactersStream,
    generateCompleteOutlineStream: mocks.generateCompleteOutlineStream,
  },
}));

vi.mock('react-router-dom', async importOriginal => {
  const actual = await importOriginal<typeof import('react-router-dom')>();

  return {
    ...actual,
    useNavigate: () => mocks.navigate,
  };
});

import { AIProjectGenerator } from '../AIProjectGenerator';

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

function createMemoryStorage(): Storage {
  const values = new Map<string, string>();

  return {
    get length() {
      return values.size;
    },
    clear() {
      values.clear();
    },
    getItem(key: string) {
      return values.get(key) ?? null;
    },
    key(index: number) {
      return Array.from(values.keys())[index] ?? null;
    },
    removeItem(key: string) {
      values.delete(key);
    },
    setItem(key: string, value: string) {
      values.set(key, value);
    },
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

  throw lastError ?? new Error('断言等待超时');
}

const storyBibleDraft: InspirationStoryBibleDraft = {
  core_idea: '断裂星桥后的归乡故事',
  story_promise: '每卷修复一段星桥，同时揭开故乡真相。',
  target_genre: ['科幻', '冒险'],
  world_rules: ['记忆可作为燃料', '星桥航线需要税印'],
  core_conflict: '主角必须在找回记忆和拯救同伴之间做选择。',
  protagonist_profile: '失忆星图师，谨慎但无法拒绝求救。',
  antagonistic_force: '垄断星桥税则的封锁联盟。',
  golden_finger: '读取星桥残响',
  opening_hook: '主角的最后一段童年记忆被公开拍卖。',
  tone_and_style: '奇观冒险与温暖群像并重。',
  foreshadowing_seeds: ['破损罗盘', '无名税印'],
  constraints: ['不提前揭底', '每卷解决一个航线问题'],
};

const inspirationContext: InspirationGenerationContext = {
  source: 'inspiration_story_bible',
  initial_idea: '星桥断裂后的归乡故事',
  confirmed_fields: {
    title: '星桥尽头',
    world_setting: '星桥税则限制航行，记忆可作为燃料。',
  },
  story_bible_draft: storyBibleDraft,
};

const baseConfig: GenerationConfig = {
  title: '星桥尽头',
  description: '远航者在星桥断裂后寻找归途。',
  theme: '流亡与归属',
  genre: ['科幻', '冒险'],
  narrative_perspective: '第三人称',
  target_words: 100000,
  chapter_count: 3,
  character_count: 5,
};

async function renderGenerator(config: GenerationConfig) {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);

  await act(async () => {
    root.render(
      <AIProjectGenerator
        config={config}
        storagePrefix="inspiration"
        onComplete={vi.fn()}
      />,
    );
    await delay();
  });

  return {
    async cleanup() {
      await act(async () => {
        root.unmount();
        await delay();
      });
      container.remove();
    },
  };
}

beforeEach(() => {
  const storage = createMemoryStorage();
  Object.defineProperty(window, 'localStorage', { configurable: true, value: storage });
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: storage });
  localStorage.clear();
  mocks.generateWorldBuildingStream.mockReset();
  mocks.generateCareerSystemStream.mockReset();
  mocks.generateCharactersStream.mockReset();
  mocks.generateCompleteOutlineStream.mockReset();
  mocks.navigate.mockReset();

  mocks.generateWorldBuildingStream.mockImplementation(async (_data: unknown, options?: SSEClientOptions) => {
    options?.onResult?.({
      project_id: 'project-generated',
      time_period: '星桥纪元',
      location: '断裂星桥',
      atmosphere: '浪漫冒险',
      rules: '记忆可作为燃料',
    });
    return {
      project_id: 'project-generated',
      time_period: '星桥纪元',
      location: '断裂星桥',
      atmosphere: '浪漫冒险',
      rules: '记忆可作为燃料',
    };
  });
  mocks.generateCareerSystemStream.mockImplementation(async (_data: unknown, options?: SSEClientOptions) => {
    options?.onResult?.({ main_careers_count: 0, sub_careers_count: 0, main_careers: [], sub_careers: [] });
    return { project_id: 'project-generated', main_careers_count: 0, sub_careers_count: 0, main_careers: [], sub_careers: [] };
  });
  mocks.generateCharactersStream.mockImplementation(async (_data: unknown, options?: SSEClientOptions) => {
    options?.onResult?.({ characters: [] });
    return { characters: [] };
  });
  mocks.generateCompleteOutlineStream.mockImplementation(async (_data: unknown, options?: SSEClientOptions) => {
    options?.onResult?.({ outlines: [] });
    return { outlines: [] };
  });
});

describe('AIProjectGenerator inspiration context handoff', () => {
  it('keeps legacy wizard-stream calls free of inspiration context', async () => {
    const view = await renderGenerator(baseConfig);

    try {
      await waitForAssertion(() => expect(mocks.generateCompleteOutlineStream).toHaveBeenCalledTimes(1));

      expect(mocks.generateWorldBuildingStream.mock.calls[0][0]).toEqual({
        title: '星桥尽头',
        description: '远航者在星桥断裂后寻找归途。',
        theme: '流亡与归属',
        genre: '科幻、冒险',
        narrative_perspective: '第三人称',
        target_words: 100000,
        chapter_count: 3,
        character_count: 5,
        outline_mode: 'one-to-many',
      });
      expect(mocks.generateCompleteOutlineStream.mock.calls[0][0]).toEqual({
        project_id: 'project-generated',
        chapter_count: 3,
        narrative_perspective: '第三人称',
        target_words: 100000,
      });
    } finally {
      await view.cleanup();
    }
  });

  it('navigates generated projects to the sponsor entry route', async () => {
    const view = await renderGenerator(baseConfig);

    try {
      await waitForAssertion(() => expect(mocks.generateCompleteOutlineStream).toHaveBeenCalledTimes(1));

      await act(async () => {
        await delay(1050);
      });

      expect(mocks.navigate).toHaveBeenCalledWith('/project/project-generated/sponsor');
    } finally {
      await view.cleanup();
    }
  });

  it('passes optional inspiration context only to worldbuilding and outline requests', async () => {
    const view = await renderGenerator({
      ...baseConfig,
      outline_mode: 'one-to-many',
      inspiration_context: inspirationContext,
    });

    try {
      await waitForAssertion(() => expect(mocks.generateCompleteOutlineStream).toHaveBeenCalledTimes(1));

      expect(mocks.generateWorldBuildingStream.mock.calls[0][0]).toMatchObject({
        title: '星桥尽头',
        outline_mode: 'one-to-many',
        inspiration_context: inspirationContext,
      });
      expect(mocks.generateCareerSystemStream.mock.calls[0][0]).toEqual({ project_id: 'project-generated' });
      expect(mocks.generateCharactersStream.mock.calls[0][0]).not.toHaveProperty('inspiration_context');
      expect(mocks.generateCompleteOutlineStream.mock.calls[0][0]).toMatchObject({
        project_id: 'project-generated',
        chapter_count: 3,
        narrative_perspective: '第三人称',
        target_words: 100000,
        inspiration_context: inspirationContext,
      });
    } finally {
      await view.cleanup();
    }
  });
});
