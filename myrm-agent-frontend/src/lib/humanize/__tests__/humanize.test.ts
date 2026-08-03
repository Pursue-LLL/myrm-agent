import { describe, expect, it } from 'vitest';

import type { ProgressItem } from '@/store/chat/types/progress';
import { classifyApprovalSurface } from '../classify';
import { humanizeApprovalTitle } from '../humanizeApproval';
import { humanizeProgressStep } from '../humanizeProgressStep';
import { humanizeToolLine } from '../humanizeToolLine';
import { resolveScopeNote } from '../scopeNote';
import type { TranslateFn } from '../types';

const enHumanize: Record<string, string> = {
  'fallback.file': 'a file',
  'fallback.used_tool': 'Used {tool}',
  'progress.file_write': 'Wrote {filename}',
  'approval.file_write': 'Write {filename}',
  'approval.save_skill': 'Add skill: {name}',
  'approval.browser_url': 'Open webpage — {url}',
  'ask.file_write_ask': 'Wanted to write {filename}',
  'progress.web_search': 'Search the web — "{query}"',
  'scope.local': 'Changes stay on this device',
  'scope.external': 'Sends data to {destination}',
  'scope.external_unknown': 'an external service',
};

const t: TranslateFn = (key, values) => {
  let out = enHumanize[key] ?? key;
  if (values) {
    for (const [k, v] of Object.entries(values)) {
      out = out.replace(`{${k}}`, String(v));
    }
  }
  return out;
};

describe('humanizeToolLine', () => {
  it('humanizes file_write with basename', () => {
    expect(
      humanizeToolLine('file_write_tool', { filename: 'report.md' }, t, 'progress'),
    ).toBe('Wrote report.md');
  });

  it('humanizes browser_navigate with host', () => {
    expect(
      humanizeToolLine(
        'browser_navigate_tool',
        { url: 'https://customer.example.com/dashboard' },
        t,
        'approval',
      ),
    ).toBe('Open webpage — customer.example.com');
  });

  it('humanizes approval mode', () => {
    expect(
      humanizeApprovalTitle('file_write_tool', { file_path: '/workspace/src/app.ts' }, t),
    ).toBe('Write app.ts');
  });

  it('humanizes skill_manage_tool save action', () => {
    expect(
      humanizeApprovalTitle(
        'skill_manage_tool',
        { action: 'save', name: 'incident-summary', content: '# body' },
        t,
      ),
    ).toBe('Add skill: incident-summary');
  });
});

describe('humanizeProgressStep', () => {
  it('extracts filename from progress items', () => {
    const step = {
      tool_name: 'file_write_tool',
      items: [{ file_path: '/tmp/output.json' }],
    } as ProgressItem;
    expect(humanizeProgressStep(step, t)).toBe('Wrote output.json');
  });

  it('uses ask tense for cancelled steps', () => {
    const step = {
      tool_name: 'file_write_tool',
      status: 'cancelled',
      items: [{ file_path: '/tmp/output.json' }],
    } as ProgressItem;
    expect(humanizeProgressStep(step, t)).toBe('Wanted to write output.json');
  });
});

describe('classifyApprovalSurface', () => {
  it('marks local file tools as compact', () => {
    expect(classifyApprovalSurface('file_write_tool')).toBe('compact');
    expect(classifyApprovalSurface('bash_code_execute_tool')).toBe('full');
  });
});

describe('resolveScopeNote', () => {
  it('returns local scope by default', () => {
    expect(resolveScopeNote('file_write_tool', {}, t).text).toBe('Changes stay on this device');
  });

  it('flags external targets', () => {
    const note = resolveScopeNote('send_message_tool', { target: 'slack:general' }, t);
    expect(note.external).toBe(true);
    expect(note.text).toContain('Slack');
  });

  it('does not treat browser target colons as external channel scope', () => {
    const note = resolveScopeNote('browser_manage_tool', { target: 'about:blank' }, t);
    expect(note.external).toBe(false);
    expect(note.text).toBe('Changes stay on this device');
  });

  it('does not treat non-channel tools with colon-like targets as external', () => {
    const note = resolveScopeNote('browser_manage_tool', {
      target: 'document.querySelector(".pay")',
    }, t);
    expect(note.external).toBe(false);
  });
});
