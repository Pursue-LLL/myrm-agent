/** @vitest-environment jsdom */
import { act, cleanup } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type {
  ImportResultResponse,
  ObsidianImportResultResponse,
  WikiImportConflictOptions,
} from '@/services/wikiService';
import { deferred } from '@/test-utils/deferred';
import { settle } from '@/test-utils/fakeClock';
import { resetKit, service, toast, toastTexts, world } from './wikiSectionTestKit';
import {
  fileOf,
  importResultOf,
  obsidianResultOf,
  urlImportResultOf,
  videoImportResultOf,
} from './wikiSectionFixtures';
import { renderImport, type ImportBench } from './wikiImportBench';

const CONFLICTS = ['notes/a.md', 'notes/b.md'];
const FOLDER_REPLACED_SUMMARY = 'import.folderResultWithSkips|{"imported":2,"skipped":3}';
const OBSIDIAN_SUMMARY = 'import.obsidianResult|{"processed":5,"tags":2,"images":1,"skipped":1}';
const SUPERSEDE: WikiImportConflictOptions = { onConflict: 'supersede', supersedeReason: 'newer notes' };
const ARCHIVE = fileOf('notes.zip');
let consoleError: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  resetKit();
  consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

/** 每种导入首次命中冲突后，用户选“覆盖”时应原样重放的那次调用。 */
const RETRIES = [
  {
    label: 'a desktop folder',
    tauri: true,
    busy: 'isImporting',
    method: 'importFolder',
    conflicted: importResultOf({ conflict_paths: CONFLICTS }),
    replaced: importResultOf({ files_scanned: 5, files_enqueued: 2, conflict_paths: CONFLICTS }),
    summary: FOLDER_REPLACED_SUMMARY,
    begin: (bench: ImportBench) => act(() => bench.current().handleImportFolder()),
    replay: ['/picked/folder', ['.md', '.txt', '.org'], true, 'a1', SUPERSEDE],
  },
  {
    label: 'a ZIP archive',
    tauri: false,
    busy: 'isImporting',
    method: 'importZip',
    conflicted: importResultOf({ conflict_paths: CONFLICTS }),
    replaced: importResultOf({ files_scanned: 5, files_enqueued: 2, conflict_paths: CONFLICTS }),
    summary: FOLDER_REPLACED_SUMMARY,
    begin: (bench: ImportBench) => bench.choose('zip', [ARCHIVE]),
    replay: [ARCHIVE, '.md,.txt,.org', true, 'a1', SUPERSEDE],
  },
  {
    label: 'an Obsidian vault folder',
    tauri: true,
    busy: 'isImportingObsidian',
    method: 'importObsidianFolder',
    conflicted: obsidianResultOf({ conflict_paths: CONFLICTS }),
    replaced: obsidianResultOf({ conflict_paths: CONFLICTS }),
    summary: OBSIDIAN_SUMMARY,
    begin: (bench: ImportBench) => act(() => bench.current().handleImportObsidianFolder()),
    replay: ['/picked/folder', true, 'a1', SUPERSEDE],
  },
  {
    label: 'an Obsidian ZIP archive',
    tauri: false,
    busy: 'isImportingObsidian',
    method: 'importObsidianZip',
    conflicted: obsidianResultOf({ conflict_paths: CONFLICTS }),
    replaced: obsidianResultOf({ conflict_paths: CONFLICTS }),
    summary: OBSIDIAN_SUMMARY,
    begin: (bench: ImportBench) => bench.choose('obsidian-zip', [ARCHIVE]),
    replay: [ARCHIVE, true, 'a1', SUPERSEDE],
  },
] as const;

