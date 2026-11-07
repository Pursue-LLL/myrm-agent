/** @vitest-environment jsdom */
import { act, cleanup } from '@testing-library/react';
import JSZip from 'jszip';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ImportResultResponse, ObsidianImportResultResponse } from '@/services/wikiService';
import { deferred } from '@/test-utils/deferred';
import { settle } from '@/test-utils/fakeClock';
import { dialogOpen, resetKit, service, toast, toastTexts, world } from './wikiSectionTestKit';
import { fileOf, importResultOf, obsidianResultOf } from './wikiSectionFixtures';
import { renderImport } from './wikiImportBench';

const TEXT_EXTENSIONS = ['.md', '.txt', '.org'];
const OBSIDIAN_SUMMARY = 'import.obsidianResult|{"processed":5,"tags":2,"images":1,"skipped":1}';
let consoleError: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  resetKit();
  consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('useWikiImport: desktop folder import', () => {
  beforeEach(() => {
    world.tauri = true;
  });

  it('asks for a folder, imports it and sends the user to the duplicate review', async () => {
    const bench = renderImport('a1');
    expect(bench.current().isTauriEnv).toBe(true);
    await act(() => bench.current().handleImportFolder());
    expect(dialogOpen).toHaveBeenCalledExactlyOnceWith({
      directory: true,
      multiple: false,
      title: 'import.selectFolder',
    });
    expect(service.importFolder).toHaveBeenCalledExactlyOnceWith('/picked/folder', TEXT_EXTENSIONS, true, 'a1');
    expect(toastTexts('success')).toEqual(['Imported 3 files']);
    expect(toastTexts('message')).toEqual(['import.dedupScanStarted']);
    expect(toast.error).not.toHaveBeenCalled();
    expect(bench.handleWikiTabChange).toHaveBeenCalledExactlyOnceWith('duplicateReview');
    expect(bench.overview.loadStats).toHaveBeenCalledOnce();
    expect(bench.current().isImporting).toBe(false);
  });

  it('shows the import as running until the server answers', async () => {
    const pending = deferred<ImportResultResponse>();
    service.importFolder.mockReturnValue(pending.promise);
    const bench = renderImport();
    let importing: Promise<void> = Promise.resolve();
    act(() => {
      importing = bench.current().handleImportFolder();
    });
    await settle();
    expect(bench.current().isImporting).toBe(true);
    expect(bench.current().isImportingObsidian).toBe(false);
    pending.resolve(importResultOf());
    await act(() => importing);
    expect(bench.current().isImporting).toBe(false);
  });

  it('does nothing when the dialog is cancelled', async () => {
    dialogOpen.mockResolvedValue(null);
    const bench = renderImport();
    await act(() => bench.current().handleImportFolder());
    expect(service.importFolder).not.toHaveBeenCalled();
    expect(bench.current().isImporting).toBe(false);
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('reports a refusal from the server without reviewing duplicates', async () => {
    service.importFolder.mockResolvedValue(importResultOf({ success: false, message: 'The folder is empty' }));
    const bench = renderImport();
    await act(() => bench.current().handleImportFolder());
    expect(toastTexts('error')).toEqual(['The folder is empty']);
    expect(toast.success).not.toHaveBeenCalled();
    expect(toast.message).not.toHaveBeenCalled();
    expect(bench.handleWikiTabChange).not.toHaveBeenCalled();
    expect(bench.overview.loadStats).not.toHaveBeenCalled();
  });

  it('reports a failed request and logs it', async () => {
    const failure = new Error('network');
    service.importFolder.mockRejectedValue(failure);
    const bench = renderImport();
    await act(() => bench.current().handleImportFolder());
    expect(toastTexts('error')).toEqual(['errors.importFailed']);
    expect(consoleError).toHaveBeenCalledWith('Folder import failed:', failure);
    expect(bench.current().isImporting).toBe(false);
  });

  it('reports a dialog that cannot open the same way', async () => {
    const failure = new Error('no dialog');
    dialogOpen.mockRejectedValue(failure);
    const bench = renderImport();
    await act(() => bench.current().handleImportFolder());
    expect(toastTexts('error')).toEqual(['errors.importFailed']);
    expect(service.importFolder).not.toHaveBeenCalled();
    expect(consoleError).toHaveBeenCalledWith('Folder import failed:', failure);
  });
});

describe('useWikiImport: folder import in the browser', () => {
  it('opens the hidden folder picker instead of the desktop dialog', async () => {
    const click = vi.spyOn(HTMLInputElement.prototype, 'click').mockImplementation(() => undefined);
    const bench = renderImport();
    expect(bench.current().isTauriEnv).toBe(false);
    await act(() => bench.current().handleImportFolder());
    expect(click).toHaveBeenCalledOnce();
    expect(click.mock.contexts[0]).toBe(bench.input('web-folder'));
    expect(dialogOpen).not.toHaveBeenCalled();
  });

  it('zips only the notes it can read, keeps their relative paths and imports the archive', async () => {
    const bench = renderImport('a1');
    await bench.choose('web-folder', [
      fileOf('a.md', 'vault/a.md', 'alpha'),
      fileOf('B.TXT', 'vault/sub/B.TXT', 'beta'),
      fileOf('c.org', 'vault/c.org', 'gamma'),
      fileOf('photo.png', 'vault/photo.png'),
      fileOf('README', 'vault/README'),
      fileOf('loose.md', '', 'delta'),
    ]);
    await bench.idle();
    expect(service.importZip).toHaveBeenCalledOnce();
    const [archive, extensions, overwrite, scope] = service.importZip.mock.calls[0] as [File, string, boolean, string];
    expect(archive.name).toBe('folder-import.zip');
    expect(archive.type).toBe('application/zip');
    expect([extensions, overwrite, scope]).toEqual(['.md,.txt,.org', true, 'a1']);
    const entries = await JSZip.loadAsync(await archive.arrayBuffer());
    expect(
      entries
        .file(/.*/)
        .map((entry) => entry.name)
        .sort(),
    ).toEqual(['loose.md', 'vault/a.md', 'vault/c.org', 'vault/sub/B.TXT']);
    expect(await entries.file('vault/a.md')?.async('string')).toBe('alpha');
    expect(await entries.file('loose.md')?.async('string')).toBe('delta');
    expect(toastTexts('success')).toEqual(['Imported 3 files']);
    expect(bench.handleWikiTabChange).toHaveBeenCalledExactlyOnceWith('duplicateReview');
  });

  it('tells the user when the folder holds nothing it can import', async () => {
    const bench = renderImport();
    await bench.choose('web-folder', [fileOf('photo.png', 'v/photo.png'), fileOf('README', 'v/README')]);
    await bench.idle();
    expect(toastTexts('error')).toEqual(['import.noValidFiles']);
    expect(service.importZip).not.toHaveBeenCalled();
    expect(bench.current().isImporting).toBe(false);
  });

  it.each([null, []])('ignores a pick without files (%j)', async (files) => {
    const bench = renderImport();
    await bench.choose('web-folder', files);
    expect(service.importZip).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
    expect(bench.current().isImporting).toBe(false);
  });

  it('resets the picker after every import so the same folder can be chosen again', async () => {
    const bench = renderImport();
    const reset = vi.spyOn(bench.input('web-folder'), 'value', 'set');
    await bench.choose('web-folder', [fileOf('a.md', 'v/a.md')]);
    await bench.idle();
    expect(reset).toHaveBeenCalledExactlyOnceWith('');
    reset.mockClear();
    await bench.choose('web-folder', [fileOf('photo.png', 'v/photo.png')]);
    await bench.idle();
    expect(reset).toHaveBeenCalledExactlyOnceWith('');
  });

  it('reports a failed request, logs it and still resets the picker', async () => {
    const failure = new Error('network');
    service.importZip.mockRejectedValue(failure);
    const bench = renderImport();
    const reset = vi.spyOn(bench.input('web-folder'), 'value', 'set');
    await bench.choose('web-folder', [fileOf('a.md', 'v/a.md')]);
    await bench.idle();
    expect(toastTexts('error')).toEqual(['errors.importFailed']);
    expect(consoleError).toHaveBeenCalledWith('Web folder import failed:', failure);
    expect(reset).toHaveBeenCalledExactlyOnceWith('');
    expect(bench.current().isImporting).toBe(false);
  });
});

describe('useWikiImport: ZIP import', () => {
  it('imports the chosen archive and resets the picker', async () => {
    const archive = fileOf('notes.zip');
    const bench = renderImport('a1');
    const reset = vi.spyOn(bench.input('zip'), 'value', 'set');
    await bench.choose('zip', [archive]);
    expect(service.importZip).toHaveBeenCalledExactlyOnceWith(archive, '.md,.txt,.org', true, 'a1');
    expect(toastTexts('success')).toEqual(['Imported 3 files']);
    expect(bench.handleWikiTabChange).toHaveBeenCalledExactlyOnceWith('duplicateReview');
    expect(reset).toHaveBeenCalledExactlyOnceWith('');
    expect(bench.current().isImporting).toBe(false);
  });

  it('shows the import as running until the server answers', async () => {
    const pending = deferred<ImportResultResponse>();
    service.importZip.mockReturnValue(pending.promise);
    const bench = renderImport();
    await bench.choose('zip', [fileOf('notes.zip')]);
    expect(bench.current().isImporting).toBe(true);
    expect(bench.current().isImportingObsidian).toBe(false);
    pending.resolve(importResultOf());
    await settle();
    expect(bench.current().isImporting).toBe(false);
  });

  it.each([null, []])('ignores a pick without a file (%j)', async (files) => {
    const bench = renderImport();
    await bench.choose('zip', files);
    expect(service.importZip).not.toHaveBeenCalled();
    expect(bench.current().isImporting).toBe(false);
  });

  it('reports a failed upload, logs it and still resets the picker', async () => {
    const failure = new Error('network');
    service.importZip.mockRejectedValue(failure);
    const bench = renderImport();
    const reset = vi.spyOn(bench.input('zip'), 'value', 'set');
    await bench.choose('zip', [fileOf('notes.zip')]);
    expect(toastTexts('error')).toEqual(['errors.importFailed']);
    expect(consoleError).toHaveBeenCalledWith('ZIP import failed:', failure);
    expect(reset).toHaveBeenCalledExactlyOnceWith('');
    expect(bench.current().isImporting).toBe(false);
  });
});

describe('useWikiImport: Obsidian folder import', () => {
  it('offers no vault dialog outside the desktop app', async () => {
    const bench = renderImport();
    await act(() => bench.current().handleImportObsidianFolder());
    expect(dialogOpen).not.toHaveBeenCalled();
    expect(service.importObsidianFolder).not.toHaveBeenCalled();
  });

  describe('on the desktop', () => {
    beforeEach(() => {
      world.tauri = true;
    });

    it('imports the chosen vault, summarises it and points to the knowledge graph', async () => {
      const bench = renderImport('a1');
      await act(() => bench.current().handleImportObsidianFolder());
      expect(dialogOpen).toHaveBeenCalledExactlyOnceWith({
        directory: true,
        multiple: false,
        title: 'import.selectObsidianVault',
      });
      expect(service.importObsidianFolder).toHaveBeenCalledExactlyOnceWith('/picked/folder', true, 'a1');
      expect(toastTexts('success')).toEqual([OBSIDIAN_SUMMARY]);
      expect(toast.message).toHaveBeenNthCalledWith(1, 'obsidianVault.postWorkflowHint', {
        action: { label: 'obsidianVault.postWorkflowAction', onClick: bench.goToKnowledgeGraph },
      });
      expect(toast.message).toHaveBeenNthCalledWith(2, 'import.dedupScanStarted');
      expect(bench.handleWikiTabChange).toHaveBeenCalledExactlyOnceWith('duplicateReview');
      expect(bench.overview.loadStats).toHaveBeenCalledOnce();
      expect(bench.current().isImportingObsidian).toBe(false);
    });

    it('counts the notes skipped for a conflict with the ones skipped for other reasons', async () => {
      service.importObsidianFolder.mockResolvedValue(obsidianResultOf({ files_skipped: 1, files_skipped_conflict: 2 }));
      const bench = renderImport();
      await act(() => bench.current().handleImportObsidianFolder());
      expect(toastTexts('success')).toEqual(['import.obsidianResult|{"processed":5,"tags":2,"images":1,"skipped":3}']);
    });

    it('shows the import as running until the server answers', async () => {
      const pending = deferred<ObsidianImportResultResponse>();
      service.importObsidianFolder.mockReturnValue(pending.promise);
      const bench = renderImport();
      let importing: Promise<void> = Promise.resolve();
      act(() => {
        importing = bench.current().handleImportObsidianFolder();
      });
      await settle();
      expect(bench.current().isImportingObsidian).toBe(true);
      expect(bench.current().isImporting).toBe(false);
      pending.resolve(obsidianResultOf());
      await act(() => importing);
      expect(bench.current().isImportingObsidian).toBe(false);
    });

    it('does nothing when the dialog is cancelled', async () => {
      dialogOpen.mockResolvedValue(null);
      const bench = renderImport();
      await act(() => bench.current().handleImportObsidianFolder());
      expect(service.importObsidianFolder).not.toHaveBeenCalled();
      expect(bench.current().isImportingObsidian).toBe(false);
    });

    it('reports a refusal from the server', async () => {
      service.importObsidianFolder.mockResolvedValue(obsidianResultOf({ success: false, message: 'Not a vault' }));
      const bench = renderImport();
      await act(() => bench.current().handleImportObsidianFolder());
      expect(toastTexts('error')).toEqual(['Not a vault']);
      expect(toast.success).not.toHaveBeenCalled();
      expect(bench.handleWikiTabChange).not.toHaveBeenCalled();
    });

    it('reports a failed request and logs it', async () => {
      const failure = new Error('network');
      service.importObsidianFolder.mockRejectedValue(failure);
      const bench = renderImport();
      await act(() => bench.current().handleImportObsidianFolder());
      expect(toastTexts('error')).toEqual(['errors.importFailed']);
      expect(consoleError).toHaveBeenCalledWith('Obsidian folder import failed:', failure);
      expect(bench.current().isImportingObsidian).toBe(false);
    });
  });
});

describe('useWikiImport: Obsidian ZIP import', () => {
  it('imports the chosen archive, summarises it and resets the picker', async () => {
    const archive = fileOf('vault.zip');
    const bench = renderImport('a1');
    const reset = vi.spyOn(bench.input('obsidian-zip'), 'value', 'set');
    await bench.choose('obsidian-zip', [archive]);
    expect(service.importObsidianZip).toHaveBeenCalledExactlyOnceWith(archive, true, 'a1');
    expect(toastTexts('success')).toEqual([OBSIDIAN_SUMMARY]);
    expect(bench.handleWikiTabChange).toHaveBeenCalledExactlyOnceWith('duplicateReview');
    expect(reset).toHaveBeenCalledExactlyOnceWith('');
    expect(bench.current().isImportingObsidian).toBe(false);
  });

  it('shows the import as running until the server answers', async () => {
    const pending = deferred<ObsidianImportResultResponse>();
    service.importObsidianZip.mockReturnValue(pending.promise);
    const bench = renderImport();
    await bench.choose('obsidian-zip', [fileOf('vault.zip')]);
    expect(bench.current().isImportingObsidian).toBe(true);
    expect(bench.current().isImporting).toBe(false);
    pending.resolve(obsidianResultOf());
    await settle();
    expect(bench.current().isImportingObsidian).toBe(false);
  });

  it.each([null, []])('ignores a pick without a file (%j)', async (files) => {
    const bench = renderImport();
    await bench.choose('obsidian-zip', files);
    expect(service.importObsidianZip).not.toHaveBeenCalled();
    expect(bench.current().isImportingObsidian).toBe(false);
  });

  it('reports a failed upload, logs it and still resets the picker', async () => {
    const failure = new Error('network');
    service.importObsidianZip.mockRejectedValue(failure);
    const bench = renderImport();
    const reset = vi.spyOn(bench.input('obsidian-zip'), 'value', 'set');
    await bench.choose('obsidian-zip', [fileOf('vault.zip')]);
    expect(toastTexts('error')).toEqual(['errors.importFailed']);
    expect(consoleError).toHaveBeenCalledWith('Obsidian ZIP import failed:', failure);
    expect(reset).toHaveBeenCalledExactlyOnceWith('');
    expect(bench.current().isImportingObsidian).toBe(false);
  });
});
