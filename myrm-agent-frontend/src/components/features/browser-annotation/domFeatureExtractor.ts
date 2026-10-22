/**
 * [INPUT]
 * ./browserAnnotationTypes (POS: ElementDomMetadata, BrowserAnnotationPin, AnnotationSubtreeGroup)
 *
 * [OUTPUT]
 * sanitizeElementTextAndHtml, generateCssSelector, extractComputedLayoutStyles, detectSubtreeBranch, partitionPinsBySubtree
 *
 * [POS]
 * DOM feature extraction, DLP data sanitization, and subtree partition utilities for pinpoint annotation.
 */

import type {
  AnnotationSubtreeGroup,
  BrowserAnnotationPin,
  ElementDomMetadata,
} from './browserAnnotationTypes';

const SENSITIVE_KEY_PATTERN = /(?:password|token|secret|api[_-]?key|auth|bearer|credentials)/i;
const SENSITIVE_VALUE_PATTERN = /((?:Bearer\s+|sk-|ghp_|eyJh)[a-zA-Z0-9._-]+)/gi;
const MAX_TEXT_LENGTH = 160;
const MAX_HTML_LENGTH = 500;

export function sanitizeElementTextAndHtml(
  rawHtml: string,
  rawText: string,
): { sanitizedHtml: string; sanitizedText: string } {
  let sanitizedHtml = rawHtml;

  // Mask password inputs
  sanitizedHtml = sanitizedHtml.replace(
    /(<input[^>]*type=["']password["'][^>]*value=["'])([^"']*)(["'][^>]*>)/gi,
    '$1[REDACTED]$3',
  );

  // Mask sensitive attribute values (e.g. data-token="...")
  sanitizedHtml = sanitizedHtml.replace(
    /([a-zA-Z0-9_-]*(?:token|secret|key|password|auth)[a-zA-Z0-9_-]*\s*=\s*["'])([^"']+)(["'])/gi,
    '$1[REDACTED]$3',
  );

  // Mask bearer tokens and typical API keys
  sanitizedHtml = sanitizedHtml.replace(SENSITIVE_VALUE_PATTERN, '[REDACTED_SECRET]');

  let sanitizedText = rawText.replace(SENSITIVE_VALUE_PATTERN, '[REDACTED_SECRET]');
  if (SENSITIVE_KEY_PATTERN.test(sanitizedText)) {
    sanitizedText = sanitizedText.replace(/(:\s*)([^\s,;]+)/g, '$1[REDACTED]');
  }

  if (sanitizedText.length > MAX_TEXT_LENGTH) {
    sanitizedText = `${sanitizedText.slice(0, MAX_TEXT_LENGTH)}...`;
  }
  if (sanitizedHtml.length > MAX_HTML_LENGTH) {
    sanitizedHtml = `${sanitizedHtml.slice(0, MAX_HTML_LENGTH)}...`;
  }

  return { sanitizedHtml, sanitizedText };
}

export function generateCssSelector(el: Element): string {
  if (el.id) {
    return `#${el.id}`;
  }

  const path: string[] = [];
  let current: Element | null = el;

  while (current && current.nodeType === Node.ELEMENT_NODE) {
    if (current.id) {
      path.unshift(`#${current.id}`);
      break;
    }

    const tagName = current.tagName.toLowerCase();
    if (tagName === 'html') {
      path.unshift('html');
      break;
    }
    if (tagName === 'body') {
      path.unshift('body');
      break;
    }

    const parent: Element | null = current.parentElement;
    if (!parent) {
      path.unshift(tagName);
      break;
    }

    const siblings = Array.from(parent.children).filter((c) => c.tagName.toLowerCase() === tagName);
    if (siblings.length === 1) {
      const classNames = Array.from(current.classList)
        .slice(0, 2)
        .filter((c) => !c.includes(':') && !c.includes('/'))
        .join('.');
      const segment = classNames.length > 0 ? `${tagName}.${classNames}` : tagName;
      path.unshift(segment);
    } else {
      const index = siblings.indexOf(current) + 1;
      path.unshift(`${tagName}:nth-of-type(${index})`);
    }

    current = parent;
  }

  return path.join(' > ');
}

export function extractComputedLayoutStyles(style: CSSStyleDeclaration): Record<string, string> {
  const properties = [
    'display',
    'flexDirection',
    'gridTemplateColumns',
    'position',
    'width',
    'height',
    'margin',
    'padding',
    'color',
    'backgroundColor',
    'fontSize',
    'borderWidth',
    'borderRadius',
    'zIndex',
  ] as const;

  const result: Record<string, string> = {};
  for (const prop of properties) {
    const val = (style as unknown as Record<string, string>)[prop];
    if (val && val !== 'none' && val !== 'normal' && val !== 'auto' && val !== 'rgba(0, 0, 0, 0)') {
      result[prop] = val;
    }
  }

  return result;
}

export function detectSubtreeBranch(el: Element): string {
  let current: Element | null = el;
  const semanticTags = new Set(['header', 'nav', 'aside', 'main', 'footer', 'section', 'article', 'form']);

  while (current && current !== document.body && current !== document.documentElement) {
    if (current.id) {
      return `#${current.id}`;
    }
    const tag = current.tagName.toLowerCase();
    if (semanticTags.has(tag)) {
      const parent = current.parentElement;
      if (parent) {
        const siblings = Array.from(parent.children).filter((c) => c.tagName.toLowerCase() === tag);
        if (siblings.length > 1) {
          const idx = siblings.indexOf(current) + 1;
          return `${tag}:nth-of-type(${idx})`;
        }
      }
      return tag;
    }
    current = current.parentElement;
  }

  return 'main-viewport';
}

export function extractElementDomMetadata(el: Element): ElementDomMetadata {
  const cssSelector = generateCssSelector(el);
  const tagName = el.tagName.toLowerCase();
  const classList = Array.from(el.classList);
  const rawOuterHtml = el.outerHTML ?? '';
  const rawInnerText = (el as HTMLElement).innerText ?? el.textContent ?? '';
  const { sanitizedHtml, sanitizedText } = sanitizeElementTextAndHtml(rawOuterHtml, rawInnerText);

  let computedStyles: Record<string, string> = {};
  if (typeof window !== 'undefined' && typeof window.getComputedStyle === 'function') {
    computedStyles = extractComputedLayoutStyles(window.getComputedStyle(el));
  }

  const subtreeBranch = detectSubtreeBranch(el);

  return {
    cssSelector,
    tagName,
    classList,
    sanitizedOuterHtml: sanitizedHtml,
    innerText: sanitizedText,
    computedStyles,
    subtreeBranch,
  };
}

export function partitionPinsBySubtree(pins: BrowserAnnotationPin[]): AnnotationSubtreeGroup[] {
  const groupMap = new Map<string, BrowserAnnotationPin[]>();

  for (const pin of pins) {
    const branchKey = pin.domMetadata?.subtreeBranch || 'general-layout';
    const existing = groupMap.get(branchKey);
    if (existing) {
      existing.push(pin);
    } else {
      groupMap.set(branchKey, [pin]);
    }
  }

  const groups: AnnotationSubtreeGroup[] = [];
  for (const [key, groupedPins] of groupMap.entries()) {
    let subtreeName = key;
    if (key.startsWith('#')) {
      subtreeName = `Module [${key}]`;
    } else if (key === 'header' || key === 'nav') {
      subtreeName = `Navigation Header`;
    } else if (key === 'aside') {
      subtreeName = `Sidebar Panel`;
    } else if (key === 'footer') {
      subtreeName = `Footer Area`;
    } else {
      subtreeName = `Content Section (${key})`;
    }

    groups.push({
      subtreeKey: key,
      subtreeName,
      pins: groupedPins,
    });
  }

  return groups;
}
