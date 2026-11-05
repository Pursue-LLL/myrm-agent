import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

/**
 * Every block on the empty chat competes for first-screen height. This contract keeps new cards from
 * landing there unreviewed: a component imported by EmptyChat.tsx must be listed here together with the
 * reason it earns first-screen space.
 */
const FIRST_SCREEN_COMPONENTS: Record<string, string> = {
  MessageInput: 'the composer, the primary action and the workspace row it owns',
  SamplePrompts: 'starter prompts, always shown',
  AgentConfigPanel: 'collapsed by default; expanded only from the agent indicator',
  CompanionWidget: 'feature-gated, renders beside the composer',
  NoProviderBanner: 'renders only while no model provider is configured',
  WorkUnitBalanceBar: 'renders only in sandbox deployments with entitlements',
  IncognitoNotice: 'renders only while incognito is on',
  MigrationDiscoveryBanner: 'renders only when external assistant data is detected (local mode)',
  UpdateNudgeBanner: 'renders only when an update is pending',
  ResourcePressureBanner: 'renders only under resource pressure',
  ModelOrchestrationPlaybookDialog: 'closed dialog, adds no first-screen height',
};

const IMPORT_PATTERN = /import\s+(?:(\w+)\s*,?\s*)?(?:\{([^}]*)\}\s*)?from\s*'([^']+)'/g;

function importedComponents(source: string): string[] {
  const components: string[] = [];
  for (const [, defaultImport, namedImports = '', specifier] of source.matchAll(IMPORT_PATTERN)) {
    const isLocalModule = specifier.startsWith('.') || specifier.startsWith('@/components');
    if (!isLocalModule) {
      continue;
    }
    const names = [
      defaultImport,
      ...namedImports.split(',').map((name) =>
        name
          .trim()
          .split(/\s+as\s+/)
          .pop(),
      ),
    ];
    components.push(...names.filter((name): name is string => !!name && /^[A-Z]/.test(name)));
  }
  return components;
}

describe('empty chat first-screen contract', () => {
  const source = readFileSync(resolve(__dirname, '../EmptyChat.tsx'), 'utf8');
  const components = importedComponents(source);

  it('imports only components that are allowed on the first screen', () => {
    const unlisted = components.filter((name) => !(name in FIRST_SCREEN_COMPONENTS));

    expect(
      unlisted,
      `EmptyChat.tsx imports ${unlisted.join(', ')} without a first-screen allowlist entry. ` +
        'Prefer a conditional or secondary surface; if it truly belongs on the first screen, ' +
        'add it to FIRST_SCREEN_COMPONENTS with the reason.',
    ).toEqual([]);
  });

  it('keeps the allowlist free of components that are no longer imported', () => {
    const stale = Object.keys(FIRST_SCREEN_COMPONENTS).filter((name) => !components.includes(name));

    expect(stale, `Remove stale allowlist entries: ${stale.join(', ')}`).toEqual([]);
  });

  it('leaves viewport filling to AppLayout, so the wrapper padding cannot turn a clean screen into a scrollbar', () => {
    expect(source).not.toMatch(/min-h-(?:screen|dvh|svh|lvh|\[)/);
  });
});

/**
 * The desktop composer toolbar scrolls sideways with its scrollbar hidden, so a clipped edge would end mid-control
 * with nothing hinting at the rest. jsdom has no layout, so the wiring is pinned at the source; the fade rule itself
 * is pinned by app/__tests__/scroll-fade-css.test.ts.
 */
describe('empty chat composer toolbar scroll hint', () => {
  it('wires the desktop toolbar scroller to the edge fade', () => {
    const composer = readFileSync(resolve(__dirname, '../MessageInput.tsx'), 'utf8');

    expect(composer).toContain('ref={toolbarFadeRef}');
    expect(composer).toMatch(/className="scroll-fade-x hidden sm:flex[^"]*overflow-x-auto/);
  });
});
