import { describe, expect, it } from 'vitest';
import { sx } from './sx';

function runtimeStyleSheet(): CSSStyleSheet {
  const style = document.querySelector<HTMLStyleElement>('style[data-app-runtime-styles]');
  expect(style?.sheet).toBeTruthy();
  return style!.sheet!;
}

describe('sx runtime styles', () => {
  it('keeps WebkitLineClamp unitless', () => {
    const className = sx({
      display: '-webkit-box',
      WebkitLineClamp: 2,
      WebkitBoxOrient: 'vertical',
    });

    const cssRule = Array.from(runtimeStyleSheet().cssRules)
      .find(rule => rule.cssText.includes(`.${className}`));

    expect(cssRule?.cssText).toContain('-webkit-line-clamp: 2 !important');
    expect(cssRule?.cssText).not.toContain('-webkit-line-clamp: 2px');
  });

  it('reuses a variable-backed class for changing coordinates', () => {
    const style = { top: 'var(--toolbar-top)', left: 'var(--toolbar-left)' };
    const className = sx(style);
    const sheet = runtimeStyleSheet();
    const ruleCount = sheet.cssRules.length;

    for (let coordinate = 0; coordinate < 100; coordinate += 1) {
      const element = document.createElement('div');
      element.className = className;
      element.style.setProperty('--toolbar-top', `${coordinate}px`);
      element.style.setProperty('--toolbar-left', `${coordinate * 2}px`);
    }

    expect(sx(style)).toBe(className);
    expect(runtimeStyleSheet().cssRules.length).toBe(ruleCount);
  });
});
