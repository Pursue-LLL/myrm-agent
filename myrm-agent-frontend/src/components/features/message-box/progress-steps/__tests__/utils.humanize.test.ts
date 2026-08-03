import { describe, expect, it } from 'vitest';

import type { ProgressItem } from '@/store/chat/types/progress';
import { getStepTitle } from '../utils';

const progressT = (key: string) => {
  if (key === 'file_write_tool') return 'Writing file';
  return key;
};

const humanizeT = (key: string, values?: Record<string, string | number>) => {
  const dict: Record<string, string> = {
    'progress.file_write': 'Wrote {filename}',
  };
  let out = dict[key] ?? key;
  if (values) {
    for (const [k, v] of Object.entries(values)) {
      out = out.replace(`{${k}}`, String(v));
    }
  }
  return out;
};

describe('getStepTitle humanize integration', () => {
  it('prefers humanize one-liner over raw tool name', () => {
    const step = {
      step_key: 'file_write_tool',
      tool_name: 'file_write_tool',
      items: [{ file_path: '/workspace/report.md' }],
    } as ProgressItem;
    expect(getStepTitle(step, progressT, true, humanizeT)).toBe('Wrote report.md');
  });
});
