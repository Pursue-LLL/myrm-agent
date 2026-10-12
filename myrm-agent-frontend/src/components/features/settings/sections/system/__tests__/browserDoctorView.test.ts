import { describe, expect, it } from 'vitest';

import { buildDoctorView, statusLabelKey, type BrowserDoctorReport, type DoctorCheck } from '../browserDoctorView';

function report(checks: Record<string, DoctorCheck>, overallHealthy = true): BrowserDoctorReport {
  return { summary: 'raw english summary', overall_healthy: overallHealthy, checks, recommendations: [] };
}

function rowOf(name: string, check: DoctorCheck, overallHealthy = true) {
  const row = buildDoctorView(report({ [name]: check }, overallHealthy)).rows[0];
  if (!row) {
    throw new Error('expected one row');
  }
  return row;
}

describe('buildDoctorView', () => {
  it('treats ok checks as quiet rows without a hint', () => {
    const row = rowOf('patchright', { status: 'ok', message: 'patchright 1.63.0 installed' });
    expect(row.tone).toBe('ok');
    expect(row.hint).toBeNull();
  });

  it('keeps optional warnings out of the attention count and the unhealthy verdict', () => {
    const view = buildDoctorView(
      report({
        patchright: { status: 'ok', message: 'ok' },
        camoufox: { status: 'warning', message: 'camoufox not ready', details: { optional: true } },
        extension_relay: { status: 'warning', message: 'not connected', details: { optional: true } },
      }),
    );
    expect(view.needsAttention).toBe(0);
    expect(view.optionalCount).toBe(2);
    expect(view.hasFailure).toBe(false);
    expect(view.healthy).toBe(true);
    expect(view.rows.map((row) => row.hint?.key ?? null)).toEqual([null, 'optionalCamoufox', 'optionalExtension']);
  });

  it('does not treat a warning as optional unless the backend marks it with a literal true', () => {
    for (const marker of ['true', 1, 'yes', null]) {
      const row = rowOf('extension_relay', { status: 'warning', message: 'm', details: { optional: marker } });
      expect(row.tone, String(marker)).toBe('attention');
    }
    const unmarked = rowOf('extension_relay', { status: 'warning', message: 'access policy missing', details: null });
    expect(unmarked.tone).toBe('attention');
    expect(unmarked.hint?.key).toBe('attentionGeneric');
  });

  it('never lets a real warning pass as healthy even when the backend verdict is healthy', () => {
    const view = buildDoctorView(
      report({ orphan_processes: { status: 'warning', message: 'Found 2 orphans', details: { count: 2 } } }, true),
    );
    expect(view.needsAttention).toBe(1);
    expect(view.healthy).toBe(false);
    expect(view.rows[0]?.hint?.key).toBe('orphansFound');
  });

  it('reports failures for error and missing rows with the matching status label', () => {
    const view = buildDoctorView(
      report(
        {
          browser_launch: { status: 'error', message: 'Browser launch failed' },
          patchright: { status: 'missing', message: 'patchright not installed' },
        },
        false,
      ),
    );
    expect(view.hasFailure).toBe(true);
    expect(view.needsAttention).toBe(2);
    expect(view.healthy).toBe(false);
    expect(view.rows.map((row) => row.hint?.key)).toEqual(['errorGeneric', 'errorGeneric']);
    expect(statusLabelKey('error', 'error')).toBe('statusError');
    expect(statusLabelKey('error', 'missing')).toBe('statusMissing');
    expect(statusLabelKey('attention', 'warning')).toBe('statusWarning');
    expect(statusLabelKey('optional', 'warning')).toBe('statusOptional');
    expect(statusLabelKey('ok', 'ok')).toBe('statusOk');
  });

  it('describes memory and disk with a rounded available size and picks the low variant by tone', () => {
    expect(rowOf('memory', { status: 'ok', message: 'm', details: { available_gb: 12.449 } }).hint).toEqual({
      key: 'memoryOk',
      values: { size: 12.4 },
    });
    expect(rowOf('memory', { status: 'error', message: 'm', details: { available_gb: 0.46 } }).hint).toEqual({
      key: 'memoryLow',
      values: { size: 0.5 },
    });
    expect(rowOf('disk', { status: 'ok', message: 'm', details: { available_gb: 80 } }).hint).toEqual({
      key: 'diskOk',
      values: { size: 80 },
    });
    expect(rowOf('disk', { status: 'warning', message: 'm', details: { available_gb: 0.8 } }).hint).toEqual({
      key: 'diskLow',
      values: { size: 0.8 },
    });
  });

  it('falls back to the generic hint when the resource size is missing or not a finite number', () => {
    for (const available of [undefined, '12', Number.NaN, Number.POSITIVE_INFINITY, null]) {
      const row = rowOf('memory', { status: 'warning', message: 'm', details: { available_gb: available } });
      expect(row.hint?.key, String(available)).toBe('attentionGeneric');
    }
    expect(rowOf('disk', { status: 'ok', message: 'm' }).hint).toBeNull();
  });

  it('degrades unknown check names and statuses to a visible warning without crashing', () => {
    const unknownName = rowOf('constructor', { status: 'warning', message: 'm', details: { optional: true } });
    expect(unknownName.tone).toBe('optional');
    expect(unknownName.hint).toBeNull();

    const unknownStatus = rowOf('future_check', { status: 'degraded', message: 'm' });
    expect(unknownStatus.tone).toBe('attention');
    expect(statusLabelKey(unknownStatus.tone, unknownStatus.check.status)).toBe('statusWarning');
  });
});