describe.each(RETRIES)('useWikiImport: replacing the conflicting notes of $label', (kind) => {
  beforeEach(() => {
    world.tauri = kind.tauri;
    service[kind.method].mockResolvedValueOnce(kind.conflicted);
  });

  it('opens the conflict notice with the paths the import ran into', async () => {
    const bench = renderImport('a1');
    await kind.begin(bench);
    expect(bench.current().importConflictOpen).toBe(true);
    expect(bench.current().importConflictPaths).toEqual(CONFLICTS);
  });

  it('replays the import with the supersede option, closes the notice at once and shows it running', async () => {
    const bench = renderImport('a1');
    await kind.begin(bench);
    const pending = deferred<ImportResultResponse | ObsidianImportResultResponse>();
    service[kind.method].mockReturnValue(pending.promise);
    let retrying: Promise<void> = Promise.resolve();
    act(() => {
      retrying = bench.current().retryImportWithSupersede('newer notes');
    });
    expect(bench.current().importConflictOpen).toBe(false);
    expect(bench.current().importConflictPaths).toEqual([]);
    expect(bench.current()[kind.busy]).toBe(true);
    expect(service[kind.method]).toHaveBeenCalledTimes(2);
    expect(service[kind.method]).toHaveBeenLastCalledWith(...kind.replay);
    pending.resolve(kind.replaced);
    await act(() => retrying);
    expect(bench.current()[kind.busy]).toBe(false);
  });

  it('reports the replacement like the import it repeats and never asks about conflicts a second time', async () => {
    const bench = renderImport('a1');
    await kind.begin(bench);
    service[kind.method].mockResolvedValue(kind.replaced);
    await act(() => bench.current().retryImportWithSupersede('newer notes'));
    const summaries = toastTexts('success');
    expect(summaries).toHaveLength(2);
    expect(summaries.at(-1)).toBe(kind.summary);
    expect(bench.handleWikiTabChange).toHaveBeenCalledTimes(2);
    expect(bench.overview.loadStats).toHaveBeenCalledTimes(2);
    expect(bench.current().importConflictOpen).toBe(false);
    await act(() => bench.current().retryImportWithSupersede('again'));
    expect(service[kind.method]).toHaveBeenCalledTimes(2);
  });

  it('reports a failed replacement and logs it', async () => {
    const failure = new Error('network');
    const bench = renderImport('a1');
    await kind.begin(bench);
    service[kind.method].mockRejectedValue(failure);
    await act(() => bench.current().retryImportWithSupersede('newer notes'));
    expect(toastTexts('error')).toEqual(['errors.importFailed']);
    expect(consoleError).toHaveBeenCalledWith('Import supersede retry failed:', failure);
    expect(bench.current()[kind.busy]).toBe(false);
    expect(bench.current().importConflictOpen).toBe(false);
  });

  it('forgets the retry when the notice is dismissed', async () => {
    const bench = renderImport('a1');
    await kind.begin(bench);
    act(() => bench.current().dismissImportConflict());
    expect(bench.current().importConflictOpen).toBe(false);
    expect(bench.current().importConflictPaths).toEqual([]);
    await act(() => bench.current().retryImportWithSupersede('newer notes'));
    expect(service[kind.method]).toHaveBeenCalledOnce();
  });

  it('keeps the skipped notes, says how many and forgets the retry', async () => {
    const bench = renderImport('a1');
    await kind.begin(bench);
    act(() => bench.current().keepSkippedImports());
    expect(toast.message).toHaveBeenLastCalledWith('import.conflictSkippedToast|{"count":2}');
    expect(bench.current().importConflictOpen).toBe(false);
    expect(bench.current().importConflictPaths).toEqual([]);
    await act(() => bench.current().retryImportWithSupersede('newer notes'));
    expect(service[kind.method]).toHaveBeenCalledOnce();
  });
});

describe('useWikiImport: replacing the conflicting notes of a browser folder', () => {
  it('replays the generated archive', async () => {
    service.importZip.mockResolvedValueOnce(importResultOf({ conflict_paths: CONFLICTS }));
    const bench = renderImport('a1');
    await bench.choose('web-folder', [fileOf('a.md', 'v/a.md')]);
    await bench.idle();
    const [archive] = service.importZip.mock.calls[0] as [File];
    await act(() => bench.current().retryImportWithSupersede('newer notes'));
    expect(service.importZip).toHaveBeenLastCalledWith(archive, '.md,.txt,.org', true, 'a1', SUPERSEDE);
    expect(archive.name).toBe('folder-import.zip');
  });
});

