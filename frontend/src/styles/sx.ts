import type { CSSProperties } from 'react';

type StyleObject = CSSProperties | Record<string, unknown>;
type StyleInput = string | StyleObject | false | null | undefined;

const unitlessProperties = new Set([
  'animationIterationCount', 'aspectRatio', 'borderImageOutset', 'borderImageSlice',
  'borderImageWidth', 'boxFlex', 'boxFlexGroup', 'boxOrdinalGroup', 'columnCount',
  'columns', 'fillOpacity', 'flex', 'flexGrow', 'flexNegative', 'flexOrder',
  'flexPositive', 'flexShrink', 'floodOpacity', 'fontWeight', 'gridArea',
  'gridColumn', 'gridColumnEnd', 'gridColumnSpan', 'gridColumnStart', 'gridRow',
  'gridRowEnd', 'gridRowSpan', 'gridRowStart', 'lineClamp', 'lineHeight', 'opacity',
  'WebkitLineClamp',
  'order', 'orphans', 'scale', 'stopOpacity', 'strokeDasharray', 'strokeDashoffset',
  'strokeMiterlimit', 'strokeOpacity', 'strokeWidth', 'tabSize', 'widows', 'zIndex',
  'zoom',
]);

const classCache = new Map<string, string>();
const declarationCache = new Map<string, string>();

const toCssProperty = (property: string): string => {
  if (property.startsWith('--')) return property;
  const kebab = property.replace(/[A-Z]/g, letter => `-${letter.toLowerCase()}`);
  if (kebab.startsWith('webkit-')) return `-${kebab}`;
  if (kebab.startsWith('ms-')) return `-${kebab}`;
  return kebab;
};

const toCssValue = (property: string, value: unknown): string | null => {
  if (value === null || value === undefined || typeof value === 'boolean') return null;
  if (typeof value === 'number' && value !== 0 && !property.startsWith('--') && !unitlessProperties.has(property)) {
    return `${value}px`;
  }
  return String(value);
};

const styleToDeclaration = (style: StyleObject): string => Object.entries(style)
  .flatMap(([property, rawValue]) => {
    const value = toCssValue(property, rawValue);
    if (value === null) return [];
    const important = property.startsWith('--') ? '' : ' !important';
    return `${toCssProperty(property)}:${value}${important}`;
  })
  .join(';');

const hashDeclaration = (declaration: string): string => {
  let hash = 0x811c9dc5;
  for (let index = 0; index < declaration.length; index += 1) {
    hash ^= declaration.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(36);
};

const getStyleSheet = (): CSSStyleSheet | null => {
  if (typeof document === 'undefined') return null;
  let element = document.querySelector<HTMLStyleElement>('style[data-app-runtime-styles]');
  if (!element) {
    element = document.createElement('style');
    element.dataset.appRuntimeStyles = 'true';
    document.head.appendChild(element);
  }
  return element.sheet;
};

const getStyleClass = (style: StyleObject): string => {
  const declaration = styleToDeclaration(style);
  if (!declaration) return '';

  const cached = classCache.get(declaration);
  if (cached) return cached;

  const baseName = `sx-${hashDeclaration(declaration)}`;
  let className = baseName;
  let suffix = 1;
  while (declarationCache.has(className) && declarationCache.get(className) !== declaration) {
    className = `${baseName}-${suffix}`;
    suffix += 1;
  }

  classCache.set(declaration, className);
  declarationCache.set(className, declaration);
  getStyleSheet()?.insertRule(`.${className}{${declaration}}`);
  return className;
};

export const sx = (...inputs: StyleInput[]): string => inputs
  .flatMap(input => {
    if (!input) return [];
    if (typeof input === 'string') return input;
    return getStyleClass(input);
  })
  .filter(Boolean)
  .join(' ');
