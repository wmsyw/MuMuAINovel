import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  type InspirationDirectionCard,
  type InspirationStoryBibleDraft,
} from '../../types';

const mocks = vi.hoisted(() => ({
  post: vi.fn((url: string, data?: unknown) => Promise.resolve({ url, data })),
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

import { inspirationApi } from '../api';

const sampleCard: InspirationDirectionCard = {
  id: 'card-1',
  title: '星桥尽头',
  hook: '断裂星桥后的归乡承诺',
  genre: ['科幻', '冒险'],
  world_setting: '星桥税则限制航行，记忆可作为燃料。',
  core_conflict: '修复星桥需要牺牲故乡的最后坐标。',
  protagonist: '失忆星图师',
  golden_finger: '读取星桥残响',
  opening_hook: '主角醒来时，自己的记忆正在被拍卖。',
  selling_points: ['记忆交易', '星桥谜团'],
  risks: ['世界规则复杂', '情感线需要收束'],
};

const anotherCard: InspirationDirectionCard = {
  ...sampleCard,
  id: 'card-2',
  title: '云城回声',
};

const storyBibleDraft: InspirationStoryBibleDraft = {
  core_idea: '星桥断裂后的归乡故事',
  story_promise: '每次修复都要付出一段真实记忆。',
  target_genre: ['科幻', '冒险'],
  world_rules: ['星桥以记忆为燃料', '月潮决定城市边界'],
  core_conflict: '归乡与牺牲故乡坐标之间的两难。',
  protagonist_profile: '失忆星图师，擅长解读星桥残响。',
  antagonistic_force: '封锁星桥的云城议会。',
  golden_finger: '读取星桥残响',
  opening_hook: '主角发现自己的童年被列入拍卖目录。',
  tone_and_style: '克制、浪漫、带悬疑感。',
  foreshadowing_seeds: ['旧星图上的缺失坐标', '反复出现的月潮钟声'],
  constraints: ['不直接创建角色或世界观记录'],
};

beforeEach(() => {
  mocks.post.mockClear();
  mocks.get.mockClear();
  mocks.put.mockClear();
  mocks.delete.mockClear();
});

describe('inspirationApi shared optimization contracts', () => {
  it('maps direction card, story bible, evaluate, and repair contracts to /api inspiration routes', async () => {
    await inspirationApi.generateCards({
      idea: '星桥断裂后的归乡故事',
      context: { theme: '流亡与归属' },
      card_count: 3,
    });
    await inspirationApi.mergeCards({ cards: [sampleCard, anotherCard], primary_card_id: sampleCard.id });
    await inspirationApi.generateStoryBible({ idea: '星桥断裂后的归乡故事', direction_card: sampleCard });
    await inspirationApi.evaluate({ story_bible_draft: storyBibleDraft });
    await inspirationApi.repair({ draft: storyBibleDraft, issue_ids: ['consistency-1'] });

    expect(mocks.post).toHaveBeenNthCalledWith(1, '/inspiration/generate-cards', {
      idea: '星桥断裂后的归乡故事',
      context: { theme: '流亡与归属' },
      card_count: 3,
    });
    expect(mocks.post).toHaveBeenNthCalledWith(2, '/inspiration/merge-cards', {
      cards: [sampleCard, anotherCard],
      primary_card_id: sampleCard.id,
    });
    expect(mocks.post).toHaveBeenNthCalledWith(3, '/inspiration/generate-story-bible', {
      idea: '星桥断裂后的归乡故事',
      direction_card: sampleCard,
    });
    expect(mocks.post).toHaveBeenNthCalledWith(4, '/inspiration/evaluate', {
      story_bible_draft: storyBibleDraft,
    });
    expect(mocks.post).toHaveBeenNthCalledWith(5, '/inspiration/repair', {
      draft: storyBibleDraft,
      issue_ids: ['consistency-1'],
    });
  });
  it('serializes platform, channel, and refinement fields for batch generation', async () => {
    await inspirationApi.batchGenerate({
      base_idea: '星桥断裂后的归乡故事',
      platform: 'qidian',
      channel: '男频',
      genre_tags: ['科幻'],
      plot_keywords: ['归乡'],
      character_traits: ['失忆'],
      count: 3,
      extra_requirement: '强化第一章悬念',
      previous_cards: [sampleCard],
    });

    expect(mocks.post).toHaveBeenCalledWith('/inspiration/batch-generate', {
      base_idea: '星桥断裂后的归乡故事',
      platform: 'qidian',
      channel: '男频',
      genre_tags: ['科幻'],
      plot_keywords: ['归乡'],
      character_traits: ['失忆'],
      count: 3,
      extra_requirement: '强化第一章悬念',
      previous_cards: [sampleCard],
    });
  });
});