describe('useWikiImport: conflict and security notices', () => {
  it('closes the conflict notice and starts nothing when there is nothing to retry', async () => {
    const bench = renderImport('a1');
    await act(() => bench.current().retryImportWithSupersede('newer notes'));
    expect(bench.current().importConflictOpen).toBe(false);
    expect(bench.current().isImporting).toBe(false);
    expect(bench.current().isImportingObsidian).toBe(false);
    expect(Object.values(service).filter((method) => method.mock.calls.length > 0)).toEqual([]);
    expect(toast.error).not.toHaveBeenCalled();
  });

  it.each([[undefined], [[]]])('opens no notice for an import without conflicts or findings (%j)', async (paths) => {
    service.importZip.mockResolvedValue(
      importResultOf({ conflict_paths: paths, security_blocked_paths: paths, security_redacted_paths: paths }),
    );
    const bench = renderImport();
    await bench.choose('zip', [ARCHIVE]);
    expect(bench.current().importConflictOpen).toBe(false);
    expect(bench.current().importSecurityOpen).toBe(false);
  });

  it.each([
    ['blocked files only', ['secret.md'], []],
    ['redacted files only', [], ['token.md']],
    ['both', ['secret.md'], ['token.md']],
  ])('opens the security notice for %s', async (_label, blocked, redacted) => {
    service.importZip.mockResolvedValue(
      importResultOf({ security_blocked_paths: blocked, security_redacted_paths: redacted }),
    );
    const bench = renderImport();
    await bench.choose('zip', [ARCHIVE]);
    expect(bench.current().importSecurityOpen).toBe(true);
    expect(bench.current().importSecurityBlockedPaths).toEqual(blocked);
    expect(bench.current().importSecurityRedactedPaths).toEqual(redacted);
    expect(bench.current().importConflictOpen).toBe(false);
  });

  it('empties and closes the security notice when it is dismissed', async () => {
    service.importZip.mockResolvedValue(
      importResultOf({ security_blocked_paths: ['secret.md'], security_redacted_paths: ['token.md'] }),
    );
    const bench = renderImport();
    await bench.choose('zip', [ARCHIVE]);
    act(() => bench.current().dismissImportSecurity());
    expect(bench.current().importSecurityOpen).toBe(false);
    expect(bench.current().importSecurityBlockedPaths).toEqual([]);
    expect(bench.current().importSecurityRedactedPaths).toEqual([]);
  });

  it('opens the notices only after the statistics are fresh', async () => {
    const reload = deferred<undefined>();
    service.importZip.mockResolvedValue(
      importResultOf({ conflict_paths: CONFLICTS, security_blocked_paths: ['secret.md'] }),
    );
    const bench = renderImport();
    bench.overview.loadStats.mockReturnValue(reload.promise);
    await bench.choose('zip', [ARCHIVE]);
    expect(bench.handleWikiTabChange).toHaveBeenCalledExactlyOnceWith('duplicateReview');
    expect(bench.current().importSecurityOpen).toBe(false);
    expect(bench.current().importConflictOpen).toBe(false);
    reload.resolve(undefined);
    await settle();
    expect(bench.current().importSecurityOpen).toBe(true);
    expect(bench.current().importConflictOpen).toBe(true);
  });

  it('still asks about the conflicts of an import that queued nothing, without announcing a duplicate scan', async () => {
    service.importZip.mockResolvedValue(
      importResultOf({ files_scanned: 2, files_enqueued: 0, conflict_paths: CONFLICTS }),
    );
    const bench = renderImport();
    await bench.choose('zip', [ARCHIVE]);
    expect(bench.current().importConflictOpen).toBe(true);
    expect(toast.message).not.toHaveBeenCalled();
    expect(bench.handleWikiTabChange).not.toHaveBeenCalled();
  });

  it('opens no notice for a refused import even when it lists paths', async () => {
    service.importZip.mockResolvedValue(
      importResultOf({
        success: false,
        message: 'Refused',
        conflict_paths: CONFLICTS,
        security_blocked_paths: ['secret.md'],
      }),
    );
    const bench = renderImport();
    await bench.choose('zip', [ARCHIVE]);
    expect(toastTexts('error')).toEqual(['errors.importFailed']);
    expect(bench.current().importConflictOpen).toBe(false);
    expect(bench.current().importSecurityOpen).toBe(false);
  });
});

