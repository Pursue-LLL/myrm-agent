import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { ApiError } from '@/lib/api';
import { locales } from '@/i18n/config';
import type { ImaItemCounts, ImaStatus } from '@/services/wiki/ima';
import {
  canImaSyncNow,
  deriveImaSyncMode,
  deriveImaView,
  formatImaChars,
  formatImaNames,
  hasImaUnreadableNotes,
  imaAttentionCount,
  imaAutoCompileKey,
  IMA_DEDUP_REVIEW_ERROR_KEY,
  imaErrorKey,
  imaKindKey,
  imaNoteKeys,
  imaProgress,
  imaReasonKey,
  imaSkippedCount,
  imaUnreadableLibraries,
  isImaBackfilling,
  shouldPollIma,
} from '../imaCopy';

const NO_COUNTS: ImaItemCounts = {
  total: 0,
  synced: 0,
  pending: 0,
  failed: 0,
  unsupported: 0,
  too_large: 0,
  blocked: 0,
  dismissed: 0,
  remote_deleted: 0,
  duplicate: 0,
  partial: 0,
};

function makeStatus(overrides: Partial<ImaStatus> = {}): ImaStatus {
  return {
    connected: true,
    account_hint: 'abcd…wxyz',
    needs_reauth: false,
    knowledge_bases: [],
    include_notes: true,
    job: { state: 'active', next_run_at: null },
    phase: 'idle',
    backfill_complete: false,
    last_run_at: null,
    last_error_kind: '',
    unreadable: [],
    auto_compile: true,
    counts: NO_COUNTS,
    total_chars: 0,
    ...overrides,
  };
}

describe('deriveImaView', () => {
  it('walks connect, reconnect, choose and sync from the server status alone', () => {
    expect(deriveImaView(makeStatus({ connected: false }), false)).toBe('connect');
    expect(deriveImaView(makeStatus({ needs_reauth: true }), false)).toBe('reconnect');
    expect(deriveImaView(makeStatus({ job: { state: 'none', next_run_at: null } }), false)).toBe('choose');
    expect(deriveImaView(makeStatus(), false)).toBe('sync');
    expect(deriveImaView(makeStatus({ job: { state: 'paused', next_run_at: null } }), false)).toBe('sync');
  });

  it('lets the user reopen the choice while a sync exists, but never before connecting', () => {
    expect(deriveImaView(makeStatus(), true)).toBe('choose');
    expect(deriveImaView(makeStatus({ connected: false }), true)).toBe('connect');
    expect(deriveImaView(makeStatus({ needs_reauth: true }), true)).toBe('reconnect');
  });
});

describe('deriveImaSyncMode', () => {
  it('reports what the running sync is doing', () => {
    expect(deriveImaSyncMode(makeStatus({ phase: 'inventory' }))).toBe('reading');
    expect(deriveImaSyncMode(makeStatus({ phase: 'fetch' }))).toBe('importing');
    expect(deriveImaSyncMode(makeStatus({ phase: 'idle', backfill_complete: false }))).toBe('waiting');
    expect(deriveImaSyncMode(makeStatus({ phase: 'idle', backfill_complete: true }))).toBe('upToDate');
  });

  it('puts a paused job first, whatever phase it was left in', () => {
    expect(deriveImaSyncMode(makeStatus({ phase: 'fetch', job: { state: 'paused', next_run_at: null } }))).toBe(
      'paused',
    );
  });
});

describe('sync now and auto-compile wording', () => {
  it('offers a check only between slices or once up to date, never while one is reading or importing', () => {
    expect(canImaSyncNow(makeStatus({ phase: 'idle', backfill_complete: true }))).toBe(true);
    expect(canImaSyncNow(makeStatus({ phase: 'idle', backfill_complete: false }))).toBe(true);
    expect(canImaSyncNow(makeStatus({ phase: 'inventory' }))).toBe(false);
    expect(canImaSyncNow(makeStatus({ phase: 'fetch' }))).toBe(false);
    expect(canImaSyncNow(makeStatus({ phase: 'idle', job: { state: 'paused', next_run_at: null } }))).toBe(false);
  });

  it('only promises automatic compiling once the first import is complete and the shared switch is on', () => {
    expect(imaAutoCompileKey(makeStatus({ auto_compile: false, backfill_complete: true }))).toBe('compile.autoOff');
    expect(imaAutoCompileKey(makeStatus({ auto_compile: false, backfill_complete: false }))).toBe('compile.autoOff');
    expect(imaAutoCompileKey(makeStatus({ auto_compile: true, backfill_complete: false }))).toBe('compile.autoPending');
    expect(imaAutoCompileKey(makeStatus({ auto_compile: true, backfill_complete: true }))).toBe('compile.autoOn');
  });
});

