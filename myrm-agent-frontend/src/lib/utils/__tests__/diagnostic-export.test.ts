import { describe, expect, it } from 'vitest';

import type { DoctorResponse } from '@/services/runtime-health';
import { formatDoctorReportAsMarkdown } from '../diagnostic-export';

const doctor: DoctorResponse = {
  harness: [
    {
      component_name: 'SystemExhaustion',
      status: 'warn',
      message: 'Swap/Pagefile usage is high.',
      detail: 'Swap/Pagefile: 93.6%',
      measured: 'Swap 93.6%',
      expected: 'Swap <70%',
      cause: 'Idle pages were moved to swap earlier.',
      fix_suggestion: 'Inspect orphan worker processes.',
    },
    { component_name: 'Database', status: 'pass', message: 'Database is healthy.' },
  ],
  server: [],
  repair_actions: [],
};

describe('formatDoctorReportAsMarkdown', () => {
  it('carries the measured, expected and cause fields so a pasted report is enough for support', () => {
    const markdown = formatDoctorReportAsMarkdown(doctor);

    expect(markdown).toContain('  - `Swap/Pagefile: 93.6%`');
    expect(markdown).toContain('  - Measured: Swap 93.6%');
    expect(markdown).toContain('  - Expected: Swap <70%');
    expect(markdown).toContain('  - Cause: Idle pages were moved to swap earlier.');
    expect(markdown).toContain('  - Fix: Inspect orphan worker processes.');
  });

  it('prints no empty field lines for a report without them', () => {
    const markdown = formatDoctorReportAsMarkdown({ ...doctor, harness: [doctor.harness[1]] });

    expect(markdown).toContain('**Database** — Database is healthy.');
    expect(markdown).not.toMatch(/Measured:|Expected:|Cause:|Fix:/);
  });
});
