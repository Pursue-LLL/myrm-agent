/**
 * Side Panel copy: every message key the panel and the popup toggle ask `chrome.i18n` for exists in both extension
 * locales, and no panel message is left without a user.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { APPROVAL_NOTIFY_KEY } from '../../../../../myrm-agent-extension/src/sidepanel/approval_notify.js';

const EXTENSION_DIR = resolve(__dirname, '../../../../../myrm-agent-extension');
const read = (relativePath: string) => readFileSync(resolve(EXTENSION_DIR, relativePath), 'utf8');

type Catalog = Record<string, { message: string; placeholders?: Record<string, unknown> }>;
const catalogs = {
  en: JSON.parse(read('_locales/en/messages.json')) as Catalog,
  zh_CN: JSON.parse(read('_locales/zh_CN/messages.json')) as Catalog,
};

const PANEL_SOURCES = [
  'src/sidepanel/sidepanel.js',
  'src/sidepanel/approval.js',
  'src/sidepanel/approval_overlay.js',
  'src/sidepanel/approval_notify.js',
  'src/sidepanel/chat_view.js',
  'src/sidepanel/page_context.js',
  'src/sidepanel/sidepanel.html',
  'src/popup.html',
];

/** Messages the panel owns, by the prefixes its keys carry. */
const PANEL_KEY = /"((?:approval|panel|notifyApproval)[A-Za-z]*)"/g;

/** Keys named in `msg("...")` / `translate("...")` calls and in `data-i18n*` attributes, plus every panel-prefixed literal. */
function referencedKeys(): string[] {
  const keys = new Set<string>();
  for (const file of PANEL_SOURCES) {
    const source = read(file);
    for (const match of source.matchAll(/(?:msg|translate)\(\s*"(\w+)"/g)) {
      keys.add(match[1]);
    }
    for (const match of source.matchAll(/data-i18n(?:-title|-placeholder)?="(\w+)"/g)) {
      keys.add(match[1]);
    }
    for (const match of source.matchAll(PANEL_KEY)) {
      keys.add(match[1]);
    }
  }
  keys.delete(APPROVAL_NOTIFY_KEY); // a storage setting, not a message
  return [...keys].sort();
}

describe('side panel locale keys', () => {
  it('finds the keys the panel uses, including those chosen at run time', () => {
    expect(referencedKeys()).toEqual(
      expect.arrayContaining([
        'approvalApprove',
        'approvalHandledElsewhere',
        'approvalHintTooLong',
        'approvalHintNoDetails',
        'approvalDeadlineDeny',
        'approvalDeadlineAllow',
        'approvalNotifyLabel',
        'notifyApprovalTitle',
        'panelUsingTool',
        'panelInputPaused',
        'panelStreamError',
      ]),
    );
  });

  it.each(Object.keys(catalogs) as (keyof typeof catalogs)[])(
    'has a message for every referenced key in %s',
    (locale) => {
      const missing = referencedKeys().filter((key) => !catalogs[locale][key]?.message);

      expect(missing).toEqual([]);
    },
  );

  it('keeps no panel message that nothing asks for', () => {
    const referenced = new Set(referencedKeys());
    const orphans = Object.keys(catalogs.en).filter(
      (key) => /^(?:approval|panel|notifyApproval)/.test(key) && !referenced.has(key),
    );

    expect(orphans).toEqual([]);
  });

  it('keeps the same keys and placeholders in both locales', () => {
    expect(Object.keys(catalogs.zh_CN).sort()).toEqual(Object.keys(catalogs.en).sort());
    for (const [key, entry] of Object.entries(catalogs.en)) {
      expect(Object.keys(catalogs.zh_CN[key].placeholders ?? {}), key).toEqual(Object.keys(entry.placeholders ?? {}));
    }
  });

  it('uses every declared placeholder in the message of both locales', () => {
    for (const locale of Object.keys(catalogs) as (keyof typeof catalogs)[]) {
      for (const [key, entry] of Object.entries(catalogs[locale])) {
        for (const name of Object.keys(entry.placeholders ?? {})) {
          expect(entry.message.toUpperCase(), `${locale}.${key}`).toContain(`$${name.toUpperCase()}$`);
        }
      }
    }
  });
});