describe('progress and polling', () => {
  it('counts everything that is no longer waiting as processed', () => {
    expect(imaProgress(NO_COUNTS)).toEqual({ done: 0, total: 0, percent: 0 });
    expect(imaProgress({ ...NO_COUNTS, total: 10, pending: 4 })).toEqual({ done: 6, total: 10, percent: 60 });
  });

  it('shows the bar only while the first import is still filling the wiki', () => {
    expect(isImaBackfilling(makeStatus())).toBe(true);
    expect(isImaBackfilling(makeStatus({ backfill_complete: true }))).toBe(false);
    expect(isImaBackfilling(makeStatus({ job: { state: 'paused', next_run_at: null } }))).toBe(false);
  });

  it('polls only while something can still change by itself', () => {
    expect(shouldPollIma(null)).toBe(false);
    expect(shouldPollIma(makeStatus({ connected: false }))).toBe(false);
    expect(shouldPollIma(makeStatus({ phase: 'fetch' }))).toBe(true);
    expect(shouldPollIma(makeStatus({ phase: 'idle', backfill_complete: false }))).toBe(true);
    expect(shouldPollIma(makeStatus({ phase: 'idle', backfill_complete: true }))).toBe(false);
    expect(shouldPollIma(makeStatus({ phase: 'fetch', job: { state: 'paused', next_run_at: null } }))).toBe(false);
  });

  it('adds up skipped and attention items the way the report tabs do', () => {
    const counts = { ...NO_COUNTS, failed: 2, unsupported: 3, too_large: 1, blocked: 1, duplicate: 9, dismissed: 4 };
    expect(imaSkippedCount(counts)).toBe(5);
    expect(imaAttentionCount(counts)).toBe(7);
  });
});

describe('unreadable parts', () => {
  it('tells the libraries apart from the notes', () => {
    const status = makeStatus({
      unreadable: [
        { kind: 'library', name: 'Research' },
        { kind: 'notes', name: '' },
        { kind: 'library', name: 'Recipes' },
      ],
    });
    expect(imaUnreadableLibraries(status)).toEqual(['Research', 'Recipes']);
    expect(hasImaUnreadableNotes(status)).toBe(true);
    expect(imaUnreadableLibraries(makeStatus())).toEqual([]);
    expect(hasImaUnreadableNotes(makeStatus())).toBe(false);
  });

  it('joins library names the way the reader language does', () => {
    expect(formatImaNames(['Research'], 'en')).toBe('Research');
    expect(formatImaNames(['Research', 'Recipes'], 'en')).toBe('Research and Recipes');
    expect(formatImaNames(['Research', 'Recipes'], 'zh')).toBe('Research和Recipes');
  });
});

describe('code to copy mapping', () => {
  it('maps the server error code and falls back to a generic line for anything else', () => {
    expect(imaErrorKey(new ApiError('x', 400, [], undefined, 'ima_auth_failed'))).toBe('errors.ima_auth_failed');
    expect(imaErrorKey(new ApiError('x', 409, [], undefined, 'dedup_review_required'))).toBe(
      'errors.dedup_review_required',
    );
    // The card compares against this key to decide when to open Duplicate Review, so it must track the mapping above.
    expect(IMA_DEDUP_REVIEW_ERROR_KEY).toBe('errors.dedup_review_required');
    expect(imaErrorKey(new ApiError('x', 500, [], undefined, 'something_new'))).toBe('errors.generic');
    expect(imaErrorKey(new ApiError('x', 500))).toBe('errors.generic');
    expect(imaErrorKey(new TypeError('Failed to fetch'))).toBe('errors.generic');
  });

  it('never lets a raw reason, note or media code reach the screen', () => {
    expect(imaReasonKey('too_large')).toBe('reasons.too_large');
    expect(imaReasonKey('raw_gate_internal_code')).toBe('reasons.generic');
    expect(imaReasonKey('')).toBe('reasons.generic');
    expect(imaNoteKeys(['redacted', 'unknown_note', 'images_remote'])).toEqual([
      'notes.redacted',
      'notes.images_remote',
    ]);
    expect(imaKindKey('wechat')).toBe('kinds.wechat');
    expect(imaKindKey('mystery')).toBe('kinds.other');
  });

  it('formats character totals in the reader locale', () => {
    expect(formatImaChars(1234, 'en')).toBe('1.2K');
    expect(formatImaChars(1234, 'de')).not.toBe('');
  });
});

