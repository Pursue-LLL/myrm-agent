/**
 * The Side Panel is its own document, so the web app's global reduced-motion block never reaches
 * it. Its stylesheet must carry the guard itself, or the connection dot, tool-progress icons and
 * typing dots keep animating for a reader who turned motion off at the OS level.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const PANEL_CSS = readFileSync(
  resolve(__dirname, '../../../../../myrm-agent-extension/src/sidepanel/sidepanel.css'),
  'utf8',
);

describe('side panel reduced-motion guard', () => {
  it('carries its own guard, because the host stylesheet cannot reach this document', () => {
    expect(PANEL_CSS).toContain('@media (prefers-reduced-motion: reduce)');
    expect(PANEL_CSS).toContain('animation-duration: 0.01ms !important');
    expect(PANEL_CSS).toContain('animation-iteration-count: 1 !important');
    expect(PANEL_CSS).toContain('transition-duration: 0.01ms !important');
  });

  // The panel's infinite animations are named (pulse, dotBounce). A guard that lists them would
  // miss the next one added, so it must be the universal selector.
  it('covers every element instead of naming the current animations', () => {
    expect(PANEL_CSS).toContain('*, *::before, *::after {');
  });
});
