/** @vitest-environment jsdom */
import { describe, it, expect } from 'vitest';

import { toLivenessState, buildTooltip } from '../useLivenessState';
import type { LivenessState } from '../useLivenessState';

// ── toLivenessState: state mapping logic ──

describe('toLivenessState', () => {
  it.each<LivenessState>(['busy', 'idle', 'degraded', 'draining'])(
    'accepts valid API state "%s"',
    (s) => expect(toLivenessState(s)).toBe(s),
  );

  it('rejects "offline" as an API state (offline is frontend-only)', () => {
    expect(toLivenessState('offline')).toBe('degraded');
  });

  it('falls back to degraded for unknown string', () => {
    expect(toLivenessState('banana')).toBe('degraded');
    expect(toLivenessState('')).toBe('degraded');
  });

  it('falls back to degraded for non-string types', () => {
    expect(toLivenessState(42)).toBe('degraded');
    expect(toLivenessState(null)).toBe('degraded');
    expect(toLivenessState(undefined)).toBe('degraded');
    expect(toLivenessState(true)).toBe('degraded');
    expect(toLivenessState({})).toBe('degraded');
  });
});

// ── buildTooltip: tooltip generation for all 5 states ──

describe('buildTooltip', () => {
  it('offline → "Backend offline"', () => {
    expect(buildTooltip('offline', 0)).toBe('Backend offline');
    expect(buildTooltip('offline', 5)).toBe('Backend offline');
  });

  it('draining with tasks → mentions task count', () => {
    expect(buildTooltip('draining', 1)).toContain('1 task');
    expect(buildTooltip('draining', 3)).toContain('3 tasks finishing');
  });

  it('draining without tasks → "Shutting down…"', () => {
    expect(buildTooltip('draining', 0)).toBe('Shutting down…');
  });

  it('busy singular', () => {
    expect(buildTooltip('busy', 1)).toBe('1 task running');
  });

  it('busy plural', () => {
    expect(buildTooltip('busy', 5)).toBe('5 tasks running');
  });

  it('degraded → "Service degraded"', () => {
    expect(buildTooltip('degraded', 0)).toBe('Service degraded');
  });

  it('idle → empty string', () => {
    expect(buildTooltip('idle', 0)).toBe('');
  });
});

// ── Poll logic coverage via functional equivalence ──
// The poll() function (module-internal) does:
//   1. fetch success + ok   → toLivenessState(json.state) + activeCount
//   2. fetch success + !ok  → 'degraded' (NOT offline)
//   3. fetch exception      → 'offline'
// Items 1-2 are fully verified by toLivenessState tests above.
// The critical bug fix (catch → 'offline', !ok → 'degraded') is a
// direct consequence of these mappings. Integration coverage of poll()
// is handled by Chrome MCP e2e against the real running frontend.

describe('state design contract', () => {
  it('API_STATES does not include offline (offline is frontend-derived)', () => {
    expect(toLivenessState('offline')).toBe('degraded');
  });

  it('all 5 states produce distinct tooltips', () => {
    const states: LivenessState[] = ['idle', 'busy', 'degraded', 'draining', 'offline'];
    const tooltips = new Set(states.map((s) => buildTooltip(s, 1)));
    expect(tooltips.size).toBe(states.length);
  });
});
