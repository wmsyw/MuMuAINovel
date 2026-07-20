import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import PartialRegenerateToolbar from './PartialRegenerateToolbar';

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

let root: Root;
let container: HTMLDivElement;

function renderToolbar(position: { top: number; left: number }, visible = true) {
  act(() => {
    root.render(
      <PartialRegenerateToolbar
        visible={visible}
        position={position}
        onRegenerate={vi.fn()}
        selectedText="一段需要重新生成的内容"
      />,
    );
  });
}

describe('PartialRegenerateToolbar positioning', () => {
  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it('updates position variables without generating coordinate classes', () => {
    renderToolbar({ top: 12, left: 34 });
    const toolbar = container.firstElementChild as HTMLDivElement;
    const className = toolbar.className;
    const style = document.querySelector<HTMLStyleElement>('style[data-app-runtime-styles]');
    const ruleCount = style?.sheet?.cssRules.length;

    expect(toolbar.style.getPropertyValue('--partial-regenerate-top')).toBe('12px');
    expect(toolbar.style.getPropertyValue('--partial-regenerate-left')).toBe('34px');

    renderToolbar({ top: 420.5, left: 860.25 });

    expect(toolbar.className).toBe(className);
    expect(toolbar.style.getPropertyValue('--partial-regenerate-top')).toBe('420.5px');
    expect(toolbar.style.getPropertyValue('--partial-regenerate-left')).toBe('860.25px');
    expect(style?.sheet?.cssRules.length).toBe(ruleCount);
  });

  it('initializes variables when the toolbar mounts after being hidden', () => {
    renderToolbar({ top: 90, left: 140 }, false);
    expect(container.firstElementChild).toBeNull();

    renderToolbar({ top: 90, left: 140 });
    const toolbar = container.firstElementChild as HTMLDivElement;

    expect(toolbar.style.getPropertyValue('--partial-regenerate-top')).toBe('90px');
    expect(toolbar.style.getPropertyValue('--partial-regenerate-left')).toBe('140px');
  });
});
