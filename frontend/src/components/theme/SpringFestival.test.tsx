import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('canvas-confetti', () => ({ default: vi.fn() }));

import SpringFestival from './SpringFestival';

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

const storage = new Map<string, string>();
const localStorageMock = {
  clear: () => storage.clear(),
  getItem: (key: string) => storage.get(key) ?? null,
  setItem: (key: string, value: string) => storage.set(key, value),
};

let root: Root;
let container: HTMLDivElement;

function renderFestival() {
  act(() => {
    root.render(<SpringFestival />);
  });
}

describe('SpringFestival motion values', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    Object.defineProperty(window, 'localStorage', { configurable: true, value: localStorageMock });
    localStorage.clear();
    localStorage.setItem('spring-festival-visible', 'false');
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1200 });
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 600 });
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
  });

  it('updates drag coordinates through CSS variables without sx rules', () => {
    renderFestival();

    const button = container.querySelector<HTMLButtonElement>('.sf-toggle-btn');
    expect(button).not.toBeNull();
    expect(button?.className).toBe('sf-toggle-btn');
    expect(button?.style.getPropertyValue('--sf-btn-x')).toBe('1178px');
    expect(button?.style.getPropertyValue('--sf-btn-y')).toBe('300px');

    act(() => {
      button?.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, clientX: 1178, clientY: 300 }));
    });
    act(() => {
      window.dispatchEvent(new MouseEvent('mousemove', { bubbles: true, clientX: 540, clientY: 160 }));
    });
    act(() => {
      window.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, clientX: 540, clientY: 160 }));
    });

    expect(button?.className.startsWith('sf-toggle-btn')).toBe(true);
    expect(button?.className).not.toContain('sx-');
    expect(button?.style.getPropertyValue('--sf-btn-y')).toBe('160px');
    expect(document.querySelector('style[data-app-runtime-styles]')).toBeNull();
  });

  it('keeps random falling values out of runtime stylesheet rules', () => {
    renderFestival();
    const button = container.querySelector<HTMLButtonElement>('.sf-toggle-btn');

    act(() => {
      button?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });

    const fallingItems = container.querySelectorAll<HTMLElement>('.sf-falling-item');
    expect(fallingItems).toHaveLength(12);
    expect(Array.from(fallingItems).every(item => item.className === 'sf-falling-item')).toBe(true);
    expect(Array.from(fallingItems).every(item => item.style.getPropertyValue('--sf-falling-size').endsWith('px'))).toBe(true);

    act(() => {
      vi.advanceTimersByTime(30_000);
    });

    expect(container.querySelectorAll('.sf-falling-item')).toHaveLength(16);
    expect(document.querySelector('style[data-app-runtime-styles]')).toBeNull();
  });
});
