import { useEffect } from 'react';
import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, describe, expect, it } from 'vitest';

import { useStore } from '../store';
import { useCharacterSync, useChapterSync, useOutlineSync } from '../store/hooks';
import type { Project } from '../types';

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

const baseProject: Project = {
  id: 'project-refresh-stability',
  title: '回调稳定性项目',
  description: '用于验证项目刷新 hook 不随 currentProject 写入抖动',
  theme: '稳定刷新',
  genre: '测试',
  target_words: 100000,
  current_words: 0,
  status: 'planning',
  outline_mode: 'one-to-many',
  world_time_period: '旧历三百年',
  world_location: '雾港',
  world_atmosphere: '克制',
  world_rules: '灯不灭，夜不乱',
  created_at: '2026-04-27T00:00:00Z',
  updated_at: '2026-04-27T00:00:00Z',
};

type HookSnapshot = {
  projectId?: string;
  projectTitle?: string;
  refreshCharacters: ReturnType<typeof useCharacterSync>['refreshCharacters'];
  refreshOutlines: ReturnType<typeof useOutlineSync>['refreshOutlines'];
  refreshChapters: ReturnType<typeof useChapterSync>['refreshChapters'];
};

function HookIdentityProbe({ onSample }: { onSample: (snapshot: HookSnapshot) => void }) {
  const currentProject = useStore(state => state.currentProject);
  const projectId = currentProject?.id;
  const projectTitle = currentProject?.title;
  const { refreshCharacters } = useCharacterSync();
  const { refreshOutlines } = useOutlineSync();
  const { refreshChapters } = useChapterSync();

  useEffect(() => {
    onSample({
      projectId,
      projectTitle,
      refreshCharacters,
      refreshOutlines,
      refreshChapters,
    });
  }, [projectId, projectTitle, refreshCharacters, refreshOutlines, refreshChapters, onSample]);

  return null;
}

function getLastSample(samples: HookSnapshot[]): HookSnapshot | undefined {
  return samples[samples.length - 1];
}

async function delay(ms = 0): Promise<void> {
  await new Promise<void>(resolve => window.setTimeout(resolve, ms));
}

afterEach(() => {
  useStore.setState({
    currentProject: null,
    outlines: [],
    characters: [],
    chapters: [],
    currentChapter: null,
    loading: false,
  });
});

describe('store refresh hooks', () => {
  it('keeps project refresh callback identities stable across currentProject writes', async () => {
    const samples: HookSnapshot[] = [];
    const container = document.createElement('div');
    document.body.appendChild(container);
    const root = createRoot(container);

    try {
      await act(async () => {
        root.render(<HookIdentityProbe onSample={snapshot => samples.push(snapshot)} />);
        await delay();
      });

      expect(samples).toHaveLength(1);
      const initialSnapshot = samples[0];
      expect(initialSnapshot.projectId).toBeUndefined();

      await act(async () => {
        useStore.getState().setCurrentProject(baseProject);
        await delay();
      });

      const loadedProjectSnapshot = getLastSample(samples);
      expect(loadedProjectSnapshot?.projectId).toBe(baseProject.id);
      expect(loadedProjectSnapshot?.refreshCharacters).toBe(initialSnapshot.refreshCharacters);
      expect(loadedProjectSnapshot?.refreshOutlines).toBe(initialSnapshot.refreshOutlines);
      expect(loadedProjectSnapshot?.refreshChapters).toBe(initialSnapshot.refreshChapters);

      await act(async () => {
        useStore.getState().setCurrentProject({
          ...baseProject,
          title: '世界观接受后更新的项目对象',
          world_location: '浮空群岛',
          updated_at: '2026-04-27T01:00:00Z',
        });
        await delay();
      });

      const updatedProjectSnapshot = getLastSample(samples);
      expect(updatedProjectSnapshot?.projectTitle).toBe('世界观接受后更新的项目对象');
      expect(updatedProjectSnapshot?.refreshCharacters).toBe(initialSnapshot.refreshCharacters);
      expect(updatedProjectSnapshot?.refreshOutlines).toBe(initialSnapshot.refreshOutlines);
      expect(updatedProjectSnapshot?.refreshChapters).toBe(initialSnapshot.refreshChapters);
    } finally {
      await act(async () => {
        root.unmount();
      });
      container.remove();
    }
  });
});
