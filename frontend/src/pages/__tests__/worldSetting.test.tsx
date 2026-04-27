import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useStore } from '../../store';
import type { Project, WorldSettingResult, WorldSettingResultOperationResponse } from '../../types';
import WorldSetting from '../WorldSetting';

type WorldSettingApiClient = Parameters<typeof WorldSetting>[0]['apiClient'];

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
  id: 'project-world-1',
  title: '云海旧约',
  description: '旧城与云海之间的盟约故事',
  theme: '承诺与背叛',
  genre: '玄幻',
  target_words: 100000,
  current_words: 0,
  status: 'planning',
  outline_mode: 'one-to-many',
  world_time_period: '旧历三百年',
  world_location: '北境云海',
  world_atmosphere: '冷峻克制',
  world_rules: '灵潮每十年回落一次',
  narrative_perspective: '第三人称',
  created_at: '2026-04-27T00:00:00Z',
  updated_at: '2026-04-27T00:00:00Z',
};

const pendingResult: WorldSettingResult = {
  id: 'world-result-1',
  project_id: baseProject.id,
  status: 'pending',
  world_time_period: '新历元年',
  world_location: '浮空群岛',
  world_atmosphere: '明亮但紧张',
  world_rules: '岛屿以誓约维持悬浮',
  provider: 'openai',
  model: 'gpt-4.1',
  reasoning_intensity: 'medium',
  source_type: 'ai_world_generation',
  created_at: '2026-04-27T01:00:00Z',
};

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

function findButtonByText(container: HTMLElement, text: string): HTMLButtonElement {
  const button = Array.from(container.querySelectorAll('button')).find(element => element.textContent?.includes(text));
  if (!button) {
    throw new Error(`未找到按钮：${text}`);
  }
  return button;
}

async function renderWorldSetting(apiClient: NonNullable<WorldSettingApiClient>) {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);

  await act(async () => {
    root.render(<WorldSetting apiClient={apiClient} />);
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
  useStore.setState({ currentProject: null });
});

describe('WorldSetting result review flow', () => {
  it('accepts a pending world-setting result after review and refreshes the active snapshot', async () => {
    let items: WorldSettingResult[] = [pendingResult];
    const acceptedResult: WorldSettingResult = {
      ...pendingResult,
      status: 'accepted',
      accepted_at: '2026-04-27T01:05:00Z',
    };
    const operationResponse: WorldSettingResultOperationResponse = {
      changed: true,
      reason: 'accepted',
      result: acceptedResult,
      previous_result: null,
      active_world: {
        project_id: baseProject.id,
        world_time_period: '新历元年',
        world_location: '浮空群岛',
        world_atmosphere: '明亮但紧张',
        world_rules: '岛屿以誓约维持悬浮',
      },
    };
    const apiClient: NonNullable<WorldSettingApiClient> = {
      listResults: vi.fn<NonNullable<WorldSettingApiClient>['listResults']>().mockImplementation(async () => ({
        total: items.length,
        items,
      })),
      acceptResult: vi.fn<NonNullable<WorldSettingApiClient>['acceptResult']>().mockImplementation(async () => {
        items = [acceptedResult];
        return operationResponse;
      }),
      rejectResult: vi.fn<NonNullable<WorldSettingApiClient>['rejectResult']>(),
      rollbackResult: vi.fn<NonNullable<WorldSettingApiClient>['rollbackResult']>(),
    };

    useStore.setState({ currentProject: baseProject });
    const view = await renderWorldSetting(apiClient);

    try {
      await waitForAssertion(() => {
        expect(view.container.textContent).toContain('待评审');
        expect(view.container.textContent).toContain('浮空群岛');
        expect(view.container.textContent).toContain('当前生效');
        expect(view.container.textContent).toContain('候选结果');
      });

      await act(async () => {
        findButtonByText(view.container, '接受结果').dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
        await delay();
      });

      await waitForAssertion(() => {
        expect(apiClient.acceptResult).toHaveBeenCalledWith('world-result-1');
        expect(apiClient.listResults).toHaveBeenCalledTimes(2);
        expect(useStore.getState().currentProject?.world_time_period).toBe('新历元年');
        expect(useStore.getState().currentProject?.world_location).toBe('浮空群岛');
        expect(view.container.textContent).toContain('已生效');
      });
    } finally {
      await view.cleanup();
    }
  });
});
