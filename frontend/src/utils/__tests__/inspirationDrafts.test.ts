import { describe, expect, it } from 'vitest';

import {
  PROJECT_WIZARD_DRAFT_KEY,
  clearProjectWizardDraft,
  getProjectWizardDraftScope,
  loadProjectWizardDraft,
  moveProjectWizardDraft,
  saveProjectWizardDraft,
} from '../inspirationDrafts';
import type { ProjectWizardFormDraft } from '../inspirationDrafts';

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

const baseDraft: ProjectWizardFormDraft = {
  values: {
    title: '星桥尽头',
    description: '远航者在星桥断裂后寻找归途。',
    theme: '流亡与归属',
    genre: ['科幻'],
    chapter_count: 3,
    narrative_perspective: '第三人称',
    character_count: 5,
    target_words: 100000,
    outline_mode: 'one-to-one',
  },
  updated_at: '2026-07-20T00:00:00.000Z',
};

describe('project wizard draft storage', () => {
  it('keeps an unrelated session draft when a resumed project is completed', () => {
    const storage = createMemoryStorage();
    const sessionDraft = { ...baseDraft, scope: { session_id: 'session-a' } };
    const projectDraft = { ...baseDraft, scope: { project_id: 'project-b' } };

    saveProjectWizardDraft(sessionDraft, storage);
    saveProjectWizardDraft(projectDraft, storage);
    clearProjectWizardDraft(storage, { project_id: 'project-b' });

    expect(loadProjectWizardDraft(storage, { session_id: 'session-a' })).toEqual(sessionDraft);
    expect(loadProjectWizardDraft(storage, { project_id: 'project-b' })).toBeUndefined();
  });

  it('adopts the legacy single draft for a session and migrates it on load', () => {
    const storage = createMemoryStorage();
    storage.setItem(PROJECT_WIZARD_DRAFT_KEY, JSON.stringify(baseDraft));

    expect(loadProjectWizardDraft(storage, { session_id: 'session-a' })).toEqual({
      ...baseDraft,
      scope: { session_id: 'session-a' },
    });

    const scopedDraft = { ...baseDraft, scope: { session_id: 'session-a' } };
    saveProjectWizardDraft(scopedDraft, storage);
    const stored = JSON.parse(storage.getItem(PROJECT_WIZARD_DRAFT_KEY) ?? '{}') as {
      version: number;
      drafts: ProjectWizardFormDraft[];
    };
    expect(stored.drafts).toEqual([scopedDraft]);
  });

  it('uses a durable active scope for new-form drafts', () => {
    const storage = createMemoryStorage();

    const firstScope = getProjectWizardDraftScope(undefined, storage);
    const secondScope = getProjectWizardDraftScope(undefined, storage);

    expect(firstScope).toEqual(secondScope);
    expect(firstScope.session_id).toBeTruthy();
  });

  it('moves a new-form draft to its generated project scope', () => {
    const storage = createMemoryStorage();
    const activeScope = { session_id: 'active-new-draft' };
    const projectScope = { project_id: 'project-b' };
    const draft = { ...baseDraft, scope: activeScope };

    saveProjectWizardDraft(draft, storage);
    const moved = moveProjectWizardDraft(storage, activeScope, projectScope);

    expect(moved).toMatchObject({ scope: projectScope });
    expect(loadProjectWizardDraft(storage, projectScope)).toMatchObject({ scope: projectScope });
    expect(loadProjectWizardDraft(storage, activeScope)).toBeUndefined();
  });

  it('persists an inspiration handoff dismissal with the draft', () => {
    const storage = createMemoryStorage();
    const dismissedDraft = {
      ...baseDraft,
      inspiration_handoff_dismissed: true,
      scope: { session_id: 'session-a' },
    };

    saveProjectWizardDraft(dismissedDraft, storage);

    expect(loadProjectWizardDraft(storage, { session_id: 'session-a' })).toEqual(dismissedDraft);
  });
});
