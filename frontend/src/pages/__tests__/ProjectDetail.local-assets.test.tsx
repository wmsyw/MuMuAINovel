import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useStore } from '../../store';
import type { FeatureFlags, Project } from '../../types';

const mocks = vi.hoisted(() => ({
  getProject: vi.fn(),
  getFeatureFlags: vi.fn(),
  refreshCharacters: vi.fn(),
  refreshOutlines: vi.fn(),
  refreshChapters: vi.fn(),
}));

vi.mock('../../services/api', () => ({
  projectApi: {
    getProject: mocks.getProject,
  },
  settingsApi: {
    getFeatureFlags: mocks.getFeatureFlags,
  },
}));

vi.mock('../../store/hooks', () => ({
  useCharacterSync: () => ({ refreshCharacters: mocks.refreshCharacters }),
  useOutlineSync: () => ({ refreshOutlines: mocks.refreshOutlines }),
  useChapterSync: () => ({ refreshChapters: mocks.refreshChapters }),
}));

vi.mock('../../components/common/ThemeSwitch', () => ({
  default: () => null,
}));

vi.mock('../../components/FloatingTaskPanel', () => ({
  default: () => null,
}));

vi.mock('../../theme/useThemeMode', () => ({
  useThemeMode: () => ({
    mode: 'light',
    resolvedMode: 'light',
    setMode: vi.fn(),
  }),
}));

import ProjectDetail from '../ProjectDetail';

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

const baseProject: Project = {
  id: 'project-local-assets-1',
  title: '本地资源守门测试',
  description: '验证默认关闭时不会暴露本地资源入口',
  theme: '守门与回退',
  genre: '测试',
  target_words: 100000,
  current_words: 1200,
  status: 'writing',
  outline_mode: 'one-to-many',
  created_at: '2026-05-23T00:00:00Z',
  updated_at: '2026-05-23T00:00:00Z',
};

async function delay(ms = 0): Promise<void> {
  await new Promise<void>(resolve => window.setTimeout(resolve, ms));
}

async function waitForAssertion(assertion: () => void): Promise<void> {
  let lastError: unknown;

  for (let attempt = 0; attempt < 40; attempt += 1) {
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

async function renderProjectDetail(initialPath: string) {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);

  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/project/:projectId/*" element={<ProjectDetail />}>
            <Route path="world-setting" element={<div data-testid="world-setting-page">世界设定页面</div>} />
            <Route path="local-assets" element={<div data-testid="local-assets-page">本地资源页面</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
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

afterEach(() => {
  useStore.setState({
    currentProject: null,
    loading: false,
    outlines: [],
    characters: [],
    chapters: [],
  });
});

describe('ProjectDetail local-assets feature gate', () => {
  it('redirects direct local-assets navigation when the feature is disabled', async () => {
    mocks.getProject.mockResolvedValueOnce(baseProject);
    mocks.getFeatureFlags.mockResolvedValueOnce({ local_assets_enabled: false } satisfies FeatureFlags);
    mocks.refreshOutlines.mockResolvedValueOnce([]);
    mocks.refreshCharacters.mockResolvedValueOnce([]);
    mocks.refreshChapters.mockResolvedValueOnce([]);

    const view = await renderProjectDetail(`/project/${baseProject.id}/local-assets`);

    try {
      await waitForAssertion(() => {
        expect(view.container.querySelector('[data-testid="world-setting-page"]')).not.toBeNull();
        expect(view.container.querySelector('[data-testid="local-assets-page"]')).toBeNull();
        expect(view.container.querySelector('a[href="/project/project-local-assets-1/local-assets"]')).toBeNull();
      });
    } finally {
      await view.cleanup();
    }
  });

  it('shows the local-assets entry and page when the feature is enabled', async () => {
    mocks.getProject.mockResolvedValueOnce(baseProject);
    mocks.getFeatureFlags.mockResolvedValueOnce({ local_assets_enabled: true } satisfies FeatureFlags);
    mocks.refreshOutlines.mockResolvedValueOnce([]);
    mocks.refreshCharacters.mockResolvedValueOnce([]);
    mocks.refreshChapters.mockResolvedValueOnce([]);

    const view = await renderProjectDetail(`/project/${baseProject.id}/local-assets`);

    try {
      await waitForAssertion(() => {
        expect(view.container.querySelector('[data-testid="local-assets-page"]')).not.toBeNull();
        expect(view.container.querySelector('[data-testid="world-setting-page"]')).toBeNull();
        expect(view.container.querySelector('a[href="/project/project-local-assets-1/local-assets"]')).not.toBeNull();
      });
    } finally {
      await view.cleanup();
    }
  });
});
