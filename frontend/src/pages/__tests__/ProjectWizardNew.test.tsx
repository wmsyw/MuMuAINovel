import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import type { InspirationDraftRecord } from '../../utils/inspirationDrafts';
import { PROJECT_WIZARD_DRAFT_KEY, saveInspirationDraftToStorage } from '../../utils/inspirationDrafts';

const mocks = vi.hoisted(() => ({
  generatorProps: [] as Array<Record<string, unknown>>,
  navigate: vi.fn(),
}));

vi.mock('../../components/generation/AIProjectGenerator', async () => {
  const React = await import('react');

  return {
    AIProjectGenerator: (props: Record<string, unknown>) => {
      mocks.generatorProps.push(props);
      return React.createElement('div', { 'data-testid': 'ai-project-generator' }, 'generator');
    },
  };
});

vi.mock('react-router-dom', async importOriginal => {
  const actual = await importOriginal<typeof import('react-router-dom')>();

  return {
    ...actual,
    useNavigate: () => mocks.navigate,
  };
});

import ProjectWizardNew from '../ProjectWizardNew';

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

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

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

function createInspirationDraft(): InspirationDraftRecord {
  return {
    id: 'inspiration-wizard-test',
    title: '星桥尽头',
    description: '远航者在星桥断裂后寻找归途。',
    theme: '流亡与归属',
    genre: ['科幻'],
    narrative_perspective: '第三人称',
    outline_mode: 'one-to-one',
    initial_idea: '星桥断裂后的归乡故事',
    created_at: '2026-07-20T00:00:00.000Z',
    status: 'draft',
  };
}


function delay(ms = 0): Promise<void> {
  const { promise, resolve } = Promise.withResolvers<void>();
  window.setTimeout(resolve, ms);
  return promise;
}
async function renderWizard(initialEntry: string) {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);

  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={[initialEntry]}>
        <ProjectWizardNew />
      </MemoryRouter>,
    );
    await delay();
  });

  return {
    container,
    async cleanup() {
      await act(async () => {
        root.unmount();
        await delay();
      });
      container.remove();
    },
  };
}

function setInputValue(input: HTMLInputElement, value: string): void {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
  setter?.call(input, value);
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
}

beforeEach(() => {
  const localStorage = createMemoryStorage();
  const sessionStorage = createMemoryStorage();
  Object.defineProperty(window, 'localStorage', { configurable: true, value: localStorage });
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: localStorage });
  Object.defineProperty(window, 'sessionStorage', { configurable: true, value: sessionStorage });
  Object.defineProperty(globalThis, 'sessionStorage', { configurable: true, value: sessionStorage });
  localStorage.clear();
  sessionStorage.clear();
  mocks.generatorProps.length = 0;
  mocks.navigate.mockReset();
});

describe('ProjectWizardNew persistence', () => {
  it('submits unopened advanced defaults and keeps them after a basic-field edit', async () => {
    saveInspirationDraftToStorage(createInspirationDraft());
    const view = await renderWizard('/wizard?from_inspiration=inspiration-wizard-test');
    try {
      const titleInput = view.container.querySelector('input[placeholder="输入你的小说标题"]');
      expect(titleInput).toBeTruthy();
      await act(async () => {
        setInputValue(titleInput as HTMLInputElement, '星桥尽头（修订）');
      });

      const stored = JSON.parse(localStorage.getItem(PROJECT_WIZARD_DRAFT_KEY) ?? '{}') as {
        drafts?: Array<{ values?: Record<string, unknown>; scope?: Record<string, string> }>;
      };
      expect(stored.drafts?.[0]?.values).toMatchObject({
        narrative_perspective: '第三人称',
        character_count: 5,
        target_words: 100000,
        outline_mode: 'one-to-one',
      });

      const submitButton = Array.from(view.container.querySelectorAll('button')).find(button =>
        button.textContent?.includes('开始 AI 生成'),
      );
      expect(submitButton).toBeTruthy();
      await act(async () => {
        (submitButton as HTMLButtonElement).click();
        await delay();
      });

      const config = mocks.generatorProps[0]?.config as Record<string, unknown>;
      expect(config).toMatchObject({
        character_count: 5,
        target_words: 100000,
        outline_mode: 'one-to-one',
      });
      await act(async () => {
        const onProjectCreated = mocks.generatorProps[0]?.onProjectCreated as ((projectId: string) => void) | undefined;
        onProjectCreated?.('project-generated');
        await delay();
      });

      const moved = JSON.parse(localStorage.getItem(PROJECT_WIZARD_DRAFT_KEY) ?? '{}') as {
        drafts?: Array<{ scope?: Record<string, string> }>;
      };
      expect(moved.drafts?.[0]?.scope).toEqual({ project_id: 'project-generated' });

      await act(async () => {
        const onComplete = mocks.generatorProps[0]?.onComplete as ((projectId: string) => void) | undefined;
        onComplete?.('project-generated');
        await delay();
      });
      expect(localStorage.getItem(PROJECT_WIZARD_DRAFT_KEY)).toBeNull();
    } finally {
      await view.cleanup();
    }
  });

  it('restores matching generation context while keeping project fields authoritative', async () => {
    const persistedContext = {
      source: 'inspiration_story_bible',
      initial_idea: '星桥断裂后的归乡故事',
      confirmed_fields: { title: '旧标题' },
    };
    localStorage.setItem('wizard_project_id', 'project-resumed');
    localStorage.setItem('wizard_generation_data', JSON.stringify({
      title: '旧标题',
      inspiration_context: persistedContext,
    }));
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        title: '项目权威标题',
        description: '项目简介',
        theme: '项目主题',
        genre: '科幻',
        wizard_step: 3,
      }),
    }));

    const view = await renderWizard('/wizard?project_id=project-resumed');
    try {
      await act(async () => {
        await delay(10);
      });

      const config = mocks.generatorProps[0]?.config as Record<string, unknown>;
      expect(config).toMatchObject({
        title: '项目权威标题',
        inspiration_context: persistedContext,
      });
    } finally {
      await view.cleanup();
      vi.unstubAllGlobals();
    }
  });

  it('persists inspiration handoff dismissal across reload and resume', async () => {
    saveInspirationDraftToStorage(createInspirationDraft());
    const initial = await renderWizard('/wizard?from_inspiration=inspiration-wizard-test');

    try {
      const closeButton = initial.container.querySelector('.ant-alert-close-icon');
      expect(closeButton).toBeTruthy();
      await act(async () => {
        (closeButton as HTMLElement).click();
        await delay();
      });

      const stored = JSON.parse(localStorage.getItem(PROJECT_WIZARD_DRAFT_KEY) ?? '{}') as {
        drafts?: Array<{ inspiration?: unknown; inspiration_handoff_dismissed?: boolean }>;
      };
      expect(stored.drafts?.[0]).toMatchObject({ inspiration_handoff_dismissed: true });
      expect(stored.drafts?.[0]).not.toHaveProperty('inspiration');
    } finally {
      await initial.cleanup();
    }

    const reloaded = await renderWizard('/wizard');
    try {
      const continueButton = Array.from(reloaded.container.querySelectorAll('button')).find(button =>
        button.textContent?.includes('继续上次填写'),
      );
      expect(continueButton).toBeTruthy();
      await act(async () => {
        (continueButton as HTMLButtonElement).click();
        await delay();
      });
      expect(reloaded.container.querySelector('.ant-alert-success')).toBeNull();
    } finally {
      await reloaded.cleanup();
    }
  });
});
