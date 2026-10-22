/**
 * [INPUT]
 * components/features/chat-window/subagent/SubagentStream::STATUS_ICON_MAP (POS: Record keyed by every SubagentStatus)
 * locales/{zh,en,ja,ko,de,zh-TW}.json — subagentDashboard.statusLabel strings and subagentDashboard.detailBlockedNote.
 * [OUTPUT]
 * Vitest: every subagent status the backend can publish has a label in every locale, and a blocked node has its review note.
 * [POS]
 * Regression guard for raw i18n keys (e.g. subagentDashboard.statusLabel.blocked) in the subagent tree, drawer and inline strip.
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { STATUS_ICON_MAP } from '../SubagentStream';

const LOCALES_ROOT = resolve(process.cwd(), 'locales');
const LANGUAGES = ['zh', 'en', 'ja', 'ko', 'de', 'zh-TW'] as const;

type SubagentDashboardMessages = { statusLabel?: Record<string, unknown> } & Record<string, unknown>;

function loadSubagentDashboard(lang: (typeof LANGUAGES)[number]): SubagentDashboardMessages {
  const raw = readFileSync(resolve(LOCALES_ROOT, `${lang}.json`), 'utf-8');
  const data = JSON.parse(raw) as { subagentDashboard?: SubagentDashboardMessages };
  return data.subagentDashboard ?? {};
}

function loadStatusLabels(lang: (typeof LANGUAGES)[number]): Record<string, unknown> {
  return loadSubagentDashboard(lang).statusLabel ?? {};
}

describe('subagent status labels', () => {
  for (const lang of LANGUAGES) {
    it(`${lang}.json labels every subagent status`, () => {
      const labels = loadStatusLabels(lang);

      for (const status of Object.keys(STATUS_ICON_MAP)) {
        expect(typeof labels[status], `${lang}: statusLabel.${status}`).toBe('string');
        expect((labels[status] as string).length).toBeGreaterThan(0);
      }
    });

    it(`${lang}.json explains a blocked node`, () => {
      const note = loadSubagentDashboard(lang).detailBlockedNote;

      expect(typeof note, `${lang}: detailBlockedNote`).toBe('string');
      expect((note as string).length).toBeGreaterThan(0);
    });
  }
});
