import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

/**
 * The desktop composer's options region clips its content (`overflow-hidden`, so its height can animate), and a
 * clipping box cuts a child that is positioned outside it. A popup positioned inside it with `absolute bottom-full`
 * / `top-full` is cut to the region's height, so the viewer opens an empty-looking control. Controls that live in the
 * composer open Radix portals (Popover, DropdownMenu, HoverCard) instead. jsdom has no layout, so the rule is pinned
 * at the source.
 */
const FEATURES_DIR = resolve(__dirname, '../..');

const TOOLBAR_SOURCES = [
  'message-input-actions',
  'chat-window/composer-options',
  'chat-window/thinking-permission',
  'chat-window/agent-config-panel/ExpertSummonPopover.tsx',
];

const INLINE_POPUP_PATTERN =
  /\babsolute\b[^'"`\n]*\b(?:bottom|top)-full\b|\b(?:bottom|top)-full\b[^'"`\n]*\babsolute\b/;

function collectSources(entry: string): string[] {
  if (!statSync(entry).isDirectory()) {
    return entry.endsWith('.tsx') ? [entry] : [];
  }
  return readdirSync(entry).flatMap((name) => (name === '__tests__' ? [] : collectSources(join(entry, name))));
}

describe('composer toolbar popups', () => {
  const sources = TOOLBAR_SOURCES.flatMap((entry) => collectSources(join(FEATURES_DIR, entry)));

  it('scans the toolbar controls it is meant to guard', () => {
    expect(sources.length).toBeGreaterThan(15);
  });

  it('never positions a popup inline with absolute bottom-full / top-full', () => {
    const offenders = sources
      .filter((file) =>
        readFileSync(file, 'utf8')
          .split('\n')
          .some((line) => INLINE_POPUP_PATTERN.test(line)),
      )
      .map((file) => relative(FEATURES_DIR, file));

    expect(
      offenders,
      `${offenders.join(', ')} position a popup inside the composer's clipping options region. ` +
        'Open it through @/components/primitives/popover or dropdown-menu, which render in a portal.',
    ).toEqual([]);
  });
});
