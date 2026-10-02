import { Children, Fragment, cloneElement, createElement, isValidElement, type ReactNode } from 'react';

const DUAL_TEXT_SEPARATOR = ' / ';

const CJK_PATTERN = /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Hangul}]/u;

const hasCjk = (value: string): boolean => CJK_PATTERN.test(value);

/**
 * Pick the locale-appropriate side from a dual-language string.
 *
 * The project currently uses strings in the form `English / 中文`.
 * This helper keeps the current locale's side while preserving surrounding
 * whitespace and leaving non-dual strings untouched.
 */
export function selectLocalizedText(value: string, locale: string): string {
  const separatorIndex = value.indexOf(DUAL_TEXT_SEPARATOR);
  if (separatorIndex === -1) {
    return value;
  }

  const leadingWhitespace = value.match(/^\s*/u)?.[0] ?? '';
  const trailingWhitespace = value.match(/\s*$/u)?.[0] ?? '';
  const core = value.trim();
  const coreSeparatorIndex = core.indexOf(DUAL_TEXT_SEPARATOR);

  if (coreSeparatorIndex === -1) {
    return value;
  }

  const left = core.slice(0, coreSeparatorIndex).trim();
  const right = core.slice(coreSeparatorIndex + DUAL_TEXT_SEPARATOR.length).trim();

  if (!left || !right) {
    return value;
  }

  const leftHasCjk = hasCjk(left);
  const rightHasCjk = hasCjk(right);

  if (!leftHasCjk && !rightHasCjk) {
    return value;
  }

  const selected = locale.startsWith('zh') ? (rightHasCjk ? right : left) : leftHasCjk && !rightHasCjk ? right : left;

  return `${leadingWhitespace}${selected}${trailingWhitespace}`;
}

function localizeChildren(children: ReactNode, locale: string): ReactNode {
  if (Array.isArray(children)) {
    const normalizedChildren = Children.toArray(children);
    let hasChanges = false;
    const localizedChildren = normalizedChildren.map((child) => {
      const localizedChild = localizeReactNode(child, locale);
      if (localizedChild !== child) {
        hasChanges = true;
      }
      return localizedChild;
    });

    if (!hasChanges) {
      return children;
    }

    return localizedChildren.length === 1 ? localizedChildren[0] : createElement(Fragment, null, ...localizedChildren);
  }

  return localizeReactNode(children, locale);
}

/**
 * Recursively localize React text nodes and string props.
 *
 * This lets us keep the existing bilingual source strings while rendering only
 * the active locale on screen.
 */
export function localizeReactNode(node: ReactNode, locale: string): ReactNode {
  if (node == null || typeof node === 'boolean' || typeof node === 'number') {
    return node;
  }

  if (typeof node === 'string') {
    return selectLocalizedText(node, locale);
  }

  if (Array.isArray(node)) {
    const localizedChildren = Children.toArray(node).map((child) => localizeReactNode(child, locale));
    return localizedChildren.length === 1 ? localizedChildren[0] : createElement(Fragment, null, ...localizedChildren);
  }

  if (!isValidElement<Record<string, unknown> & { children?: ReactNode }>(node)) {
    return node;
  }

  const nextProps: Record<string, unknown> = {};
  let hasPropChanges = false;

  for (const [key, value] of Object.entries(node.props)) {
    if (key === 'children' || key === 'dangerouslySetInnerHTML') {
      continue;
    }

    if (typeof value === 'string') {
      const localized = selectLocalizedText(value, locale);
      if (localized !== value) {
        nextProps[key] = localized;
        hasPropChanges = true;
      }
    }
  }

  const originalChildren = node.props.children as ReactNode;
  const localizedChildren = localizeChildren(originalChildren, locale);
  const childrenChanged = localizedChildren !== originalChildren;

  if (!hasPropChanges && !childrenChanged) {
    return node;
  }

  return cloneElement(node, nextProps, localizedChildren);
}