describe('useWikiImport: link and video imports', () => {
  it('refreshes the statistics, then the tree views, after a link import', async () => {
    const reload = deferred<undefined>();
    const bench = renderImport();
    bench.overview.loadStats.mockReturnValue(reload.promise);
    let finished: Promise<void> = Promise.resolve();
    act(() => {
      finished = bench.current().handleUrlImportFinished(urlImportResultOf(0));
    });
    await settle();
    expect(bench.overview.bumpTreeSync).not.toHaveBeenCalled();
    reload.resolve(undefined);
    await act(() => finished);
    expect(bench.overview.bumpTreeSync).toHaveBeenCalledOnce();
  });

  it('reviews duplicates after a link import only when pages were queued', async () => {
    const bench = renderImport();
    await act(() => bench.current().handleUrlImportFinished(urlImportResultOf(0)));
    expect(toast.message).not.toHaveBeenCalled();
    expect(bench.handleWikiTabChange).not.toHaveBeenCalled();
    await act(() => bench.current().handleUrlImportFinished(urlImportResultOf(2)));
    expect(toastTexts('message')).toEqual(['import.dedupScanStarted']);
    expect(bench.handleWikiTabChange).toHaveBeenCalledExactlyOnceWith('duplicateReview');
    expect(bench.overview.loadStats).toHaveBeenCalledTimes(2);
    expect(bench.overview.bumpTreeSync).toHaveBeenCalledTimes(2);
  });

  it('refreshes the statistics, then the tree views, after a video import', async () => {
    const reload = deferred<undefined>();
    const bench = renderImport();
    bench.overview.loadStats.mockReturnValue(reload.promise);
    let finished: Promise<void> = Promise.resolve();
    act(() => {
      finished = bench.current().handleVideoImportFinished(videoImportResultOf({ success: false, status: 'error' }));
    });
    await settle();
    expect(bench.overview.bumpTreeSync).not.toHaveBeenCalled();
    reload.resolve(undefined);
    await act(() => finished);
    expect(bench.overview.bumpTreeSync).toHaveBeenCalledOnce();
  });

  it.each([
    ['imported', { success: true, status: 'success' }, true],
    ['replaced', { success: true, status: 'superseded' }, true],
    ['skipped for a conflict', { success: true, status: 'skipped_conflict' }, false],
    ['refused', { success: false, status: 'error' }, false],
  ] as const)('reviews duplicates after a video that was %s: %s', async (_label, over, reviews) => {
    const bench = renderImport();
    await act(() => bench.current().handleVideoImportFinished(videoImportResultOf(over)));
    expect(bench.handleWikiTabChange).toHaveBeenCalledTimes(reviews ? 1 : 0);
    expect(toast.message).toHaveBeenCalledTimes(reviews ? 1 : 0);
    expect(bench.overview.loadStats).toHaveBeenCalledOnce();
  });

  it('toggles the link and video dialogs independently', () => {
    const bench = renderImport();
    expect([bench.current().urlImportDialogOpen, bench.current().videoImportDialogOpen]).toEqual([false, false]);
    act(() => bench.current().setUrlImportDialogOpen(true));
    expect([bench.current().urlImportDialogOpen, bench.current().videoImportDialogOpen]).toEqual([true, false]);
    act(() => bench.current().setVideoImportDialogOpen(true));
    expect([bench.current().urlImportDialogOpen, bench.current().videoImportDialogOpen]).toEqual([true, true]);
  });
});
