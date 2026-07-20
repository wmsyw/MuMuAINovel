import type { InspirationStoryBibleDraft, WizardBasicInfo } from '../types';

export const INSPIRATION_DRAFTS_KEY = 'inspiration_saved_drafts';
export const PROJECT_WIZARD_DRAFT_KEY = 'project_wizard_form_draft_v1';
export const PROJECT_WIZARD_SESSION_KEY = 'project_wizard_session_id_v1';

export interface InspirationDraftRecord {
  id: string;
  title: string;
  description: string;
  theme: string;
  genre: string[];
  world_setting?: string;
  core_conflict?: string;
  protagonist?: string;
  golden_finger?: string | null;
  narrative_perspective: string;
  outline_mode: 'one-to-one' | 'one-to-many';
  initial_idea: string;
  story_bible_draft?: InspirationStoryBibleDraft;
  created_at: string;
  status: 'draft';
}

export interface ProjectWizardDraftScope {
  project_id?: string;
  session_id?: string;
}

export interface ProjectWizardFormDraft {
  values: Partial<WizardBasicInfo>;
  inspiration?: InspirationDraftRecord;
  inspiration_handoff_dismissed?: boolean;
  scope?: ProjectWizardDraftScope;
  updated_at: string;
}

export function saveInspirationDraftToStorage(
  draft: InspirationDraftRecord,
  storage: Storage = localStorage,
): void {
  const raw = storage.getItem(INSPIRATION_DRAFTS_KEY);
  const existing = raw ? JSON.parse(raw) as InspirationDraftRecord[] : [];
  storage.setItem(INSPIRATION_DRAFTS_KEY, JSON.stringify([draft, ...existing.filter(item => item.id !== draft.id)].slice(0, 20)));
}

export function loadInspirationDraft(
  id: string,
  storage: Storage = localStorage,
): InspirationDraftRecord | undefined {
  const raw = storage.getItem(INSPIRATION_DRAFTS_KEY);
  if (!raw) return undefined;

  try {
    return (JSON.parse(raw) as InspirationDraftRecord[]).find(draft => draft.id === id);
  } catch {
    return undefined;
  }
}

interface ProjectWizardDraftStore {
  version: 2;
  drafts: ProjectWizardFormDraft[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function getProjectWizardDrafts(storage: Storage): ProjectWizardFormDraft[] {
  const raw = storage.getItem(PROJECT_WIZARD_DRAFT_KEY);
  if (!raw) return [];

  try {
    const parsed: unknown = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed as ProjectWizardFormDraft[];
    }
    if (isRecord(parsed) && Array.isArray(parsed.drafts)) {
      return parsed.drafts as ProjectWizardFormDraft[];
    }
    if (isRecord(parsed) && isRecord(parsed.values)) {
      // Migrate the original single-draft object on the next write.
      return [parsed as unknown as ProjectWizardFormDraft];
    }
  } catch {
    storage.removeItem(PROJECT_WIZARD_DRAFT_KEY);
  }

  return [];
}

function getDraftScopeKey(scope?: ProjectWizardDraftScope): string {
  if (scope?.project_id) return `project:${scope.project_id}`;
  if (scope?.session_id) return `session:${scope.session_id}`;
  return 'legacy';
}

function writeProjectWizardDrafts(storage: Storage, drafts: ProjectWizardFormDraft[]): void {
  const store: ProjectWizardDraftStore = { version: 2, drafts };
  storage.setItem(PROJECT_WIZARD_DRAFT_KEY, JSON.stringify(store));
}

export function getProjectWizardSessionId(
  storage: Storage = localStorage,
): string {
  const existing = storage.getItem(PROJECT_WIZARD_SESSION_KEY);
  if (existing) return existing;

  const sessionId = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `wizard-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  storage.setItem(PROJECT_WIZARD_SESSION_KEY, sessionId);
  return sessionId;
}

export function getProjectWizardDraftScope(
  projectId?: string,
  storage: Storage = localStorage,
): ProjectWizardDraftScope {
  return projectId
    ? { project_id: projectId }
    : { session_id: getProjectWizardSessionId(storage) };
}

export function saveProjectWizardDraft(
  draft: ProjectWizardFormDraft,
  storage: Storage = localStorage,
): void {
  const scopeKey = getDraftScopeKey(draft.scope);
  const existing = getProjectWizardDrafts(storage);
  writeProjectWizardDrafts(storage, [
    draft,
    ...existing.filter(item => getDraftScopeKey(item.scope) !== scopeKey),
  ]);
}

export function moveProjectWizardDraft(
  storage: Storage,
  fromScope: ProjectWizardDraftScope,
  toScope: ProjectWizardDraftScope,
): ProjectWizardFormDraft | undefined {
  const draft = loadProjectWizardDraft(storage, fromScope);
  if (!draft) return undefined;

  if (getDraftScopeKey(fromScope) === getDraftScopeKey(toScope)) {
    return draft;
  }

  const movedDraft: ProjectWizardFormDraft = {
    ...draft,
    scope: toScope,
    updated_at: new Date().toISOString(),
  };
  saveProjectWizardDraft(movedDraft, storage);
  clearProjectWizardDraft(storage, fromScope);
  return movedDraft;
}

export function loadProjectWizardDraft(
  storage: Storage = localStorage,
  scope?: ProjectWizardDraftScope,
): ProjectWizardFormDraft | undefined {
  const drafts = getProjectWizardDrafts(storage);
  if (!scope) return drafts[0];

  const scopeKey = getDraftScopeKey(scope);
  const matching = drafts.find(item => getDraftScopeKey(item.scope) === scopeKey);
  if (matching) return matching;

  if (!scope.session_id) return undefined;

  const legacy = drafts.find(item => !item.scope);
  if (!legacy) return undefined;

  const migrated = { ...legacy, scope };
  writeProjectWizardDrafts(storage, [migrated, ...drafts.filter(item => item !== legacy)]);
  return migrated;
}

export function clearProjectWizardDraft(
  storage: Storage = localStorage,
  scope?: ProjectWizardDraftScope,
): void {
  if (!scope) {
    storage.removeItem(PROJECT_WIZARD_DRAFT_KEY);
    return;
  }

  const drafts = getProjectWizardDrafts(storage);
  const scopeKey = getDraftScopeKey(scope);
  const remaining = drafts.filter(item => getDraftScopeKey(item.scope) !== scopeKey);
  if (remaining.length === drafts.length) return;

  if (remaining.length === 0) {
    storage.removeItem(PROJECT_WIZARD_DRAFT_KEY);
  } else {
    writeProjectWizardDrafts(storage, remaining);
  }
}
