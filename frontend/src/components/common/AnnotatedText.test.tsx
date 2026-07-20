import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { ConfigProvider } from 'antd';

import AnnotatedText, { type MemoryAnnotation } from './AnnotatedText';

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

const annotation: MemoryAnnotation = {
  id: 'annotation-1',
  type: 'hook',
  title: '伏笔',
  content: '一枚旧钥匙',
  importance: 1,
  position: 0,
  length: 5,
  tags: [],
  metadata: {},
};

let root: Root;
let container: HTMLDivElement;

function renderAnnotatedText(colorError: string) {
  act(() => {
    root.render(
      <ConfigProvider
        theme={{
          token: {
            colorError,
            colorInfo: '#1677ff',
            colorSuccess: '#52c41a',
            colorWarning: '#faad14',
          },
        }}
      >
        <AnnotatedText
          content="一枚旧钥匙静静躺在桌上。"
          annotations={[annotation]}
          activeAnnotationId={annotation.id}
        />
      </ConfigProvider>,
    );
  });
}

describe('AnnotatedText responsive annotation styles', () => {
  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it('keeps one stable rule while updating annotation variables', () => {
    renderAnnotatedText('#d4380d');
    const segment = container.querySelector<HTMLElement>('[data-annotation-id="annotation-1"]');
    expect(segment).not.toBeNull();
    const className = segment?.className;
    const style = document.querySelector<HTMLStyleElement>('style[data-app-runtime-styles]');
    const ruleCount = style?.sheet?.cssRules.length;

    expect(segment?.style.getPropertyValue('--annotation-color')).toBe('#d4380d');
    expect(segment?.style.getPropertyValue('--annotation-background-color')).toContain('#d4380d');

    renderAnnotatedText('#cf1322');
    const rerenderedSegment = container.querySelector<HTMLElement>('[data-annotation-id="annotation-1"]');

    expect(rerenderedSegment?.className).toBe(className);
    expect(rerenderedSegment?.style.getPropertyValue('--annotation-color')).toBe('#cf1322');
    expect(rerenderedSegment?.style.getPropertyValue('--annotation-background-color')).toContain('#cf1322');
    expect(style?.sheet?.cssRules.length).toBe(ruleCount);
  });
});