// Every code the server can send (see the ima package's errors / ledger reasons / fidelity notes / media labels).
const SERVER_ERROR_CODES = [
  'ima_auth_failed',
  'ima_rate_limited',
  'ima_unreachable',
  'ima_not_connected',
  'ima_no_selection',
  'ima_sync_not_started',
  'ima_credentials_missing',
  'dedup_review_required',
  'sync_unavailable',
];
const SERVER_REASONS = [
  'unsupported_type',
  'no_download_url',
  'no_text',
  'too_large',
  'security',
  'notes_permission',
  'permission',
  'not_owner',
  'timeout',
  'transient',
  'permanent',
  'page_unavailable',
  'auth',
  'rate_limit',
];
// Notices the sync panel words directly instead of through a code mapping.
const PANEL_NOTICES = ['notices.rateLimited', 'notices.unreachable', 'notices.internal', 'notices.unreadableNotes'];
const SERVER_NOTES = ['images_remote', 'body_truncated', 'layout_flattened', 'redacted'];
const SERVER_KINDS = [
  'pdf',
  'web',
  'word',
  'ppt',
  'excel',
  'wechat',
  'markdown',
  'image',
  'note',
  'ai_session',
  'text',
  'xmind',
  'audio',
  'video',
  'html',
  'epub',
];

type MessageTree = { [key: string]: string | MessageTree };

function imaMessages(locale: string): MessageTree {
  const raw = JSON.parse(readFileSync(path.join(process.cwd(), 'locales', `${locale}.json`), 'utf-8')) as MessageTree;
  return ((raw.settings as MessageTree).wiki as MessageTree).ima as MessageTree;
}

function leaf(tree: MessageTree, key: string): string | undefined {
  let node: string | MessageTree | undefined = tree;
  for (const part of key.split('.')) {
    node = typeof node === 'object' ? node[part] : undefined;
  }
  return typeof node === 'string' ? node : undefined;
}

function leafPaths(tree: MessageTree, prefix = ''): string[] {
  return Object.entries(tree).flatMap(([key, value]) =>
    typeof value === 'string' ? [`${prefix}${key}`] : leafPaths(value, `${prefix}${key}.`),
  );
}

describe('settings.wiki.ima locale contract', () => {
  const reference = leafPaths(imaMessages('zh')).sort();

  it.each(locales)('%s has exactly the same keys as zh and a line for every server code', (locale) => {
    const messages = imaMessages(locale);
    expect(leafPaths(messages).sort()).toEqual(reference);

    const keys = [
      ...SERVER_ERROR_CODES.map((code) => imaErrorKey(new ApiError('x', 400, [], undefined, code))),
      ...SERVER_REASONS.map(imaReasonKey),
      ...SERVER_NOTES.flatMap((note) => imaNoteKeys([note])),
      ...SERVER_KINDS.map(imaKindKey),
      ...PANEL_NOTICES,
      'notices.unreadableLibraries',
      'errors.generic',
      'reasons.generic',
      'kinds.other',
    ];
    for (const key of keys) {
      expect(leaf(messages, key), `${locale}: ${key}`).toBeTruthy();
    }
    expect(leaf(messages, 'notices.unreadableLibraries'), `${locale}: library names slot`).toContain('{names}');
    expect(SERVER_REASONS.map(imaReasonKey)).not.toContain('reasons.generic');
    expect(SERVER_NOTES.flatMap((note) => imaNoteKeys([note]))).toHaveLength(SERVER_NOTES.length);
    expect(SERVER_KINDS.map(imaKindKey)).not.toContain('kinds.other');
  });

  it.each(['en', 'de'])('%s copy contains no CJK text', (locale) => {
    const text = JSON.stringify(imaMessages(locale));
    expect(text).not.toMatch(/[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]/);
  });
});
