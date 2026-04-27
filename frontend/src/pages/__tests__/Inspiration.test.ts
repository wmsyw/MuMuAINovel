import { describe, expect, it, vi } from 'vitest';

import type { Project } from '../../types';
import Inspiration from '../Inspiration';

const inspirationUtils = Inspiration.__testUtils;

const wizardData = {
  title: '星桥尽头',
  description: '远航者在星桥断裂后寻找归途。',
  theme: '流亡与归属',
  genre: ['科幻', '冒险'],
  narrative_perspective: '第三人称',
  outline_mode: 'one-to-many' as const,
};

const projectDraft: Project = {
  id: 'project-draft-1',
  title: wizardData.title,
  description: wizardData.description,
  theme: wizardData.theme,
  genre: '科幻、冒险',
  target_words: 100000,
  current_words: 0,
  status: 'planning',
  outline_mode: 'one-to-many',
  created_at: '2026-04-27T00:00:00Z',
  updated_at: '2026-04-27T00:00:00Z',
};

function createMemoryStorage(onSetItem?: (key: string, value: string) => void): Storage {
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
      onSetItem?.(key, value);
    },
  };
}

describe('Inspiration draft/candidate-safe actions', () => {
  it('builds a project draft payload without canonical world/entity mutations', () => {
    const payload = inspirationUtils.buildProjectDraftPayload(wizardData);

    expect(payload).toEqual({
      title: '星桥尽头',
      description: '远航者在星桥断裂后寻找归途。',
      theme: '流亡与归属',
      genre: '科幻、冒险',
      target_words: 100000,
      outline_mode: 'one-to-many',
    });
    expect(payload).not.toHaveProperty('world_time_period');
    expect(payload).not.toHaveProperty('world_location');
    expect(payload).not.toHaveProperty('world_atmosphere');
    expect(payload).not.toHaveProperty('world_rules');
  });

  it('creates an inspiration project draft through the draft API path and never calls canonical entity create endpoints', async () => {
    const canonicalCreateCharacter = vi.fn();
    const canonicalCreateCareer = vi.fn();
    const canonicalCreateOrganization = vi.fn();
    const clients = {
      saveInspiration: vi.fn(),
      createProjectDraft: vi.fn().mockResolvedValue(projectDraft),
      createCharacter: canonicalCreateCharacter,
      createCareer: canonicalCreateCareer,
      createOrganization: canonicalCreateOrganization,
    };

    const result = await inspirationUtils.runInspirationDraftAction(
      'create_project_draft',
      wizardData,
      '想写一部星桥断裂后的归乡故事',
      clients,
    );

    expect(result).toEqual(projectDraft);
    expect(clients.createProjectDraft).toHaveBeenCalledWith({
      title: '星桥尽头',
      description: '远航者在星桥断裂后寻找归途。',
      theme: '流亡与归属',
      genre: '科幻、冒险',
      target_words: 100000,
      outline_mode: 'one-to-many',
    });
    expect(clients.saveInspiration).not.toHaveBeenCalled();
    expect(canonicalCreateCharacter).not.toHaveBeenCalled();
    expect(canonicalCreateCareer).not.toHaveBeenCalled();
    expect(canonicalCreateOrganization).not.toHaveBeenCalled();
  });

  it('saves inspiration ideas as local drafts by default', () => {
    const savedDrafts: string[] = [];
    const storage = createMemoryStorage((_key, value) => {
      savedDrafts.push(value);
    });
    const draft = inspirationUtils.normalizeWizardData(wizardData, '星桥断裂后的归乡故事');

    inspirationUtils.saveInspirationDraftToStorage(draft, storage);

    expect(inspirationUtils.INSPIRATION_DRAFTS_KEY).toBe('inspiration_saved_drafts');
    expect(savedDrafts).toHaveLength(1);
    expect(JSON.parse(savedDrafts[0])).toEqual([draft]);
  });
});
